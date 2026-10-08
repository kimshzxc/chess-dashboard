#!/usr/bin/env python3
"""체스닷컴 래피드 기보 자동 수집 → 스톡피시 분석 → 통계 → 대시보드 → 알림 → GitHub 업로드.

이 스크립트는 로컬 파일(data/chess.db, docs/)만 갱신한다. 저장소에 올리는 일은 GitHub Actions 워크플로
(.github/workflows/pipeline.yml)가 커밋으로 처리한다.

사용법:
  python pipeline.py                  수집 → 분석 → 통계 생성 → 알림
  python pipeline.py --quick          통계 API 로 새 게임 유무만 먼저 확인 (1분 간격 감시용)
  python pipeline.py --defer-notify   알림을 바로 보내지 않고 대기열에 쌓는다
  python pipeline.py --send-queued    대기열의 알림을 페이지 배포 확인 뒤 보낸다
  python pipeline.py --render-only    새 게임 수집/분석 없이 통계만 다시 생성
  python pipeline.py --weekly-dry     주간 요약 문장을 출력만 한다
"""
import argparse, base64, fcntl, io, json, math, os, re, sqlite3, sys, time, platform
import urllib.request, urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from multiprocessing import Pool

import chess, chess.pgn, chess.engine

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
DOCS = os.path.join(ROOT, "docs")
DB_PATH = os.path.join(DATA, "chess.db")
DEPTH = 18
REANALYZE_BATCH = 15   # 깊이가 바뀌면 한 번 실행에 이만큼씩 다시 분석 (새 게임이 항상 먼저)
LINE_DEPTH = 18        # 실수 국면의 정답/반격 수순 깊이 (수 평가와 같은 깊이여야 정답 수와 수순이 어긋나지 않는다)
LINES_BATCH = 40       # 한 번 실행에 수순을 계산할 국면 수 (최근 게임부터)
BOOK_DEPTH = 16        # 오프닝 연습 라인의 국면 평가 깊이 (상위 3수)
BOOK_BATCH = 150       # 한 번 실행에 오프닝 연습용으로 평가할 국면 수
BOOK_LINES = 4         # 오프닝 하나에 만드는 라인 수 (메인라인 + 상대가 자주 두는 갈래)
BOOK_MIN_N = 8         # 이 판 수 이상이거나 취약한 오프닝에 연습 라인을 만든다
ALT_WP = 5.0           # 최선 수와 승률 차이가 이 안(%p)이면 같이 좋은 수로 인정
WORKERS = 3
UA = "chess-dashboard/1.0 (personal analysis; github.com/{owner}/{repo})"
KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------- config
def load_env():
    """`.env` 를 읽어 dict 로 반환. 토큰은 실제 업로드 시점에만 사용한다."""
    cfg = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    for k in ("CHESSCOM_USERNAME", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_TOKEN", "NTFY_TOPIC", "STOCKFISH_PATH"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def stockfish_path(cfg):
    p = cfg.get("STOCKFISH_PATH") or os.path.join(ROOT, "engine", "stockfish")
    if not os.path.isfile(p):
        sys.exit(f"스톡피시 바이너리가 없습니다: {p}  (setup.sh 를 먼저 실행하세요)")
    return p


def log(msg):
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- db
def db():
    os.makedirs(DATA, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS games(
        url TEXT PRIMARY KEY, end_time INTEGER, date TEXT, my_color TEXT,
        white TEXT, black TEXT, welo INTEGER, belo INTEGER, opp TEXT, opp_elo INTEGER, my_elo INTEGER,
        result TEXT, outcome TEXT, my_result TEXT, opp_result TEXT, termination TEXT,
        eco TEXT, eco_name TEXT, time_control TEXT, pgn TEXT,
        analyzed INTEGER DEFAULT 0, notified INTEGER DEFAULT 0, summary TEXT);
    CREATE TABLE IF NOT EXISTS plies(
        url TEXT, ply INTEGER, move INTEGER, mover TEXT, mine INTEGER,
        san TEXT, best TEXT, is_best INTEGER, cp_before INTEGER, cp_after INTEGER,
        loss INTEGER, wp_loss REAL, clock REAL, spent REAL, capture INTEGER, chk INTEGER,
        piece INTEGER, phase TEXT, fen TEXT, PRIMARY KEY(url, ply));
    CREATE INDEX IF NOT EXISTS plies_url ON plies(url);
    CREATE TABLE IF NOT EXISTS lines(fen TEXT, played TEXT, best TEXT, data TEXT, PRIMARY KEY(fen, played, best));
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS book(fen TEXT PRIMARY KEY, depth INTEGER, data TEXT);
    """)
    cols = {r[1] for r in con.execute("PRAGMA table_info(games)")}
    if "pushed" not in cols:
        con.execute("ALTER TABLE games ADD COLUMN pushed INTEGER DEFAULT 0")
        con.commit()
    if "depth" not in cols:
        con.execute("ALTER TABLE games ADD COLUMN depth INTEGER")
        con.commit()
    return con


# ---------------------------------------------------------------- fetch
def has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def meta_get(con, k):
    r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else None


def meta_set(con, k, v):
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, v))
    con.commit()


def http_json(url, cfg, headers=None):
    h = {"User-Agent": UA.format(owner=cfg.get("GITHUB_OWNER", "x"), repo=cfg.get("GITHUB_REPO", "x"))}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


OUTCOME_DRAW = {"agreed", "insufficient", "stalemate", "repetition", "timevsinsufficient", "50move"}


def fetch_new_games(con, cfg, quick=False):
    """새 래피드 게임을 DB 에 넣고 url 목록을 돌려준다.
    quick=True 면 1KB 짜리 플레이어 통계로 마지막 래피드 게임 시각만 먼저 보고, DB 보다 새로울 때만 월간 기보를 받는다 (1분 간격 감시용)."""
    me = cfg["CHESSCOM_USERNAME"].lower()
    if quick:
        last_known = con.execute("SELECT MAX(end_time) FROM games").fetchone()[0]
        try:
            last_ts = http_json(f"https://api.chess.com/pub/player/{me}/stats", cfg).get("chess_rapid", {}).get("last", {}).get("date")
        except Exception:
            last_ts = None
        if last_known and last_ts and last_ts <= last_known:
            return []
    archives = http_json(f"https://api.chess.com/pub/player/{me}/games/archives", cfg)["archives"]
    known = {r[0] for r in con.execute("SELECT url FROM games")}
    new = []
    for arch in archives[-2:]:  # 이번 달 + 지난 달
        for g in http_json(arch, cfg)["games"]:
            if g.get("time_class") != "rapid" or g.get("rules") != "chess":
                continue
            if g["url"] in known or "pgn" not in g:
                continue
            side = "white" if g["white"]["username"].lower() == me else "black"
            opp = "black" if side == "white" else "white"
            r = g[side]["result"]
            outcome = "W" if r == "win" else ("D" if r in OUTCOME_DRAW else "L")
            hdr = dict(re.findall(r'\[(\w+) "([^"]*)"\]', g["pgn"]))
            eco_name = hdr.get("ECOUrl", "").rsplit("/", 1)[-1].replace("-", " ")
            row = dict(url=g["url"], end_time=g["end_time"],
                       date=datetime.fromtimestamp(g["end_time"], KST).strftime("%Y-%m-%d"),
                       my_color="w" if side == "white" else "b",
                       white=g["white"]["username"], black=g["black"]["username"],
                       welo=g["white"]["rating"], belo=g["black"]["rating"],
                       opp=g[opp]["username"], opp_elo=g[opp]["rating"], my_elo=g[side]["rating"],
                       result=hdr.get("Result"), outcome=outcome, my_result=r, opp_result=g[opp]["result"],
                       termination=hdr.get("Termination"), eco=hdr.get("ECO"), eco_name=eco_name,
                       time_control=g.get("time_control"), pgn=g["pgn"])
            con.execute("INSERT INTO games(url,end_time,date,my_color,white,black,welo,belo,opp,opp_elo,my_elo,"
                        "result,outcome,my_result,opp_result,termination,eco,eco_name,time_control,pgn) "
                        "VALUES(:url,:end_time,:date,:my_color,:white,:black,:welo,:belo,:opp,:opp_elo,:my_elo,"
                        ":result,:outcome,:my_result,:opp_result,:termination,:eco,:eco_name,:time_control,:pgn)", row)
            new.append(row["url"])
    con.commit()
    return new


# ---------------------------------------------------------------- engine analysis
clk_re = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")


def clk(comment):
    m = clk_re.search(comment or "")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def cp_of(score, pov):
    s = score.pov(pov)
    if s.is_mate():
        m = s.mate()
        return (10000 - abs(m) * 10) if m > 0 else (-10000 + abs(m) * 10)
    return max(-1500, min(1500, s.score()))


def winpct(cp):
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def phase_of(board):
    v = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3, chess.KNIGHT: 3}
    tot = sum(v[p] * len(board.pieces(p, c)) for p in v for c in (True, False))
    if board.fullmove_number <= 10:
        return "opening"
    return "endgame" if tot <= 14 else "middlegame"


def analyze_game(args):
    url, pgn_text, my_color, sf = args[:4]
    threads = args[4] if len(args) > 4 else 1
    eng = chess.engine.SimpleEngine.popen_uci(sf)
    eng.configure({"Hash": 32 if threads == 1 else 128, "Threads": threads})
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
        board = game.board()
        my = chess.WHITE if my_color == "w" else chess.BLACK
        info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
        prev_cp_w, prev_best = cp_of(info["score"], chess.WHITE), info.get("pv", [None])[0]
        prev_clk = {chess.WHITE: 600.0, chess.BLACK: 600.0}
        plies, node = [], game
        while node.variations:
            nxt = node.variation(0)
            mv, mover = nxt.move, board.turn
            san = board.san(mv)
            best_san = board.san(prev_best) if prev_best else None
            rec = dict(ply=len(plies) + 1, move=board.fullmove_number, mover="w" if mover else "b",
                       mine=int(mover == my), san=san, best=best_san, is_best=int(mv == prev_best),
                       capture=int(board.is_capture(mv)), chk=int(board.gives_check(mv)),
                       piece=board.piece_type_at(mv.from_square), phase=phase_of(board), fen=board.fen())
            board.push(mv)
            if board.is_checkmate():
                cp_w = 10000 if mover == chess.WHITE else -10000
                best_next = None
            elif board.is_stalemate() or board.is_insufficient_material():
                cp_w, best_next = 0, None
            else:
                info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
                cp_w, best_next = cp_of(info["score"], chess.WHITE), info.get("pv", [None])[0]
            before = prev_cp_w if mover == chess.WHITE else -prev_cp_w
            after = cp_w if mover == chess.WHITE else -cp_w
            c = clk(nxt.comment)
            spent = None
            if c is not None:
                spent = round(prev_clk[mover] - c, 1)
                prev_clk[mover] = c
            rec.update(cp_before=before, cp_after=after, loss=max(0, before - after),
                       wp_loss=round(max(0, winpct(before) - winpct(after)), 1), clock=c, spent=spent)
            plies.append(rec)
            prev_cp_w, prev_best, node = cp_w, best_next, nxt
        return url, plies
    finally:
        eng.quit()


def acc(wp_losses):
    a = [max(0, min(100, 103.1668 * math.exp(-0.04354 * w) - 3.1669)) for w in wp_losses]
    return round(sum(a) / len(a), 1) if a else None


def opp_best_captures(p, nxt):
    """내 수 뒤 상대 최선수가 내 기물(폰 제외)을 잡는지 → 잡히는 기물 종류 (없으면 None)."""
    if not nxt or not nxt.get("best"):
        return None
    b = chess.Board(p["fen"])
    try:
        b.push_san(p["san"])
        rep = b.parse_san(nxt["best"])
    except Exception:
        return None
    if b.is_capture(rep):
        pt = b.piece_type_at(rep.to_square)
        if pt and pt >= 2:
            return pt
    return None


# ---------------------------------------------------------------- 실수 유형 분류
# 내 수 중 승률을 MISTAKE_WP %p 이상 잃은 수를 "실수"로 보고, 왜 틀렸는지를 한 가지 유형으로 나눈다.
# 엔진을 다시 돌리지 않고 저장된 값(국면, 둔 수, 최선 수, 다음 국면의 상대 최선 수)만 쓴다.
# 유형의 이름·설명·규칙 문장은 docs/shared.js 의 CATS 에 있다 (키가 같아야 한다).
MISTAKE_WP = 10.0
EARLY_MOVES = 15       # 오프닝 단계로 보는 수 (오프닝별 실수 집계)
CAT_KEYS = ("into_capture", "ignored_threat", "unguard", "bad_trade", "allowed_tactic", "allowed_mate",
            "missed_capture", "missed_tactic", "missed_mate", "opening", "middlegame", "endgame")
PIECE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def is_mistake(p):
    return bool(p["mine"] and p["wp_loss"] >= MISTAKE_WP and p["best"] and p["best"] != p["san"])


def _creates_threat(after, reply):
    """상대의 수 reply 가 내 기물(킹 제외)을 새로 노리는가: 더 비싼 기물을 공격하거나, 지켜지지 않은 기물을 공격."""
    b = after.copy()
    b.push(reply)
    pt, me = b.piece_type_at(reply.to_square), b.turn
    for sq in b.attacks(reply.to_square):
        q = b.piece_at(sq)
        if q and q.color == me and q.piece_type != chess.KING and \
                (PIECE_VAL[q.piece_type] > PIECE_VAL[pt] or not b.attackers(me, sq)):
            return True
    return False


def mistake_cat(p, nxt):
    """실수 하나의 유형 키. p = 내 수, nxt = 바로 다음 수(상대) 레코드 또는 None. 위에서부터 먼저 맞는 것 하나.
      missed_mate     강제 외통이 있었는데 놓침
      allowed_mate    이 수로 강제 외통을 허용
      into_capture    잡히는 칸으로 기물을 옮김
      ignored_threat  이미 공격받던 기물을 그대로 둠
      unguard         지키던 기물을 떼거나 길을 열어 다른 기물이 잡힘
      bad_trade       손해 보는 잡기·교환
      missed_capture  잡는 수가 최선이었는데 안 잡음
      missed_tactic   체크로 시작하는 수가 최선이었는데 놓침
      allowed_tactic  상대의 다음 한 수(체크·잡기·새 위협)를 못 봄
      opening / middlegame / endgame   위에 해당하지 않는 조용한 실수 (국면별)"""
    try:
        b = chess.Board(p["fen"])
        mv = b.parse_san(p["san"])
    except Exception:
        return p["phase"]
    try:
        best = b.parse_san(p["best"]) if p.get("best") else None
    except Exception:
        best = None
    if p["cp_before"] >= 9000 and p["cp_after"] < 9000:
        return "missed_mate"
    if p["cp_after"] <= -9000 and p["cp_before"] > -9000:
        return "allowed_mate"
    me = b.turn
    after = b.copy()
    after.push(mv)
    reply = None
    if nxt and nxt.get("best"):
        try:
            reply = after.parse_san(nxt["best"])
        except Exception:
            reply = None
    loss = p["loss"]
    if reply and loss >= 200 and after.is_capture(reply):
        to = reply.to_square
        pt = after.piece_type_at(to)
        if pt and pt >= chess.KNIGHT:
            if to == mv.to_square:
                if not b.is_capture(mv):
                    return "into_capture"
                if PIECE_VAL[b.piece_type_at(mv.from_square)] > PIECE_VAL[b.piece_type_at(mv.to_square) or chess.PAWN]:
                    return "bad_trade"
            else:
                existed = reply.from_square in b.attackers(not me, to)     # 두기 전에도 같은 기물이 노리고 있었나
                was_guard = mv.from_square in b.attackers(me, to)          # 움직인 기물이 그 칸을 지키고 있었나
                return "ignored_threat" if existed and not was_guard else "unguard"
    if best and loss >= 150 and b.is_capture(best):
        return "missed_capture"
    if best and loss >= 150 and b.gives_check(best):
        return "missed_tactic"
    if loss >= 150 and b.is_capture(mv):
        return "bad_trade"
    if reply and loss >= 200 and (after.is_capture(reply) or after.gives_check(reply) or _creates_threat(after, reply)):
        return "allowed_tactic"
    return p["phase"]


def tag_mistakes(plies):
    """게임 하나의 수 목록에서 내 실수에 cat 을 붙인다 (제자리 수정)."""
    for i, p in enumerate(plies):
        if is_mistake(p):
            p["cat"] = mistake_cat(p, plies[i + 1] if i + 1 < len(plies) else None)
    return plies


def summarize(plies):
    """게임 하나의 요약 (DB summary 컬럼, 알림, 최근 게임 목록에 사용)."""
    mine = [p for p in plies if p["mine"]]
    opp = [p for p in plies if not p["mine"]]
    worst = max(mine, key=lambda p: p["wp_loss"], default=None)
    my_clk = [p["clock"] for p in mine if p["clock"] is not None]
    op_clk = [p["clock"] for p in opp if p["clock"] is not None]
    hung = 0
    for i, p in enumerate(plies):
        if p["mine"] and p["loss"] >= 200 and opp_best_captures(p, plies[i + 1] if i + 1 < len(plies) else None):
            hung += 1
    missed_mate = sum(1 for p in mine if p["cp_before"] >= 9000 and p["cp_after"] < 9000)
    return dict(
        accuracy=acc([p["wp_loss"] for p in mine]), opp_accuracy=acc([p["wp_loss"] for p in opp]),
        blunders=sum(1 for p in mine if p["loss"] >= 300), mistakes=sum(1 for p in mine if 100 <= p["loss"] < 300),
        opp_blunders=sum(1 for p in opp if p["loss"] >= 300),
        worst=(dict(move=worst["move"], mover=worst["mover"], san=worst["san"], best=worst["best"],
                    cp_before=worst["cp_before"], cp_after=worst["cp_after"], wp_loss=worst["wp_loss"],
                    clock=worst["clock"], fen=worst["fen"], uci=uci_of(worst["fen"], worst["san"]),
                    best_uci=uci_of(worst["fen"], worst["best"]) if worst["best"] else None) if worst else None),
        n_moves=len(mine), hung=hung, missed_mate=missed_mate,
        my_clock_20=(my_clk[19] if len(my_clk) >= 20 else None), opp_clock_20=(op_clk[19] if len(op_clk) >= 20 else None),
        my_final_clock=(my_clk[-1] if my_clk else None), opp_final_clock=(op_clk[-1] if op_clk else None),
        max_eval=max((p["cp_after"] for p in mine), default=0), min_eval=min((p["cp_after"] for p in mine), default=0),
    )


def uci_of(fen, san):
    try:
        return chess.Board(fen).parse_san(san).uci()
    except Exception:
        return None


def pv_steps(board, pv, max_plies=6):
    """PV(move list) → [{san, uci, fen}] (fen = 그 수를 둔 뒤 국면)."""
    out, b = [], board.copy()
    for mv in pv[:max_plies]:
        san = b.san(mv)
        b.push(mv)
        out.append(dict(san=san, uci=mv.uci(), fen=b.fen()))
    return out



def engine_lines(eng, fen, played_san, best_san):
    """실수 국면 하나: 저장된 최선 수로 시작하는 정답 수순, 내 수 뒤 상대의 반격 수순, 최선과 비슷하게 좋은 다른 수.
    puzzle_ok=False 는 퍼즐로 쓰기 어려운 국면(좋은 수가 4개 이상이거나 분석이 서로 엇갈림)."""
    b = chess.Board(fen)
    played = b.parse_san(played_san)
    try:
        best = b.parse_san(best_san) if best_san else None
    except Exception:
        best = None
    infos = eng.analyse(b, chess.engine.Limit(depth=LINE_DEPTH), multipv=4)
    ents = [(i["pv"][0], cp_of(i["score"], b.turn), i["pv"]) for i in infos if i.get("pv")]
    ref = next((e for e in ents if e[0] == best), None)
    if ref is None and best is not None:   # 저장된 최선 수가 상위 4수 밖이면 그 수만 따로 평가
        i = eng.analyse(b, chess.engine.Limit(depth=LINE_DEPTH), root_moves=[best])
        ref = (best, cp_of(i["score"], b.turn), i.get("pv") or [best])
    if ref is None:
        ref = ents[0]
    top_wp, ref_wp = winpct(ents[0][1]), winpct(ref[1])
    good = [e for e in ents if e[0] != ref[0] and winpct(e[1]) >= ref_wp - ALT_WP]
    puzzle_ok = (len(good) < 3                                  # 정답 포함 좋은 수가 4개 이상이면 아무 수나 정답이 된다
                 and top_wp - ref_wp <= ALT_WP                  # 저장된 최선이 엔진 1순위보다 뚜렷이 나쁘면 분석이 엇갈린 것
                 and not any(e[0] == played for e in good))     # 내가 둔 수가 좋은 수로 나오면 실수 판정이 엇갈린 것
    alts = [dict(san=b.san(e[0]), uci=e[0].uci()) for e in good if e[0] != played]
    refutation = []
    b2 = b.copy()
    b2.push(played)
    if not b2.is_game_over():
        info2 = eng.analyse(b2, chess.engine.Limit(depth=LINE_DEPTH))
        refutation = pv_steps(b2, info2.get("pv", []), 5)
    return dict(best_line=pv_steps(b, ref[2]), refutation=refutation, alts=alts, puzzle_ok=puzzle_ok)



def lines_todo(con):
    """수순이 필요한데 아직 계산되지 않은 (fen, 둔 수, 최선 수) 목록. 최근 게임 순."""
    todo, seen = [], set()

    def add(fen, san, best):
        k = (fen, san, best)
        if not best or k in seen:
            return
        seen.add(k)
        if not con.execute("SELECT 1 FROM lines WHERE fen=? AND played=? AND best=?", k).fetchone():
            todo.append(k)
    # 1) 큰 실수 (승률 20%p 이상 또는 3점 이상 손해)
    for r in con.execute("""SELECT p.fen, p.san, p.best FROM plies p JOIN games g ON g.url=p.url
                            WHERE p.mine=1 AND p.best IS NOT NULL AND (p.wp_loss>=20 OR p.loss>=300)
                              AND NOT EXISTS (SELECT 1 FROM lines l WHERE l.fen=p.fen AND l.played=p.san AND l.best=p.best)
                            ORDER BY g.end_time DESC, p.ply""").fetchall():
        add(r[0], r[1], r[2])
    # 2) 판마다 가장 아픈 수 (최근 게임 목록의 장면 보기)
    for g in con.execute("SELECT summary FROM games WHERE analyzed=1 ORDER BY end_time DESC").fetchall():
        w = (json.loads(g[0] or "{}") or {}).get("worst")
        if w and w.get("fen"):
            add(w["fen"], w["san"], w.get("best"))
    # 3) 오프닝에서 반복되는 실수
    for r in con.execute("""SELECT fen, san FROM plies WHERE mine=1 AND move<=15 AND best IS NOT NULL AND best!=san
                            GROUP BY fen, san HAVING count(*)>=2 AND avg(loss)>=60""").fetchall():
        add(r[0], r[1], common_best(con, r[0], r[1]))
    return todo


def common_best(con, fen, san):
    """같은 국면·같은 수에 대해 여러 판의 분석이 고른 최선 수 중 가장 흔한 것 (기간 탭과 무관하게 일정)."""
    r = con.execute("""SELECT best FROM plies WHERE fen=? AND san=? AND mine=1 AND best IS NOT NULL
                       GROUP BY best ORDER BY count(*) DESC, best LIMIT 1""", (fen, san)).fetchone()
    return r[0] if r else None


def enrich_lines(con, cfg, limit=LINES_BATCH):
    """실수 국면의 정답/반격 수순과 복수 정답을 계산해 lines 테이블에 저장한다.
    (계산한 국면 수, 게임 상세 JSON 을 다시 내보내야 하는 게임 url 집합) 을 돌려준다."""
    todo = lines_todo(con)
    if not todo:
        if has_table(con, "pv_cache"):   # 예전(깊이 16) 캐시는 새 계산이 모두 끝나면 버린다
            con.execute("DROP TABLE pv_cache")
            con.commit()
            con.execute("VACUUM")
            log("예전 수순 캐시(pv_cache) 삭제")
        return 0, set()
    batch = todo[:limit]
    log(f"수순 계산 {len(batch)}개 국면 (남은 {len(todo) - len(batch)}개, depth {LINE_DEPTH})")
    eng = chess.engine.SimpleEngine.popen_uci(stockfish_path(cfg))
    eng.configure({"Hash": 128, "Threads": WORKERS})
    try:
        for fen, san, best in batch:
            try:
                data = engine_lines(eng, fen, san, best)
            except Exception as e:   # 한 국면이 실패해도 계속. 빈 결과를 저장해 매번 다시 시도하지 않는다
                log(f"  수순 계산 실패 {san}: {e}")
                data = dict(best_line=[], refutation=[], alts=[], puzzle_ok=False)
            con.execute("INSERT OR REPLACE INTO lines(fen,played,best,data) VALUES(?,?,?,?)",
                        (fen, san, best, json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
        con.commit()
    finally:
        eng.quit()
    urls = set()
    for fen, san, _ in batch:
        urls.update(r[0] for r in con.execute("SELECT DISTINCT url FROM plies WHERE fen=? AND san=? AND mine=1", (fen, san)))
    return len(batch), urls



def cached_lines(con, fen, san, best=None):
    """계산해 둔 수순. lines 테이블(현재 깊이)이 우선이고, 아직 없으면 예전 pv_cache 를 쓰되
    그 정답 수순의 첫 수가 최선 수와 다르면 숨긴다 (깊이가 달라 어긋난 경우)."""
    r = con.execute("SELECT data FROM lines WHERE fen=? AND played=? AND best=?", (fen, san, best or "")).fetchone()
    if r:
        d = json.loads(r[0])
        return dict(best_line=d.get("best_line", []), refutation=d.get("refutation", []), alts=d.get("alts", []))
    if has_table(con, "pv_cache"):
        r = con.execute("SELECT data FROM pv_cache WHERE fen=? AND played=?", (fen, san)).fetchone()
        if r:
            d = json.loads(r[0])
            bl = d.get("best_line") or []
            if bl and best and bl[0]["san"] != best:
                bl = []
            return dict(best_line=bl, refutation=d.get("refutation", []), alts=[])
    return dict(best_line=[], refutation=[], alts=[])


PLY_COLS = ("ply", "move", "mover", "mine", "san", "best", "is_best", "cp_before", "cp_after", "loss", "wp_loss",
            "clock", "spent", "capture", "chk", "piece", "phase", "fen")


def store_analysis(con, url, plies):
    con.execute("DELETE FROM plies WHERE url=?", (url,))
    con.executemany(f"INSERT INTO plies(url,{','.join(PLY_COLS)}) VALUES(?,{','.join('?' * len(PLY_COLS))})",
                    [(url, *[p.get(c) for c in PLY_COLS]) for p in plies])
    con.execute("UPDATE games SET analyzed=1, depth=?, summary=? WHERE url=?", (DEPTH, json.dumps(summarize(plies)), url))
    con.commit()


def analyze_pending(con, cfg):
    sf = stockfish_path(cfg)
    rows = con.execute("SELECT url,pgn,my_color FROM games WHERE analyzed=0 ORDER BY end_time").fetchall()
    redo = con.execute("SELECT url,pgn,my_color FROM games WHERE analyzed=1 AND (depth IS NULL OR depth!=?) ORDER BY end_time DESC LIMIT ?",
                       (DEPTH, REANALYZE_BATCH)).fetchall()
    if not rows and not redo:
        return []
    if rows:
        log(f"분석 대기 {len(rows)}판 (depth {DEPTH}, {WORKERS} 프로세스)")
    if redo:
        left = con.execute("SELECT COUNT(*) FROM games WHERE analyzed=1 AND (depth IS NULL OR depth!=?)", (DEPTH,)).fetchone()[0]
        log(f"깊이 {DEPTH} 로 재분석 {len(redo)}판 (남은 {left}판)")
    rows = list(rows) + list(redo)
    tasks = [(r["url"], r["pgn"], r["my_color"], sf) for r in rows]
    done = []
    t0 = time.time()

    def finish(url, plies):
        store_analysis(con, url, plies)
        export_game(con, dict(con.execute("SELECT * FROM games WHERE url=?", (url,)).fetchone()))
        done.append(url)
        log(f"  분석 완료 {url} ({time.time() - t0:.0f}s)")

    if len(tasks) == 1:   # 한 판이면 엔진 스레드를 모두 써서 알림을 앞당긴다
        finish(*analyze_game(tasks[0] + (WORKERS,)))
    else:
        with Pool(min(WORKERS, len(tasks))) as pool:
            for url, plies in pool.imap_unordered(analyze_game, tasks):
                finish(url, plies)
    return done


# ---------------------------------------------------------------- stats
def load_games(con, since_ts=None):
    q = "SELECT * FROM games WHERE analyzed=1"
    args = ()
    if since_ts:
        q += " AND end_time>=?"
        args = (since_ts,)
    games = [dict(r) for r in con.execute(q + " ORDER BY end_time", args)]
    for g in games:
        g["summary"] = json.loads(g["summary"]) if g["summary"] else {}
        g["plies"] = tag_mistakes([dict(r) for r in con.execute("SELECT * FROM plies WHERE url=? ORDER BY ply", (g["url"],))])
    return games


def median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def with_lines(con, w):
    """실수 레코드에 uci / 정답 수순 / 반격 수순 / 이후 FEN 을 붙인다 (뷰어·퍼즐·알림용)."""
    if not w or not w.get("fen"):
        return w
    w = dict(w)
    if not w.get("uci"):
        w["uci"] = uci_of(w["fen"], w["san"])
        w["best_uci"] = uci_of(w["fen"], w["best"]) if w.get("best") else None
    w.update(cached_lines(con, w["fen"], w["san"], w.get("best")) if con else dict(best_line=[], refutation=[], alts=[]))
    try:
        b = chess.Board(w["fen"]); b.push_san(w["san"]); w["after_fen"] = b.fen()
    except Exception:
        w["after_fen"] = None
    return w


SESSION_GAP = 1800   # 30분 이상 비면 새 세션


def session_context(games):
    """게임(시간순) → {url: dict(pos=세션 내 몇 판째, streak=같은 세션에서 직전 연패 수, prev=직전 판 결과 또는 None, hour=KST 시)}"""
    ctx, prev, streak, pos = {}, None, 0, 0
    for g in games:
        if prev is None or g["end_time"] - prev["end_time"] > SESSION_GAP:
            streak, pos, prev_out = 0, 0, None
        else:
            prev_out = prev["outcome"]
        pos += 1
        ctx[g["url"]] = dict(pos=pos, streak=streak, prev=prev_out, hour=datetime.fromtimestamp(g["end_time"], KST).hour)
        streak = streak + 1 if g["outcome"] == "L" else 0
        prev = g
    return ctx


def _score(outs):
    c = Counter(outs)
    return round((c["W"] + 0.5 * c["D"]) / len(outs) * 100, 1) if outs else None


def tilt_stats(games):
    """틸트·세션: 직전 결과별 승률, 연패 후 승률, 세션 내 순서별 승률·정확도, 시간대별."""
    ctx = session_context(games)
    after, streak, spos, hours = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for g in games:
        c = ctx[g["url"]]
        if c["prev"]:
            after[c["prev"]].append(g)
            streak[min(c["streak"], 3)].append(g)
        spos[1 if c["pos"] == 1 else 2 if c["pos"] == 2 else 3 if c["pos"] == 3 else 4 if c["pos"] <= 5 else 6].append(g)
        hours[c["hour"] // 6].append(g)
    def pack(gs, label):
        acc_v = acc([p["wp_loss"] for g in gs for p in g["plies"] if p["mine"]]) if gs else None
        return dict(label=label, n=len(gs), score=_score([g["outcome"] for g in gs]), accuracy=acc_v,
                    blunders_pg=round(sum(g["summary"].get("blunders", 0) for g in gs) / len(gs), 2) if gs else None)
    sess, cur = [], []
    for g in games:
        if cur and g["end_time"] - cur[-1]["end_time"] > SESSION_GAP:
            sess.append(cur); cur = []
        cur.append(g)
    if cur:
        sess.append(cur)
    lens = sorted(len(x) for x in sess)
    return dict(
        after=[pack(after[k], l) for k, l in (("W", "직전 판 승리"), ("D", "직전 판 무승부"), ("L", "직전 판 패배"))],
        streak=[pack(streak[k], l) for k, l in ((0, "연패 없음"), (1, "1연패 후"), (2, "2연패 후"), (3, "3연패 이상 후"))],
        session_pos=[pack(spos[k], l) for k, l in ((1, "세션 1판째"), (2, "2판째"), (3, "3판째"), (4, "4~5판째"), (6, "6판째 이후"))],
        sessions=dict(n=len(sess), median_len=lens[len(lens) // 2] if lens else 0, max_len=lens[-1] if lens else 0,
                      long=sum(1 for x in sess if len(x) >= 6)),
        hours=[pack(hours[k], l) for k, l in ((0, "0~6시"), (1, "6~12시"), (2, "12~18시"), (3, "18~24시"))],
    )


def compute_stats(games, con=None):
    if not games:
        return None
    mine = [p for g in games for p in g["plies"] if p["mine"]]
    opp = [p for g in games for p in g["plies"] if not p["mine"]]
    n = len(games)
    oc = Counter(g["outcome"] for g in games)
    S = {}
    S["overview"] = dict(
        games=n, win=oc["W"], draw=oc["D"], loss=oc["L"], score=round((oc["W"] + 0.5 * oc["D"]) / n * 100, 1),
        accuracy=acc([p["wp_loss"] for p in mine]), opp_accuracy=acc([p["wp_loss"] for p in opp]),
        blunders_pg=round(sum(1 for p in mine if p["loss"] >= 300) / n, 2),
        opp_blunders_pg=round(sum(1 for p in opp if p["loss"] >= 300) / n, 2),
        rating=games[-1]["my_elo"], rating_best=max(g["my_elo"] for g in games), rating_start=games[0]["my_elo"],
        first_date=games[0]["date"], last_date=games[-1]["date"],
    )
    for c in "wb":
        gs = [g for g in games if g["my_color"] == c]
        cc = Counter(g["outcome"] for g in gs)
        S["overview"][f"score_{c}"] = round((cc["W"] + 0.5 * cc["D"]) / len(gs) * 100, 1) if gs else None
        S["overview"][f"games_{c}"] = len(gs)

    # --- 시간 관리
    def clocks_at(k, who):
        out = []
        for g in games:
            v = [p["clock"] for p in g["plies"] if bool(p["mine"]) == who and p["clock"] is not None]
            if len(v) >= k:
                out.append(v[k - 1])
        return out
    tm = {"clock_at": [dict(move=k, me=median(clocks_at(k, True)), opp=median(clocks_at(k, False))) for k in (10, 20, 30, 40)]}
    to = [g for g in games if g["my_result"] == "timeout"]
    tm["timeouts"] = len(to)
    tm["timeouts_winning"] = sum(1 for g in to if g["summary"].get("max_eval", 0) >= 200 and
                                 [p for p in g["plies"] if p["mine"]][-1]["cp_after"] >= 200)
    tm["opp_timeouts"] = sum(1 for g in games if g["opp_result"] == "timeout")
    buckets = [(0, 30), (30, 60), (60, 120), (120, 300), (300, 601)]
    tm["blunder_by_clock"] = []
    for lo, hi in buckets:
        v = [p for p in mine if p["clock"] is not None and lo <= p["clock"] < hi]
        if v:
            tm["blunder_by_clock"].append(dict(label=f"{lo}-{hi if hi < 601 else 600}s", moves=len(v),
                                               rate=round(sum(1 for p in v if p["loss"] >= 300) / len(v) * 100, 1)))
    sb = [(0, 3), (3, 10), (10, 30), (30, 60), (60, 9999)]
    tm["blunder_by_spent"] = []
    for lo, hi in sb:
        v = [p for p in mine if p["spent"] is not None and lo <= p["spent"] < hi]
        if v:
            tm["blunder_by_spent"].append(dict(label=f"{lo}-{hi}s" if hi < 9999 else f"{lo}s+", moves=len(v),
                                               rate=round(sum(1 for p in v if p["loss"] >= 300) / len(v) * 100, 1),
                                               accuracy=acc([p["wp_loss"] for p in v])))
    tm["long_thinks_opening"] = sum(1 for p in mine if p["spent"] is not None and p["spent"] >= 45 and p["move"] <= 10)
    tm["long_thinks_total"] = sum(1 for p in mine if p["spent"] is not None and p["spent"] >= 45)
    ahead, behind = [], []
    for g in games:
        s = g["summary"]
        if s.get("my_clock_20") is not None and s.get("opp_clock_20") is not None:
            (ahead if s["my_clock_20"] >= s["opp_clock_20"] else behind).append(g["outcome"])
    def score_of(v):
        c = Counter(v)
        return round((c["W"] + 0.5 * c["D"]) / len(v) * 100, 1) if v else None
    tm["ahead_at_20"] = dict(n=len(ahead), score=score_of(ahead))
    tm["behind_at_20"] = dict(n=len(behind), score=score_of(behind))
    tm["low_clock_games"] = dict(n=sum(1 for g in games if (g["summary"].get("my_final_clock") or 999) < 30),
                                 losses=sum(1 for g in games if (g["summary"].get("my_final_clock") or 999) < 30 and g["outcome"] == "L"))
    S["time"] = tm

    # --- 국면별
    S["phase"] = []
    for ph, label in (("opening", "오프닝(1-10수)"), ("middlegame", "중반전"), ("endgame", "엔드게임")):
        v = [p for p in mine if p["phase"] == ph]
        vo = [p for p in opp if p["phase"] == ph]
        if v:
            S["phase"].append(dict(phase=ph, label=label, moves=len(v), accuracy=acc([p["wp_loss"] for p in v]),
                                   opp_accuracy=acc([p["wp_loss"] for p in vo]),
                                   blunder_rate=round(sum(1 for p in v if p["loss"] >= 300) / len(v) * 100, 1)))
    S["blunder_by_move"] = []
    for lo in range(1, 61, 10):
        v = [p for p in mine if lo <= p["move"] < lo + 10]
        if len(v) >= 30:
            S["blunder_by_move"].append(dict(label=f"{lo}-{lo + 9}", moves=len(v),
                                             rate=round(sum(1 for p in v if p["loss"] >= 300) / len(v) * 100, 1)))

    # --- 역전 / 마무리
    conv = Counter(); recov = Counter()
    for g in games:
        s = g["summary"]
        if s.get("max_eval", 0) >= 300:
            conv[g["outcome"]] += 1
        if s.get("min_eval", 0) <= -300:
            recov[g["outcome"]] += 1
    S["conversion"] = dict(winning=dict(n=sum(conv.values()), won=conv["W"], lost=conv["L"], draw=conv["D"]),
                           losing=dict(n=sum(recov.values()), lost=recov["L"], won=recov["W"], draw=recov["D"]))

    # --- 전술
    hung = Counter(); hung_clock = Counter()
    pn = {2: "나이트", 3: "비숍", 4: "룩", 5: "퀸"}
    for g in games:
        pl = g["plies"]
        for i, p in enumerate(pl):
            if p["mine"] and p["loss"] >= 200:
                pt = opp_best_captures(p, pl[i + 1] if i + 1 < len(pl) else None)
                if pt:
                    hung[pn[pt]] += 1
                    hung_clock["<60s" if (p["clock"] or 999) < 60 else ">=60s"] += 1
    missed_free = sum(1 for p in mine if not p["is_best"] and p["loss"] >= 200 and p["best"] and "x" in p["best"])
    mm = Counter()
    for p in mine:
        if p["cp_before"] >= 9000 and p["cp_after"] < 9000:
            mm[min((10000 - p["cp_before"]) // 10, 5)] += 1
    S["tactics"] = dict(hung=dict(hung), hung_total=sum(hung.values()), hung_pg=round(sum(hung.values()) / n, 2),
                        hung_with_time=hung_clock[">=60s"], missed_free=missed_free,
                        missed_mate={str(k): v for k, v in sorted(mm.items())}, missed_mate_total=sum(mm.values()))

    # --- 오프닝
    S["openings"] = {}
    for c in "wb":
        d = defaultdict(list)
        for g in games:
            if g["my_color"] != c:
                continue
            key = " ".join(p["san"] for p in g["plies"][:4])
            d[key].append(g)
        rows = []
        for key, gs in d.items():
            if len(gs) < 3:
                continue
            cc = Counter(g["outcome"] for g in gs)
            early = [p for g in gs for p in g["plies"] if p["mine"] and p["move"] <= 15]
            names = Counter(g["eco_name"] for g in gs).most_common(1)[0][0]
            rows.append(dict(moves=key, name=names[:40], n=len(gs), win=cc["W"], draw=cc["D"], loss=cc["L"],
                             path=opening_path(gs, c), trouble=opening_trouble(gs, con, top=5), mist=opening_mistakes(gs),
                             score=round((cc["W"] + 0.5 * cc["D"]) / len(gs) * 100),
                             early_blunders=sum(1 for p in early if p["loss"] >= 300),
                             early_blunder_rate=round(sum(1 for p in early if p["loss"] >= 300) / max(1, len(early)) * 100, 1),
                             early_accuracy=acc([p["wp_loss"] for p in early])))
        rows.sort(key=lambda r: -r["n"])
        S["openings"][c] = rows[:8]

    # --- 월별
    bym = defaultdict(list)
    for g in games:
        bym[g["date"][:7]].append(g)
    S["monthly"] = []
    for m, gs in sorted(bym.items()):
        mp = [p for g in gs for p in g["plies"] if p["mine"]]
        cc = Counter(g["outcome"] for g in gs)
        S["monthly"].append(dict(month=m, games=len(gs), accuracy=acc([p["wp_loss"] for p in mp]),
                                 rating=gs[-1]["my_elo"], score=round((cc["W"] + 0.5 * cc["D"]) / len(gs) * 100),
                                 blunders_pg=round(sum(1 for p in mp if p["loss"] >= 300) / len(gs), 2)))

    # --- 틸트 / 세션, 레이팅 추이
    S["tilt"] = tilt_stats(games)
    S["rating_series"] = [[g["date"], g["my_elo"], g["outcome"]] for g in games]

    # --- 최근 게임 / 최악의 실수
    S["recent"] = []
    for g in games[-25:][::-1]:
        evals = [max(-1000, min(1000, p["cp_after"] if p["mine"] else -p["cp_after"])) for p in g["plies"]]
        S["recent"].append(dict(url=g["url"], date=g["date"], color=g["my_color"], opp=g["opp"], opp_elo=g["opp_elo"],
                                my_elo=g["my_elo"], outcome=g["outcome"], my_result=g["my_result"], opp_result=g["opp_result"],
                                eco_name=g["eco_name"][:35], evals=evals,
                                **{k: g["summary"].get(k) for k in ("accuracy", "blunders", "mistakes", "hung", "missed_mate",
                                                                    "my_final_clock", "opp_final_clock", "n_moves")},
                                cats=Counter(p["cat"] for p in g["plies"] if p.get("cat")).most_common(),
                                worst=with_lines(con, worst_with_cat(g))))
    worst = []
    for g in games:
        for p in g["plies"]:
            if p["mine"] and p["wp_loss"] >= 30:
                worst.append(mistake_rec(g, p))
    worst.sort(key=lambda w: (-w["wp_loss"], w["date"]))
    S["worst"] = [with_lines(con, w) for w in worst[:15]]
    # 유형별 대표 실수 (기물 방치 / 외통 놓침 / 유리한 판 붕괴) 각 5개
    S["examples"] = dict(hung=[], missed_mate=[], collapse=[])
    for g in games[::-1]:
        pl = g["plies"]
        for i, p in enumerate(pl):
            if not p["mine"]:
                continue
            base = mistake_rec(g, p)
            if len(S["examples"]["missed_mate"]) < 5 and p["cp_before"] >= 9970 and p["cp_after"] < 9000:
                S["examples"]["missed_mate"].append(base)
            elif len(S["examples"]["hung"]) < 5 and p["loss"] >= 300 and (p["clock"] or 999) >= 60 and \
                    opp_best_captures(p, pl[i + 1] if i + 1 < len(pl) else None) in (2, 3, 4, 5):
                S["examples"]["hung"].append(base)
            elif len(S["examples"]["collapse"]) < 5 and p["cp_before"] >= 300 and p["cp_after"] <= -100:
                S["examples"]["collapse"].append(base)
    for k in S["examples"]:
        S["examples"][k] = [with_lines(con, w) for w in S["examples"][k]]
    S["coach"] = coach_stats(games, con)
    S["repertoire"] = repertoire_stats(games, con)
    S["weaknesses"] = weaknesses(S, games)
    return S


def mistake_rec(g, p):
    """실수 한 수의 표시용 레코드 (뷰어·목록 공용). cat 은 실수 유형 키 (승률 손해가 작으면 없음)."""
    return dict(url=g["url"], date=g["date"], opp=g["opp"], color=g["my_color"], move=p["move"], mover=p["mover"], ply=p["ply"],
                san=p["san"], best=p["best"], cp_before=p["cp_before"], cp_after=p["cp_after"], wp_loss=p["wp_loss"],
                clock=p["clock"], spent=p["spent"], phase=p["phase"], fen=p["fen"], cat=p.get("cat"))


def worst_with_cat(g):
    """요약에 저장된 '가장 아픈 수'에 그 수의 실수 유형을 붙인다."""
    w = g["summary"].get("worst")
    if not w:
        return w
    p = next((p for p in g["plies"] if p["mine"] and p["move"] == w["move"] and p["san"] == w["san"]), None)
    return dict(w, cat=p.get("cat") if p else None)


def _share(part, whole):
    return round(len(part) / len(whole) * 100) if whole else None


def coach_stats(games, con=None, n_examples=5):
    """실수 유형별 집계: 얼마나 자주, 얼마나 비싸게, 어떤 상황에서, 최근에도 나오는지.
    cost 는 그 유형으로 잃은 승률(%p)의 합이고, cats 는 cost 가 큰 순서다. focus 는 가장 비싼 3가지."""
    n_games = len(games)
    per = defaultdict(list)                       # 유형 → [(게임 순번, 수)]
    for gi, g in enumerate(games):
        for p in g["plies"]:
            if p.get("cat"):
                per[p["cat"]].append((gi, p))
    total_n = sum(len(v) for v in per.values())
    total_cost = sum(p["wp_loss"] for v in per.values() for _, p in v)
    K = min(10, n_games)
    cats = []
    for key in CAT_KEYS:
        lst = per.get(key)
        if not lst:
            continue
        ps = [p for _, p in lst]
        by_game = Counter(gi for gi, _ in lst)
        cost = sum(p["wp_loss"] for p in ps)
        clocked = [p for p in ps if p["clock"] is not None]
        timed = [p for p in clocked if p["spent"] is not None]
        seq = [by_game.get(gi, 0) for gi in range(n_games - K, n_games)]
        newest = sorted(lst, key=lambda x: (-x[0], -x[1]["wp_loss"]))[:n_examples]
        cats.append(dict(
            key=key, n=len(ps), games=len(by_game), game_rate=round(len(by_game) / n_games * 100), per_game=round(len(ps) / n_games, 2),
            cost=round(cost), share=round(cost / total_cost * 100, 1), avg=round(cost / len(ps), 1),
            ctx=dict(calm=_share([p for p in clocked if p["clock"] >= 60], clocked),          # 시간이 1분 이상 남았을 때
                     low_clock=_share([p for p in clocked if p["clock"] < 30], clocked),      # 30초 미만
                     fast=_share([p for p in timed if p["spent"] < 5 and p["clock"] >= 60], timed),   # 여유가 있는데 5초 안에 둠
                     slow=_share([p for p in timed if p["spent"] >= 30], timed),              # 30초 넘게 생각하고도
                     winning=_share([p for p in ps if p["cp_before"] >= 300], ps),            # +3 이상 유리하던 국면
                     spent_median=median([p["spent"] for p in timed]),
                     phase={ph: sum(1 for p in ps if p["phase"] == ph) for ph in ("opening", "middlegame", "endgame")}),
            recent=dict(k=K, games=sum(1 for x in seq if x), n=sum(seq), seq=seq),
            trend=trend_analysis(metric_series(games, "cat", key), "cat"),
            examples=[with_lines(con, mistake_rec(games[gi], p)) for gi, p in newest]))
    cats.sort(key=lambda c: -c["cost"])
    early = [p for g in games for p in g["plies"] if p.get("cat") and p["move"] <= EARLY_MOVES]
    ec = Counter(p["cat"] for p in early)
    by_color = {}
    for c in "wb":
        gs = [g for g in games if g["my_color"] == c]
        by_color[c] = round(sum(1 for g in gs for p in g["plies"] if p.get("cat") and p["move"] <= EARLY_MOVES) / len(gs), 2) if gs else None
    return dict(n=total_n, games=n_games, per_game=round(total_n / n_games, 2), cost=round(total_cost), k=K,
                threshold=MISTAKE_WP, early_moves=EARLY_MOVES,
                cats=cats, focus=[c["key"] for c in cats if c["n"] >= 3][:3],
                early=dict(n=len(early), per_game=round(len(early) / n_games, 2), per_game_by_color=by_color,
                           cats=[dict(key=k, n=v, cost=round(sum(p["wp_loss"] for p in early if p["cat"] == k))) for k, v in ec.most_common()]))


# ---------------------------------------------------------------- 오프닝 성적표 (내가 고른 수순 / 상대가 고른 수순)
OPENING_KO = (("Italian Game", "이탈리안 게임"), ("Giuoco Piano", "이탈리안 게임"), ("Four Knights", "포 나이츠 게임"), ("Three Knights", "쓰리 나이츠"),
              ("Scotch", "스카치 게임"), ("Ruy Lopez", "루이 로페즈"), ("Philidor", "필리도르 디펜스"), ("Petrov", "페트로프 디펜스"),
              ("Sicilian", "시실리안 디펜스"), ("Caro Kann", "카로칸 디펜스"), ("French", "프렌치 디펜스"), ("Scandinavian", "스칸디나비안 디펜스"),
              ("Alekhine", "알레힌 디펜스"), ("Pirc", "피르츠 디펜스"), ("Modern Defense", "모던 디펜스"), ("Vienna", "비엔나 게임"),
              ("Bishops Opening", "비숍 오프닝"), ("Kings Gambit", "킹스 갬빗"), ("Center Game", "센터 게임"), ("Ponziani", "폰지아니"),
              ("Queens Gambit", "퀸스 갬빗"), ("London", "런던 시스템"), ("Slav", "슬라브 디펜스"), ("Kings Indian", "킹스 인디언"),
              ("Nimzowitsch", "님조비치 디펜스"), ("Englund", "잉글런드 갬빗"), ("English", "잉글리시 오프닝"), ("Queens Pawn", "퀸스 폰 오프닝"),
              ("Kings Pawn", "킹스 폰 오프닝"), ("Dutch", "더치 디펜스"), ("Owen", "오언 디펜스"))


def opening_name_ko(eco_name):
    for en, ko in OPENING_KO:
        if en in (eco_name or ""):
            return ko
    return " ".join((eco_name or "").split()[:3])


def _side_key(g, me, k):
    """한쪽이 둔 처음 k수 (me=True 면 내 수, False 면 상대 수)."""
    return tuple(p["san"] for p in g["plies"] if bool(p["mine"]) == me)[:k]


def _key_label(key, white):
    return " ".join(f"{i + 1}.{m}" if white else f"{i + 1}…{m}" for i, m in enumerate(key))


def repertoire_groups(gs, me, white, min_n):
    """같은 색 게임들을 한쪽의 첫 수들로 묶는다. 백의 수는 3수, 흑의 수는 2수까지 보고,
    판 수가 min_n 에 못 미치는 갈래는 한 수 짧은 묶음('그 외')으로 합친다."""
    left, out = list(gs), []
    for k in range(3 if white else 2, 0, -1):
        d = defaultdict(list)
        for g in left:
            key = _side_key(g, me, k)
            if len(key) == k:
                d[key].append(g)
        for key, v in d.items():
            if len(v) >= min_n:
                out.append((key, v, k < (3 if white else 2)))
        taken = {id(g) for _, v, _ in out for g in v}
        left = [g for g in left if id(g) not in taken]
    return out


def _eval_at(g, move):
    """내 move 번째 수를 둔 뒤의 평가 (내 기준 cp). 그 전에 끝난 판은 None."""
    p = next((p for p in g["plies"] if p["mine"] and p["move"] == move), None)
    return max(-1000, min(1000, p["cp_after"])) if p else None


def _clock_at(g, move):
    p = next((p for p in g["plies"] if p["mine"] and p["move"] == move), None)
    return p["clock"] if p else None


def _mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def repertoire_id(c, side, key):
    return f"{c}-{side}-{'_'.join(key)}"


def repertoire_row(key, gs, rest, base, con, white, me, other, rid=None):
    cc = Counter(g["outcome"] for g in gs)
    n = len(gs)
    score = round((cc["W"] + 0.5 * cc["D"]) / n * 100, 1)
    ev = evidence([POINTS[g["outcome"]] for g in gs], [POINTS[g["outcome"]] for g in rest]) if rest else dict(n=n, unit="판", p=None, confident=False)
    diff = round(score - base["score"], 1)
    verdict = "even"
    if abs(diff) >= 8:                                   # 8판 미만이거나 검정을 통과하지 못하면 '조짐'
        verdict = ("weak" if diff < 0 else "strong") + ("" if ev["confident"] and n >= 8 else "_hint")
    e15 = _mean([_eval_at(g, EARLY_MOVES) for g in gs])
    c15 = _mean([_clock_at(g, EARLY_MOVES) for g in gs])
    early = [p for g in gs for p in g["plies"] if p["mine"] and p["move"] <= EARLY_MOVES]
    ahead = [g["outcome"] for g in gs if (_eval_at(g, EARLY_MOVES) or 0) >= 100]
    behind = [g["outcome"] for g in gs if (_eval_at(g, EARLY_MOVES) or 0) <= -100]
    # 진 판에서 승부를 가른 수(가장 큰 승률 손해)가 언제, 어떤 유형이었나
    losses = [g for g in gs if g["outcome"] == "L"]
    dec = [max((p for p in g["plies"] if p["mine"]), key=lambda p: p["wp_loss"], default=None) for g in losses]
    dec = [p for p in dec if p and p["wp_loss"] >= MISTAKE_WP]
    recent_l = sorted(losses, key=lambda g: -g["end_time"])[:3]
    return dict(
        id=rid, key=_key_label(key, white), other=other, name=opening_name_ko(Counter(g["eco_name"] for g in gs).most_common(1)[0][0]),
        n=n, win=cc["W"], draw=cc["D"], loss=cc["L"], score=score, diff=diff, verdict=verdict, ev=ev,
        eval15=round(e15) if e15 is not None else None, clock15=round(c15) if c15 is not None else None,
        acc15=acc([p["wp_loss"] for p in early]),
        ahead=dict(n=len(ahead), score=_score(ahead)), behind=dict(n=len(behind), score=_score(behind)),
        decisive=dict(n=len(dec), early=sum(1 for p in dec if p["move"] <= EARLY_MOVES),
                      cats=Counter(p["cat"] for p in dec if p.get("cat")).most_common(3)),
        mist=opening_mistakes(gs), trouble=opening_trouble(gs, con, top=3),
        review=[dict(url=g["url"], date=g["date"], opp=g["opp"], accuracy=g["summary"].get("accuracy")) for g in recent_l])


def repertoire_stats(games, con=None):
    """색마다 두 갈래의 오프닝 성적표: mine = 내가 고른 수순(내 첫 수들), opp = 상대가 고른 수순(상대 첫 수들).
    각 묶음에 승률, 같은 색 나머지 판과의 차이와 검정, 15수 시점 형세·시계, 15수 안 실수 프로필, 반복 실수, 패배의 결정적 실수를 붙인다."""
    out = {}
    min_n = 5 if len(games) >= 60 else 3
    for c in "wb":
        gs = [g for g in games if g["my_color"] == c]
        if not gs:
            out[c] = dict(base=None, mine=[], opp=[])
            continue
        base = dict(n=len(gs), score=_score([g["outcome"] for g in gs]),
                    eval15=(lambda v: round(v) if v is not None else None)(_mean([_eval_at(g, EARLY_MOVES) for g in gs])),
                    clock15=(lambda v: round(v) if v is not None else None)(_mean([_clock_at(g, EARLY_MOVES) for g in gs])),
                    acc15=acc([p["wp_loss"] for g in gs for p in g["plies"] if p["mine"] and p["move"] <= EARLY_MOVES]),
                    mist_pg=round(sum(1 for g in gs for p in g["plies"] if p.get("cat") and p["move"] <= EARLY_MOVES) / len(gs), 2))
        out[c] = dict(base=base)
        for side, me in (("mine", True), ("opp", False)):
            white = (c == "w") == me                      # 이 갈래의 수를 두는 쪽이 백인가
            rows = []
            for key, v, other in repertoire_groups(gs, me, white, min_n):
                ids = {id(g) for g in v}
                rows.append(repertoire_row(key, v, [g for g in gs if id(g) not in ids], base, con, white, me, other,
                                           repertoire_id(c, side, key)))
            rows.sort(key=lambda r: -r["n"])
            out[c][side] = rows
    return out


# ---------------------------------------------------------------- 오프닝 연습 라인 (docs/book.json, train.html 이 읽는다)
# 오프닝 묶음마다 내 15수째까지의 라인을 몇 개 만든다.
#   상대의 수: 그 묶음의 내 게임에서 그 국면에 가장 자주 나온 수 (메인라인). 둘째·셋째로 잦은 수는 갈래 라인이 된다.
#              게임에 없는 국면부터는 엔진의 최선 수.
#   내 수:     평소 두던 수가 엔진 최선과 승률 차이 ALT_WP 안이면 그 수를 그대로 가르치고, 아니면 엔진 최선으로 바꾼다
#              (그 자리에는 "평소 X 를 뒀다"는 표시가 붙는다).
# 엔진 평가는 book 테이블에 국면별로 쌓아 두므로, 게임이 늘어 라인이 바뀌어도 새 국면만 계산한다.
def book_eval(con, fen, eng, budget):
    """국면의 상위 3수 [{san, uci, cp, reply}]. 캐시에 없고 엔진·예산도 없으면 None."""
    r = con.execute("SELECT data FROM book WHERE fen=? AND depth=?", (fen, BOOK_DEPTH)).fetchone()
    if r:
        return json.loads(r[0])
    if eng is None or budget[0] <= 0:
        return None
    budget[0] -= 1
    b = chess.Board(fen)
    infos = eng.analyse(b, chess.engine.Limit(depth=BOOK_DEPTH), multipv=3)
    data = [dict(san=b.san(i["pv"][0]), uci=i["pv"][0].uci(), cp=cp_of(i["score"], b.turn),
                 reply=(lambda b2, pv: b2.san(pv[1]) if len(pv) > 1 and (b2.push(pv[0]) or True) else None)(b.copy(), i["pv"]))
            for i in infos if i.get("pv")]
    con.execute("INSERT OR REPLACE INTO book(fen,depth,data) VALUES(?,?,?)", (fen, BOOK_DEPTH, json.dumps(data, separators=(",", ":"))))
    return data


def _position_index(gs):
    """국면 → 그 국면에서 내가 둔 수(횟수·승률 손해)와 상대가 둔 수(횟수). 15수째까지만."""
    idx = defaultdict(lambda: dict(mine=Counter(), loss=defaultdict(list), opp=Counter()))
    for g in gs:
        for p in g["plies"]:
            if p["move"] > EARLY_MOVES:
                break
            e = idx[p["fen"]]
            if p["mine"]:
                e["mine"][p["san"]] += 1
                e["loss"][p["san"]].append(p["wp_loss"])
            else:
                e["opp"][p["san"]] += 1
    return idx


def book_line(con, eng, budget, c, key, key_mine, grp_idx, all_idx, alt=None):
    """라인 하나. alt=(수 순번, san) 이면 그 자리에서 상대가 그 수를 두는 갈래.
    (수 목록, 메인라인에서 갈라질 수 있는 상대 수 [(횟수, 순번, san)], 끝까지 만들어졌는가) 를 돌려준다."""
    b = chess.Board()
    out, branches, my_n, reply, complete = [], [], 0, None, True
    while my_n < EARLY_MOVES and not b.is_game_over():
        mine = (b.turn == chess.WHITE) == (c == "w")
        fen, i, kidx = b.fen(), len(out), b.fullmove_number - 1
        node = dict(mine=int(mine))
        if mine == key_mine and kidx < len(key):
            san = key[kidx]                                   # 이 오프닝을 정의하는 수
        elif not mine:
            cands = [(s, n) for s, n in grp_idx[fen]["opp"].most_common() if n >= 2] if fen in grp_idx else []
            if alt and alt[0] == i:
                san = alt[1]
                node["n"] = dict(cands).get(san)
            elif cands:
                san, node["n"] = cands[0]
                branches += [(n, i, s) for s, n in cands[1:3]]
            elif reply:
                san, node["eng"] = reply, 1                    # 게임에 없는 국면: 엔진이 예상한 응수
            else:
                ev = book_eval(con, fen, eng, budget)
                if not ev:
                    complete = False
                    break
                san, node["eng"] = ev[0]["san"], 1
        else:
            ev = book_eval(con, fen, eng, budget)
            if not ev:
                complete = False
                break
            ok = [e for e in ev if winpct(ev[0]["cp"]) - winpct(e["cp"]) <= ALT_WP]
            san, node["cp"] = ev[0]["san"], ev[0]["cp"]
            e = grp_idx[fen] if fen in grp_idx and grp_idx[fen]["mine"] else all_idx.get(fen)   # 이 오프닝의 판이 먼저, 없으면 같은 색 전체
            if e and e["mine"]:
                us, un = e["mine"].most_common(1)[0]
                avg = sum(e["loss"][us]) / len(e["loss"][us])
                hit = next((x for x in ok if x["san"] == us), None)
                if hit or avg <= ALT_WP:                      # 평소 두던 수가 충분히 좋으면 그 수로 가르친다
                    san, node["mineN"] = us, un
                    if hit:
                        node["cp"] = hit["cp"]
                elif un >= 2 or avg >= MISTAKE_WP:            # 평소 두던 수가 나쁘다: 고칠 자리
                    node["bad"] = dict(san=us, uci=uci_of(fen, us), n=un, loss=round(avg, 1))
            node["ok"] = [dict(san=x["san"], uci=x["uci"]) for x in ok if x["san"] != san]
            reply = next((x.get("reply") for x in ev if x["san"] == san), None)
        try:
            mv = b.parse_san(san)
        except Exception:                                     # 이 진행에서는 둘 수 없는 수: 라인을 여기서 끝낸다
            break
        node.update(san=san, uci=mv.uci(), move=b.fullmove_number, mover="w" if b.turn == chess.WHITE else "b")
        b.push(mv)
        node["fen"] = b.fen()
        out.append(node)
        if mine:
            my_n += 1
        else:
            reply = None
    return out, branches, complete


def book_targets(games):
    """연습 라인을 만들 오프닝 묶음 (전체 기간 기준). 취약한 것부터."""
    rep = repertoire_stats(games)
    min_n = 5 if len(games) >= 60 else 3
    out = []
    for c in "wb":
        gs = [g for g in games if g["my_color"] == c]
        for side, me in (("mine", True), ("opp", False)):
            white = (c == "w") == me
            groups = {repertoire_id(c, side, key): (key, v) for key, v, other in repertoire_groups(gs, me, white, min_n) if not other}
            for r in rep[c][side]:
                if r["id"] in groups and (r["n"] >= BOOK_MIN_N or r["verdict"].startswith("weak")):
                    key, v = groups[r["id"]]
                    out.append(dict(row=r, c=c, side=side, me=me, key=key, gs=v, all=gs))
    out.sort(key=lambda t: (not t["row"]["verdict"].startswith("weak"), -t["row"]["n"]))
    return out


def build_book(con, games, eng=None, limit=0):
    """오프닝 연습 라인을 만든다. eng 가 있으면 캐시에 없는 국면을 limit 개까지 평가한다.
    ({id: 오프닝}, 새로 평가한 국면 수, 아직 덜 만들어진 오프닝 수) 를 돌려준다. 덜 만들어진 오프닝은 결과에서 뺀다."""
    budget = [limit]
    book, pending, idx_cache = {}, 0, {}
    for t in book_targets(games):
        c, r = t["c"], t["row"]
        if c not in idx_cache:
            idx_cache[c] = _position_index(t["all"])
        grp_idx = _position_index(t["gs"])
        args = (con, eng, budget, c, t["key"], t["me"], grp_idx, idx_cache[c])
        main, branches, ok = book_line(*args)
        lines = [dict(name="메인라인", note="내 게임에서 상대가 가장 자주 둔 수로 진행", plies=main)]
        seen = set()
        for n, i, san in sorted(branches, key=lambda x: (-x[0], x[1])):
            if len(lines) >= BOOK_LINES or (i, san) in seen:
                continue
            seen.add((i, san))
            pl, _, ok2 = book_line(*args, alt=(i, san))
            ok = ok and ok2
            at = pl[i] if i < len(pl) else None
            if at:
                lines.append(dict(name=f"{at['move']}{'.' if at['mover'] == 'w' else '…'}{san} 갈래", note=f"상대가 {at['move']}수째에 {san} 로 나올 때 (내 게임 {n}판)",
                                  at=i, plies=pl))
        if not ok:
            pending += 1
            continue
        lines = [ln for ln in lines if sum(p["mine"] for p in ln["plies"]) >= 6]      # 너무 일찍 끝난 라인은 뺀다
        if not lines:
            continue
        for ln in lines:
            last = next((p for p in reversed(ln["plies"]) if p.get("cp") is not None), None)
            ln["cp"] = last["cp"] if last else None
            ln["fix"] = sum(1 for p in ln["plies"] if p.get("bad"))
        book[r["id"]] = dict(id=r["id"], key=r["key"], color=c, side=t["side"], name=r["name"], n=r["n"], score=r["score"],
                             verdict=r["verdict"], lines=lines)
    con.commit()
    return book, limit - budget[0], pending


def enrich_book(con, cfg, limit=BOOK_BATCH):
    """오프닝 연습 라인에 필요한 국면을 엔진으로 평가해 book 테이블에 쌓는다. (평가한 국면 수, 덜 만들어진 오프닝 수)"""
    games = load_games(con)
    if not games:
        return 0, 0
    _, _, pending = build_book(con, games)
    if not pending:
        return 0, 0
    eng = chess.engine.SimpleEngine.popen_uci(stockfish_path(cfg))
    eng.configure({"Hash": 128, "Threads": WORKERS})
    try:
        _, n, pending = build_book(con, games, eng, limit)
    finally:
        eng.quit()
    log(f"오프닝 연습 라인: 국면 {n}개 평가 (덜 만들어진 오프닝 {pending}개, depth {BOOK_DEPTH})")
    return n, pending


def opening_mistakes(gs):
    """같은 오프닝 게임들의 15수 안 실수 프로필: 판당 횟수, 처음 틀어지는 수, 수별 분포, 유형별 횟수."""
    ms = [p for g in gs for p in g["plies"] if p.get("cat") and p["move"] <= EARLY_MOVES]
    first = [min(m) for m in ([p["move"] for p in g["plies"] if p.get("cat") and p["move"] <= EARLY_MOVES] for g in gs) if m]
    cnt = Counter(p["cat"] for p in ms)
    return dict(n=len(ms), per_game=round(len(ms) / len(gs), 2), clean=len(gs) - len(first), first_slip=median(first),
                by_move=[sum(1 for p in ms if p["move"] == m) for m in range(1, EARLY_MOVES + 1)],
                cats=[dict(key=k, n=v, cost=round(sum(p["wp_loss"] for p in ms if p["cat"] == k))) for k, v in cnt.most_common()])


def opening_path(gs, my_color, start=4, max_plies=16, min_n=3):
    """같은 첫 4수를 둔 게임들에서 가장 흔한 진행을 따라가며 수마다 통계를 붙인다."""
    path = []
    fen0 = gs[0]["plies"][start - 1]["fen"] if len(gs[0]["plies"]) >= start else None
    # 시작 국면(4수 뒤)
    b = chess.Board()
    for p in gs[0]["plies"][:start]:
        b.push_san(p["san"])
    path.append(dict(san=None, fen=b.fen(), n=len(gs), score=None, mine=None))
    cur = gs
    for k in range(start, max_plies):
        cands = Counter(g["plies"][k]["san"] for g in cur if len(g["plies"]) > k)
        if not cands:
            break
        san, n = cands.most_common(1)[0]
        if n < min_n:
            break
        nxt = [g for g in cur if len(g["plies"]) > k and g["plies"][k]["san"] == san]
        ply = nxt[0]["plies"][k]
        mine = bool(ply["mine"])
        cc = Counter(g["outcome"] for g in nxt)
        step = dict(san=san, uci=ply["uci"] if ply.get("uci") else uci_of(ply["fen"], san), n=n,
                    score=round((cc["W"] + 0.5 * cc["D"]) / n * 100), mine=mine, move=ply["move"], mover=ply["mover"])
        b2 = chess.Board(ply["fen"])
        b2.push_san(san)
        step["fen"] = b2.fen()
        if mine:
            losses = [g["plies"][k]["loss"] for g in nxt]
            step["avg_loss"] = round(sum(losses) / len(losses))
            bests = Counter(g["plies"][k]["best"] for g in nxt if g["plies"][k]["best"])
            if bests:
                bsan = bests.most_common(1)[0][0]
                step["best"] = bsan
                step["best_uci"] = uci_of(ply["fen"], bsan)
            step["problem"] = bool(step["avg_loss"] >= 40 and step.get("best") and step["best"] != san)
            # 이 국면에서 내가 둔 다른 수들 (대안)
            alts = Counter(g["plies"][k]["san"] for g in cur if len(g["plies"]) > k)
            step["alts"] = [dict(san=a, n=c) for a, c in alts.most_common(4) if a != san]
        path.append(step)
        cur = nxt
    return path


def opening_trouble(gs, con, max_move=15, top=3):
    """같은 오프닝 게임들에서 같은 국면에서 같은 수를 2번 이상 두었고 평균 손실이 큰 내 수 (반복 실수)."""
    by_key = defaultdict(list)
    for g in gs:
        for p in g["plies"]:
            if p["mine"] and p["move"] <= max_move and p["best"] and p["best"] != p["san"]:
                by_key[(p["fen"], p["san"])].append((p, g))
    out = []
    for (fen, san), lst in by_key.items():
        if len(lst) < 2:
            continue
        avg = sum(p["loss"] for p, _ in lst) / len(lst)
        if avg < 60:
            continue
        best = (common_best(con, fen, san) if con else None) or Counter(p["best"] for p, _ in lst).most_common(1)[0][0]
        p0, g0 = max(lst, key=lambda x: x[1]["end_time"])  # 가장 최근 예
        w = dict(url=g0["url"], date=g0["date"], opp=g0["opp"], color=g0["my_color"], move=p0["move"], mover=p0["mover"],
                 san=san, best=best, cp_before=p0["cp_before"], cp_after=p0["cp_after"], wp_loss=p0["wp_loss"],
                 clock=p0["clock"], spent=p0["spent"], phase=p0["phase"], fen=fen, n=len(lst), avg_loss=round(avg),
                 uci=uci_of(fen, san), best_uci=uci_of(fen, best), ply=p0["ply"],
                 cat=Counter(p.get("cat") for p, _ in lst if p.get("cat")).most_common(1)[0][0] if any(p.get("cat") for p, _ in lst) else None)
        w.update(cached_lines(con, fen, san, best) if con else dict(best_line=[], refutation=[], alts=[]))
        try:
            b = chess.Board(fen); b.push_san(san); w["after_fen"] = b.fen()
        except Exception:
            w["after_fen"] = None
        out.append(w)
    out.sort(key=lambda w: -(w["n"] * w["avg_loss"]))
    return out[:top]


def fmt_clock(s):
    if s is None:
        return "-"
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"



# ---------------------------------------------------------------- 보완점 추이 통계 (scipy 없이 순수 파이썬)
def _betacf(a, b, x):
    FPMIN = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1.0 - qab * x / qap
    d = FPMIN if abs(d) < FPMIN else d
    d = 1 / d; h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1 + aa / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = FPMIN if abs(d) < FPMIN else d
        c = 1 + aa / c; c = FPMIN if abs(c) < FPMIN else c
        d = 1 / d; delta = d * c; h *= delta
        if abs(delta - 1) < 3e-14:
            break
    return h


def betainc(a, b, x):
    """정규화 불완전 베타 함수 I_x(a,b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def t_pvalue(t, df):
    """양측 t 검정 p값."""
    if df <= 0:
        return None
    return betainc(df / 2, 0.5, df / (df + t * t))


def welch_p(a, b):
    """두 표본 평균 차이 (Welch t 검정) p값."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se2 = va / na + vb / nb
    if se2 == 0:
        return 1.0 if ma == mb else 0.0
    t = (mb - ma) / math.sqrt(se2)
    df = se2 ** 2 / (((va / na) ** 2) / (na - 1) + ((vb / nb) ** 2) / (nb - 1))
    return t_pvalue(t, max(1.0, df))


def prop_p(x1, n1, x2, n2):
    """두 비율 차이 z 검정 p값."""
    if n1 == 0 or n2 == 0:
        return None
    pp = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (x2 / n2 - x1 / n1) / se
    return math.erfc(abs(z) / math.sqrt(2))


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs, ys):
    """스피어만 순위 상관 (rho, p). 게임 순서 대비 지표의 완만한 추세용."""
    n = len(xs)
    if n < 8:
        return None, None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx); syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return 0.0, 1.0
    rho = sxy / math.sqrt(sxx * syy)
    if abs(rho) >= 1:
        return rho, 0.0
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return rho, t_pvalue(t, n - 2)


METRICS = {
    # key: (지표 이름, 표시 형식, 낮을수록 좋은가, 비율형인가)
    "clock20": ("20수 시점 상대보다 뒤진 시간", "clock", True, False),
    "long_think_opening": ("1~10수 45초 이상 장고 (판당)", "num1", True, False),
    "blunder_low_clock": ("남은 시간 30초 미만일 때 대실수율", "pct", True, True),
    "conversion": ("+3 이상 유리했던 판의 패배율", "pct", True, True),
    "hung": ("기물 방치 (판당)", "num2", True, False),
    "missed_mate": ("외통 놓침 (판당)", "num2", True, False),
    "opening": ("이 오프닝 승률", "pct", False, True),
    "endgame_acc": ("엔드게임 정확도", "pct100", False, False),
    "tilt": ("같은 세션 2연패 직후 판의 승률", "pct", False, True),
    "late_session": ("세션 6판째 이후 판의 승률", "pct", False, True),
    "cat": ("이 유형의 실수 (판당 횟수)", "num2", True, False),      # arg = 실수 유형 키 (없으면 모든 유형)
}


def metric_series(games, key, arg=None):
    """보완점 지표를 게임 단위 시계열 [{d: 날짜, v: 분자, n: 분모}] 로."""
    out = []
    ctx = session_context(games) if key in ("tilt", "late_session") else {}
    for g in games:
        s = g["summary"]; mine = [p for p in g["plies"] if p["mine"]]
        if key in ("tilt", "late_session"):
            c = ctx[g["url"]]
            if (key == "tilt" and c["streak"] < 2) or (key == "late_session" and c["pos"] < 6):
                continue
            v, n = {"W": 1, "D": 0.5, "L": 0}[g["outcome"]], 1
        elif key == "clock20":
            if s.get("my_clock_20") is None or s.get("opp_clock_20") is None:
                continue
            v, n = s["opp_clock_20"] - s["my_clock_20"], 1
        elif key == "long_think_opening":
            v, n = sum(1 for p in mine if p["spent"] is not None and p["spent"] >= 45 and p["move"] <= 10), 1
        elif key == "blunder_low_clock":
            low = [p for p in mine if p["clock"] is not None and p["clock"] < 30]
            if not low:
                continue
            v, n = sum(1 for p in low if p["loss"] >= 300), len(low)
        elif key == "conversion":
            if s.get("max_eval", 0) < 300:
                continue
            v, n = (1 if g["outcome"] == "L" else 0), 1
        elif key == "hung":
            v, n = s.get("hung", 0), 1
        elif key == "missed_mate":
            v, n = s.get("missed_mate", 0), 1
        elif key == "opening":
            color, moves = arg
            if g["my_color"] != color or " ".join(p["san"] for p in g["plies"][:4]) != moves:
                continue
            v, n = {"W": 1, "D": 0.5, "L": 0}[g["outcome"]], 1
        elif key == "cat":
            v, n = sum(1 for p in mine if p.get("cat") and (arg is None or p["cat"] == arg)), 1
        elif key == "endgame_acc":
            e = [p["wp_loss"] for p in mine if p["phase"] == "endgame"]
            if len(e) < 5:
                continue
            v, n = acc(e), 1
        else:
            continue
        out.append(dict(d=g["date"], v=v, n=n))
    return out


def trend_analysis(series, key):
    """최근 구간 vs 이전 구간 비교 + 전체 기간 순위 상관 + 기간별 버킷."""
    label, fmt, lower_better, is_rate = METRICS[key]
    N = len(series)
    res = dict(label=label, fmt=fmt, lower_better=lower_better, rate=is_rate, n=N,
               series=[[s["d"], s["v"], s["n"]] for s in series])
    if N < 10:
        res["status"] = "insufficient"
        return res
    K = 30 if N >= 60 else max(5, N // 3)
    before, recent = series[:-K], series[-K:]
    def agg(ss):
        return sum(x["v"] for x in ss) / sum(x["n"] for x in ss)
    vb, vr = agg(before), agg(recent)
    if is_rate:
        p = prop_p(sum(x["v"] for x in before), sum(x["n"] for x in before),
                   sum(x["v"] for x in recent), sum(x["n"] for x in recent))
    else:
        p = welch_p([x["v"] for x in before], [x["v"] for x in recent])
    delta = vr - vb
    improved = (delta < 0) if lower_better else (delta > 0)
    if p is None or abs(delta) < 1e-9:
        status = "flat"
    elif p < 0.05:
        status = "better" if improved else "worse"
    elif p < 0.2:
        status = "maybe_better" if improved else "maybe_worse"
    else:
        status = "flat"
    rho, rp = spearman(list(range(N)), [x["v"] / x["n"] for x in series])
    d0, d1 = datetime.strptime(series[0]["d"], "%Y-%m-%d"), datetime.strptime(series[-1]["d"], "%Y-%m-%d")
    span = (d1 - d0).days
    def bucket_of(d):
        dt = datetime.strptime(d, "%Y-%m-%d")
        if span <= 21:
            return d[5:], d
        if span <= 200:
            mon = dt - timedelta(days=dt.weekday())
            return mon.strftime("%m-%d") + "~", mon.strftime("%Y-%m-%d")
        return d[:7], d[:7]
    bk = defaultdict(list)
    for x in series:
        bk[bucket_of(x["d"])].append(x)
    buckets = [dict(label=k[0], games=len(v), value=agg(v), n=sum(x["n"] for x in v))
               for k, v in sorted(bk.items(), key=lambda kv: kv[0][1])]
    res.update(status=status, k=K, n_before=len(before), n_recent=len(recent), v_before=vb, v_recent=vr, delta=delta, p=p,
               improved=improved, rho=rho, rho_p=rp, buckets=buckets,
               unit=("day" if span <= 21 else "week" if span <= 200 else "month"))
    return res


POINTS = {"W": 1.0, "D": 0.5, "L": 0.0}


def evidence(sub, rest, unit="판"):
    """비교형 보완점의 근거: sub(값 목록)의 평균이 rest 와 다른지 Welch t 검정.
    p<0.1 이면 근거 충분으로 보고, 아니면 카드를 '표본 부족'으로 낮춘다."""
    p = welch_p(rest, sub) if len(sub) >= 2 and len(rest) >= 2 else None
    return dict(n=len(sub), unit=unit, p=(round(p, 4) if p is not None else None), confident=bool(p is not None and p < 0.1))


def evidence_one(values, unit="판"):
    """값들의 평균이 0 과 다른지 (한 표본 t 검정)."""
    n = len(values)
    if n < 3:
        return dict(n=n, unit=unit, p=None, confident=False)
    m = sum(values) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    p = 0.0 if sd == 0 and m != 0 else (1.0 if sd == 0 else t_pvalue(m / (sd / math.sqrt(n)), n - 1))
    return dict(n=n, unit=unit, p=round(p, 4), confident=p < 0.1)


def weaknesses(S, games=None):
    """통계에서 규칙 기반으로 보완점 문장을 뽑는다. 각 항목에 key/arg를 붙여 추이 분석 지표와 연결한다.
    다른 집단과 비교해서 나온 항목은 ev(근거)를 붙이고, 근거가 약하면 level 을 hint 로 낮춘다."""
    out = []
    games = games or []
    mine_plies = [p for g in games for p in g["plies"] if p["mine"]]
    ctx = session_context(games) if games else {}
    tm, ov, cv, tc = S["time"], S["overview"], S["conversion"], S["tactics"]
    c20 = next((c for c in tm["clock_at"] if c["move"] == 20), None)
    if c20 and c20["me"] is not None and c20["opp"] is not None and c20["opp"] - c20["me"] >= 60:
        diffs = [g["summary"]["opp_clock_20"] - g["summary"]["my_clock_20"] for g in games
                 if g["summary"].get("my_clock_20") is not None and g["summary"].get("opp_clock_20") is not None]
        out.append(dict(level="critical", title="시간 관리", key="clock20", ev=evidence_one(diffs) if games else None,
                        text=f"20수 시점에 상대보다 평균 {fmt_clock(c20['opp'] - c20['me'])} 뒤처집니다. "
                             f"시간패 {tm['timeouts']}판(이기던 판 {tm['timeouts_winning']}). "
                             f"시간이 뒤진 채 20수를 맞은 판 승률 {tm['behind_at_20']['score']}%."))
    if tm["long_thinks_opening"] >= max(5, ov["games"] * 0.15):
        out.append(dict(level="serious", title="오프닝 장고", key="long_think_opening",
                        text=f"1~10수에서 45초 이상 고민한 수가 {tm['long_thinks_opening']}번입니다. "
                             "자주 두는 오프닝의 처음 8수는 외워서 10초 안에 두세요."))
    bc = {b["label"]: b["rate"] for b in tm["blunder_by_clock"]}
    if bc.get("0-30s") and bc.get("300-600s") and bc["0-30s"] >= 2 * bc["300-600s"]:
        low = [1.0 if p["loss"] >= 300 else 0.0 for p in mine_plies if p["clock"] is not None and p["clock"] < 30]
        calm = [1.0 if p["loss"] >= 300 else 0.0 for p in mine_plies if p["clock"] is not None and 300 <= p["clock"] < 601]
        out.append(dict(level="serious", title="시간 압박 실수", key="blunder_low_clock", ev=evidence(low, calm, "수") if games else None,
                        text=f"남은 시간 30초 미만일 때 대실수율 {bc['0-30s']}%로, 여유 있을 때({bc['300-600s']}%)의 "
                             f"{bc['0-30s'] / bc['300-600s']:.1f}배입니다."))
    w = cv["winning"]
    if w["n"] >= 10 and w["lost"] / w["n"] >= 0.2:
        out.append(dict(level="critical", title="유리한 판 마무리", key="conversion",
                        text=f"+3 이상 유리했던 {w['n']}판 중 {w['lost']}판을 졌습니다({w['lost'] / w['n'] * 100:.0f}%). "
                             "유리하면 기물을 교환해 단순화하고, 매 수 상대의 체크와 잡는 수부터 확인하세요."))
    if tc["hung_pg"] >= 0.7:
        out.append(dict(level="serious", title="기물 방치", key="hung",
                        text=f"상대가 그냥 잡을 수 있는 기물을 둔 수가 판당 {tc['hung_pg']}개입니다"
                             f"(총 {tc['hung_total']}, 그중 {tc['hung_with_time']}번은 시간이 1분 이상 남았을 때). "
                             "수를 두기 전에 '이 기물이 잡히나'만 확인하세요."))
    if tc["missed_mate_total"] >= 5:
        out.append(dict(level="warning", title="외통 놓침", key="missed_mate",
                        text=f"강제 외통이 있었는데 놓친 경우 {tc['missed_mate_total']}번"
                             f"(1수 외통 {tc['missed_mate'].get('1', 0)}번). 1~2수 외통 퍼즐이 가장 효율적입니다."))
    for c, name in (("w", "백"), ("b", "흑")):
        for o in S["openings"].get(c, []):
            if o["n"] >= 8 and o["score"] <= 42:
                same = [g for g in games if g["my_color"] == c]
                sub = [POINTS[g["outcome"]] for g in same if " ".join(p["san"] for p in g["plies"][:4]) == o["moves"]]
                rest = [POINTS[g["outcome"]] for g in same if " ".join(p["san"] for p in g["plies"][:4]) != o["moves"]]
                out.append(dict(level="warning", title=f"{name} 오프닝", key="opening", arg=[c, o["moves"]],
                                ev=evidence(sub, rest) if games else None,
                                text=f"{o['moves']} ({o['name']}) {o['n']}판 승률 {o['score']}%, "
                                     f"15수 안 대실수 {o['early_blunders']}회. 이 라인의 기본 계획을 하나 정해 두세요."))
    tl = S.get("tilt")
    if tl:
        s2 = next((x for x in tl["streak"] if x["label"] == "2연패 후"), None)
        s3 = next((x for x in tl["streak"] if x["label"] == "3연패 이상 후"), None)
        n2 = (s2["n"] if s2 else 0) + (s3["n"] if s3 else 0)
        if n2 >= 10:
            w2 = (s2["score"] * s2["n"] + s3["score"] * s3["n"]) / n2 if s2 and s3 else (s2 or s3)["score"]
            if w2 <= ov["score"] - 10:
                sub = [POINTS[g["outcome"]] for g in games if ctx[g["url"]]["streak"] >= 2]
                rest = [POINTS[g["outcome"]] for g in games if ctx[g["url"]]["streak"] < 2]
                out.append(dict(level="serious", title="연패 후 틸트", key="tilt", ev=evidence(sub, rest) if games else None,
                                text=f"같은 세션에서 2연패한 직후의 판은 승률 {w2:.0f}%로 평소({ov['score']}%)보다 크게 낮습니다({n2}판). "
                                     "2연패하면 그날은 멈추거나 최소 30분 쉬세요."))
        late = next((x for x in tl["session_pos"] if x["label"] == "6판째 이후"), None)
        if late and late["n"] >= 10 and late["score"] <= ov["score"] - 10:
            sub = [POINTS[g["outcome"]] for g in games if ctx[g["url"]]["pos"] >= 6]
            rest = [POINTS[g["outcome"]] for g in games if ctx[g["url"]]["pos"] < 6]
            out.append(dict(level="warning", title="긴 세션", key="late_session", ev=evidence(sub, rest) if games else None,
                            text=f"한 세션에서 6판째 이후의 승률이 {late['score']}%로 평소({ov['score']}%)보다 낮습니다({late['n']}판, 정확도 {late['accuracy']}%). "
                                 "세션을 5판 안팎으로 끊는 편이 좋습니다."))
    ph = {p["phase"]: p for p in S["phase"]}
    if "endgame" in ph and "middlegame" in ph and ph["endgame"]["accuracy"] - ph["middlegame"]["accuracy"] >= 4:
        eg = [p["wp_loss"] for p in mine_plies if p["phase"] == "endgame"]
        mg = [p["wp_loss"] for p in mine_plies if p["phase"] == "middlegame"]
        out.append(dict(level="good", title="엔드게임은 강점", key="endgame_acc", ev=evidence(eg, mg, "수") if games else None,
                        text=f"엔드게임 정확도 {ph['endgame']['accuracy']}%로 중반전({ph['middlegame']['accuracy']}%)보다 높습니다. "
                             "유리할 때 엔드게임으로 가는 전략이 유효합니다."))
    for w in out:
        ev = w.get("ev")
        if ev and not ev["confident"]:
            odds = f"100번 중 {max(1, round(ev['p'] * 100))}번꼴로" if ev["p"] is not None else "흔히"
            w["level"] = "hint"
            w["text"] += f" 다만 {ev['n']}{ev['unit']}뿐이라 아직 단정하기 어렵습니다. 실제 차이가 없어도 이 정도 격차는 {odds} 나옵니다."
        if w.get("ev") is None:
            w.pop("ev", None)
    out.sort(key=lambda w: w["level"] == "hint")   # 근거가 약한 항목은 뒤로 (안정 정렬)
    if games:
        for w in out:
            w["trend"] = trend_analysis(metric_series(games, w["key"], w.get("arg")), w["key"])
    return out


# ---------------------------------------------------------------- 게임 상세 JSON
def classify(p):
    if p["cp_before"] >= 9000 and p["cp_after"] < 9000:
        return "miss"
    if p["is_best"] or p["loss"] == 0:
        return "best"
    l = p["loss"]
    return "good" if l < 50 else "inacc" if l < 100 else "mist" if l < 300 else "blun"


def game_id(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def export_game(con, g):
    """게임 하나 → docs/games/<id>.json (game.html 이 읽는다)."""
    plies = g["plies"] if "plies" in g else [dict(r) for r in con.execute("SELECT * FROM plies WHERE url=? ORDER BY ply", (g["url"],))]
    tag_mistakes(plies)
    board = chess.Board()
    fens = [board.fen()]
    out, lines = [], {}
    for p in plies:
        mv = board.parse_san(p["san"])
        uci = mv.uci()
        best_uci = None
        if p["best"]:
            try:
                best_uci = board.parse_san(p["best"]).uci()
            except Exception:
                pass
        cls = classify(p)
        cp_w = p["cp_after"] if p["mover"] == "w" else -p["cp_after"]
        out.append(dict(ply=p["ply"], move=p["move"], mover=p["mover"], mine=int(p["mine"]), san=p["san"], uci=uci,
                        best=p["best"], best_uci=best_uci, cp_before=p["cp_before"], cp_after=p["cp_after"], cp_w=cp_w,
                        loss=p["loss"], wp_loss=p["wp_loss"], clock=p["clock"], spent=p["spent"], cls=cls))
        if p.get("cat"):
            out[-1]["cat"] = p["cat"]
        if p["mine"] and cls in ("mist", "blun", "miss"):
            L = cached_lines(con, p["fen"], p["san"], p["best"])
            if L["best_line"] or L["refutation"]:
                lines[str(p["ply"])] = dict(best_line=L["best_line"], refutation=L["refutation"])
        board.push(mv)
        fens.append(board.fen())
    summary = json.loads(g["summary"]) if isinstance(g.get("summary"), str) else (g.get("summary") or {})
    data = dict(id=game_id(g["url"]), url=g["url"], date=g["date"], white=g["white"], black=g["black"], welo=g["welo"], belo=g["belo"],
                my_color=g["my_color"], result=g["result"], outcome=g["outcome"], termination=g["termination"],
                eco_name=g["eco_name"], summary=summary, plies=out, fens=fens, lines=lines,
                depth=g.get("depth") or DEPTH, pv_depth=LINE_DEPTH)
    os.makedirs(os.path.join(DOCS, "games"), exist_ok=True)
    path = os.path.join(DOCS, "games", f"{data['id']}.json")
    json.dump(data, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    return path


GAME_EXPORT_V = "2"    # 게임 상세 JSON 의 형식 버전. 올리면 다음 실행에서 모든 게임을 다시 내보낸다 (2: 실수 유형 cat)


def export_missing_games(con):
    """상세 JSON 이 없는 게임을 내보낸다. 형식 버전이 바뀌었으면 전부 다시."""
    n = 0
    redo = meta_get(con, "game_export_v") != GAME_EXPORT_V
    for g in con.execute("SELECT * FROM games WHERE analyzed=1").fetchall():
        g = dict(g)
        if redo or not os.path.exists(os.path.join(DOCS, "games", f"{game_id(g['url'])}.json")):
            export_game(con, g)
            n += 1
    if redo:
        meta_set(con, "game_export_v", GAME_EXPORT_V)
    return n


# ---------------------------------------------------------------- notify
def send_ntfy(cfg, title, message, click=None, tags=(), actions=(), png=None):
    """ntfy 로 알림 한 건. png 가 있으면 이미지 첨부로 보낸다. 성공하면 True."""
    topic = cfg.get("NTFY_TOPIC")
    if not topic:
        return False
    try:
        if png:
            # 이미지 첨부는 PUT 본문이 파일이라 메타데이터를 헤더로 보낸다. 한글은 RFC 2047 로 인코딩.
            rfc = lambda t: "=?UTF-8?B?" + base64.b64encode(t.encode()).decode() + "?="
            h = {"Content-Type": "image/png", "Filename": "board.png", "Title": rfc(title), "Message": rfc(message), "Tags": ",".join(tags)}
            if click:
                h["Click"] = click
            if actions:
                h["Actions"] = rfc("; ".join(f"view, {a['label']}, {a['url']}" for a in actions))
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=png, headers=h, method="PUT")
        else:
            body = dict(topic=topic, title=title, message=message, tags=list(tags))
            if click:
                body["click"] = click
            if actions:
                body["actions"] = [dict(action="view", label=a["label"], url=a["url"]) for a in actions]
            req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body, ensure_ascii=False).encode(),
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except Exception as e:
        log(f"알림 실패: {e}")
        return False


def notify(cfg, game, summary, dashboard_url):
    """게임 한 판의 결과 알림. 누르면 대시보드의 그 게임, 결정적 실수 장면으로 간다."""
    res = {"W": "승리", "D": "무승부", "L": "패배"}[game["outcome"]]
    how = {"checkmated": "체크메이트", "resigned": "기권", "timeout": "시간패", "abandoned": "포기"}
    detail = how.get(game["my_result"] if game["outcome"] == "L" else game["opp_result"], "")
    color = "백" if game["my_color"] == "w" else "흑"
    lines = [f"{color} vs {game['opp']}({game['opp_elo']}) · 정확도 {summary['accuracy']}% · 대실수 {summary['blunders']} 실수 {summary['mistakes']}"]
    w = summary.get("worst")
    if w and w["wp_loss"] >= 10:
        mv = f"{w['move']}.{'' if w['mover'] == 'w' else '..'}{w['san']}"
        lines.append(f"결정적 실수: {mv} (정답 {w['best']}, {w['cp_before'] / 100:+.1f} → {w['cp_after'] / 100:+.1f}, 남은시간 {fmt_clock(w['clock'])})")
    if summary.get("my_clock_20") is not None and summary.get("opp_clock_20") is not None:
        lines.append(f"20수 시계: 나 {fmt_clock(summary['my_clock_20'])} / 상대 {fmt_clock(summary['opp_clock_20'])}")
    if summary.get("hung"):
        lines.append(f"기물 방치 {summary['hung']}회")
    if summary.get("missed_mate"):
        lines.append(f"외통 놓침 {summary['missed_mate']}회")
    title = f"래피드 {res}{'(' + detail + ')' if detail else ''} · 레이팅 {game['my_elo']}"
    click = f"{dashboard_url.rstrip('/')}/game.html?id={game_id(game['url'])}{'&ply=' + str((w['move'] - 1) * 2 + (1 if w['mover'] == 'w' else 2)) if w else ''}"
    actions = [{"label": "대시보드", "url": dashboard_url}, {"label": "체스닷컴", "url": game["url"]}]
    png = board_png(w, game["my_color"]) if w and w.get("fen") else None
    if send_ntfy(cfg, title, "\n".join(lines), click=click, tags=["trophy" if game["outcome"] == "W" else "x"], actions=actions, png=png):
        log(f"알림 전송: {game['url']}{' (보드 이미지 포함)' if png else ''}")


# 알림 대기열: 워크플로가 커밋·푸시하고 GitHub Pages 가 배포한 뒤에 알림을 보내기 위한 파일 (git 에 올리지 않는다).
# 알림을 먼저 보내면, 눌렀을 때 그 게임 페이지가 아직 배포되지 않아 "데이터를 찾을 수 없습니다" 가 뜬다.
def queue_path():
    return os.path.join(DATA, "notify_queue.json")


def queue_load():
    try:
        return json.load(open(queue_path()))
    except Exception:
        return []


def queue_save(q):
    if q:
        json.dump(q, open(queue_path(), "w"))
    elif os.path.exists(queue_path()):
        os.remove(queue_path())


def wait_for_page(url, timeout=150, every=5):
    """url 이 200 을 돌려줄 때까지 기다린다 (GitHub Pages 배포 확인). 시간 안에 뜨면 True."""
    t0 = time.time()
    while True:
        try:
            req = urllib.request.Request(f"{url}?t={int(time.time() * 1000)}", headers={"User-Agent": "chess-dashboard", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        if time.time() - t0 >= timeout:
            return False
        time.sleep(every)


def send_queued(con, cfg, timeout=150):
    """대기열의 게임 알림을, 그 게임 페이지가 배포된 것을 확인한 뒤 보낸다."""
    q = queue_load()
    sent = 0
    for url in list(q):
        g = con.execute("SELECT * FROM games WHERE url=?", (url,)).fetchone()
        if g and g["summary"]:
            base = dashboard_url(cfg)
            t0 = time.time()
            ok = wait_for_page(f"{base}games/{game_id(url)}.json", timeout)
            log(f"페이지 배포 {'확인' if ok else '대기 시간 초과'} ({time.time() - t0:.0f}s): {game_id(url)}")
            notify(cfg, dict(g), json.loads(g["summary"]), base)
            sent += 1
        q.remove(url)
        queue_save(q)
    return sent


def weekly_message(con, now):
    """지난주(월~일, KST)의 요약 (제목, 본문). 지난주에 게임이 없으면 None."""
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    a0, a1, b0 = monday - timedelta(days=7), monday, monday - timedelta(days=14)
    games = load_games(con, int(b0.timestamp()))
    cur = [g for g in games if a0.timestamp() <= g["end_time"] < a1.timestamp()]
    prev = [g for g in games if g["end_time"] < a0.timestamp()]
    if not cur:
        return None

    def agg(gs):
        mine = [p for g in gs for p in g["plies"] if p["mine"]]
        oc, n = Counter(g["outcome"] for g in gs), len(gs)
        lag = [g["summary"]["opp_clock_20"] - g["summary"]["my_clock_20"] for g in gs
               if g["summary"].get("my_clock_20") is not None and g["summary"].get("opp_clock_20") is not None]
        return dict(n=n, w=oc["W"], d=oc["D"], l=oc["L"], score=round((oc["W"] + 0.5 * oc["D"]) / n * 100, 1),
                    acc=acc([p["wp_loss"] for p in mine]), bpg=round(sum(1 for p in mine if p["loss"] >= 300) / n, 2),
                    hung=round(sum(g["summary"].get("hung", 0) for g in gs) / n, 2),
                    timeouts=sum(1 for g in gs if g["my_result"] == "timeout"), lag=(sum(lag) / len(lag) if lag else None))
    c, p = agg(cur), (agg(prev) if prev else None)
    before = con.execute("SELECT my_elo FROM games WHERE end_time<? ORDER BY end_time DESC LIMIT 1", (int(a0.timestamp()),)).fetchone()
    r0, r1 = (before[0] if before else cur[0]["my_elo"]), cur[-1]["my_elo"]
    diff = lambda key, fmt: f" ({c[key] - p[key]:{fmt}})" if p and c[key] is not None and p[key] is not None else ""
    lines = [f"{c['n']}판 {c['w']}승 {c['d']}무 {c['l']}패 · 승률 {c['score']}%{diff('score', '+.1f')}",
             f"정확도 {c['acc']}%{diff('acc', '+.1f')} · 대실수 {c['bpg']}/판{diff('bpg', '+.2f')} · 기물 방치 {c['hung']}/판{diff('hung', '+.2f')}"]
    if c["lag"] is not None:
        d = f" (그 전주 {fmt_clock(abs(p['lag']))}{' 뒤짐' if p['lag'] > 0 else ' 앞섬'})" if p and p["lag"] is not None else ""
        lines.append(f"20수 시계: 상대보다 평균 {fmt_clock(abs(c['lag']))} {'뒤짐' if c['lag'] > 0 else '앞섬'}{d} · 시간패 {c['timeouts']}판")
    worst = max((dict(g["summary"]["worst"], opp=g["opp"]) for g in cur if g["summary"].get("worst")), key=lambda w: w["wp_loss"], default=None)
    if worst and worst["wp_loss"] >= 10:
        lines.append(f"가장 아픈 수: {worst['move']}.{'' if worst['mover'] == 'w' else '..'}{worst['san']} (vs {worst['opp']}, 승률 −{worst['wp_loss']}%p, 정답 {worst['best']})")
    if p:
        lines.append("괄호 안은 그 전주와의 차이")
    last_day = a1 - timedelta(days=1)
    return f"주간 요약 {a0.month}/{a0.day}~{last_day.month}/{last_day.day} · 레이팅 {r1} ({r1 - r0:+d})", "\n".join(lines)


def maybe_weekly(con, cfg, now=None):
    """월요일 9시(KST) 이후 첫 실행에서 지난주 요약을 한 번 보낸다. 보냈으면 True."""
    now = now or datetime.now(KST)
    week = now.strftime("%G-W%V")
    last = meta_get(con, "weekly_sent")
    if last is None:   # 처음 켠 주는 건너뛰고 다음 월요일부터
        meta_set(con, "weekly_sent", week)
        return False
    if last == week or (now.weekday() == 0 and now.hour < 9):
        return False
    msg = weekly_message(con, now)
    meta_set(con, "weekly_sent", week)
    if not msg:
        return False
    ok = send_ntfy(cfg, msg[0], msg[1], click=dashboard_url(cfg) + "index.html?w=7d", tags=["calendar"])
    if ok:
        log(f"주간 요약 전송: {msg[0]}")
    return ok


def board_png(w, my_color):
    """결정적 실수 국면을 PNG 로 (빨강: 내 수, 초록: 정답). cairosvg 가 없으면 None."""
    try:
        import chess.svg, cairosvg
        b = chess.Board(w["fen"])
        uci = w.get("uci") or uci_of(w["fen"], w["san"])
        best_uci = w.get("best_uci") or (uci_of(w["fen"], w["best"]) if w.get("best") else None)
        arrows = []
        if uci:
            arrows.append(chess.svg.Arrow(chess.parse_square(uci[:2]), chess.parse_square(uci[2:4]), color="#d03b3bcc"))
        if best_uci:
            arrows.append(chess.svg.Arrow(chess.parse_square(best_uci[:2]), chess.parse_square(best_uci[2:4]), color="#149a14cc"))
        svg = chess.svg.board(b, orientation=chess.WHITE if my_color == "w" else chess.BLACK, arrows=arrows, size=640,
                              colors={"square light": "#EBECD0", "square dark": "#739552"})
        return cairosvg.svg2png(bytestring=svg.encode())
    except Exception as e:
        log(f"보드 이미지 생성 실패: {e}")
        return None


# ---------------------------------------------------------------- main
def dashboard_url(cfg):
    return f"https://{cfg.get('GITHUB_OWNER', 'x')}.github.io/{cfg.get('GITHUB_REPO', 'chess-dashboard')}/"


def code_hash():
    """render.py + pipeline.py 내용 해시. 파일 수정 시각은 git 체크아웃마다 바뀌므로 내용으로 비교한다."""
    import hashlib
    h = hashlib.sha256()
    for f in ("render.py", "pipeline.py"):
        h.update(open(os.path.join(ROOT, f), "rb").read())
    return h.hexdigest()[:16]


def _read_code_hash():
    p = os.path.join(DOCS, ".code-hash")
    return open(p).read().strip() if os.path.exists(p) else ""


def export_puzzles(con, limit=200):
    """내 실수 국면을 퍼즐로 내보낸다: 승률 20%p 이상 잃은 수, 아직 가망이 있던 국면, 최근 게임부터.
    수순과 복수 정답이 계산된 국면만 쓰고, 좋은 수가 너무 많거나 분석이 엇갈린 국면(puzzle_ok=False)은 뺀다."""
    out = []
    for g in con.execute("SELECT * FROM games WHERE analyzed=1 ORDER BY end_time DESC").fetchall():
        g = dict(g)
        for p in tag_mistakes([dict(r) for r in con.execute("SELECT * FROM plies WHERE url=? ORDER BY ply", (g["url"],))]):
            if not p["mine"] or p["wp_loss"] < 20:
                continue
            if not p["best"] or p["cp_before"] < -300 or p["cp_before"] >= 9000:
                continue
            r = con.execute("SELECT data FROM lines WHERE fen=? AND played=? AND best=?", (p["fen"], p["san"], p["best"])).fetchone()
            L = json.loads(r[0]) if r else None
            if not L or not L.get("puzzle_ok") or not L.get("best_line"):
                continue
            b = chess.Board(p["fen"])
            w = dict(id=f"{game_id(g['url'])}-{p['ply']}", ply=p["ply"], url=g["url"], date=g["date"], opp=g["opp"], color=g["my_color"],
                     move=p["move"], mover=p["mover"], san=p["san"], best=p["best"], cp_before=p["cp_before"], cp_after=p["cp_after"],
                     wp_loss=p["wp_loss"], clock=p["clock"], phase=p["phase"], fen=p["fen"], cat=p.get("cat"),
                     uci=b.parse_san(p["san"]).uci(), best_uci=b.parse_san(p["best"]).uci(),
                     best_line=L["best_line"], refutation=L.get("refutation", []), alts=L.get("alts", []),
                     legal=" ".join(sorted({m.uci()[:4] for m in b.legal_moves})))   # 브라우저가 둘 수 없는 수를 걸러내는 데 쓴다
            b.push_san(p["san"])
            w["after_fen"] = b.fen()
            out.append(w)
        if len(out) >= limit:
            break
    json.dump(out[:limit], open(os.path.join(DOCS, "puzzles.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    return len(out[:limit])


def render_all(con, cfg):
    """통계 JSON 과 기물 스프라이트를 docs/ 에 쓴다. HTML/CSS/JS 는 docs/ 의 정적 파일."""
    from render import write_pieces
    now = datetime.now(KST)
    games_all = load_games(con)
    book = build_book(con, games_all)[0] if games_all else {}
    windows = {
        "all": compute_stats(games_all, con),
        "30d": compute_stats(load_games(con, int((now - timedelta(days=30)).timestamp())), con),
        "7d": compute_stats(load_games(con, int((now - timedelta(days=7)).timestamp())), con),
    }
    payload = dict(username=cfg["CHESSCOM_USERNAME"], generated=now.strftime("%Y-%m-%d %H:%M"),
                   meta=dict(depth=DEPTH, pv_depth=LINE_DEPTH), windows=windows)
    os.makedirs(DOCS, exist_ok=True)
    n = export_puzzles(con)
    pz = Counter(p["cat"] for p in json.load(open(os.path.join(DOCS, "puzzles.json"))) if p.get("cat"))
    for S in windows.values():
        for c in (S or {}).get("coach", {}).get("cats", []):
            c["puzzles"] = pz.get(c["key"], 0)        # 이 유형으로 풀 수 있는 퍼즐 수 (기간과 무관)
        for c in "wb":
            for side in ("mine", "opp"):
                for r in ((S or {}).get("repertoire", {}).get(c) or {}).get(side, []):
                    r["book"] = len(book[r["id"]]["lines"]) if r["id"] in book else 0     # 연습 라인 수
    json.dump(dict(generated=payload["generated"], depth=BOOK_DEPTH, moves=EARLY_MOVES, openings=book),
              open(os.path.join(DOCS, "book.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(payload, open(os.path.join(DOCS, "stats.json"), "w"), ensure_ascii=False)
    # 게임·퍼즐 페이지가 읽는 작은 요약: 전체 기간의 집중 과제와 유형별 최근 빈도
    co = (windows["all"] or {}).get("coach") or dict(cats=[], focus=[], games=0, k=0)
    json.dump(dict(generated=payload["generated"], games=co["games"], k=co["k"], focus=co["focus"],
                   cats={c["key"]: dict(n=c["n"], games=c["games"], share=c["share"], recent=c["recent"]["games"], puzzles=c.get("puzzles", 0))
                         for c in co["cats"]}),
              open(os.path.join(DOCS, "coach.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    write_pieces(DOCS)
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")
    open(os.path.join(DOCS, ".code-hash"), "w").write(code_hash())
    log(f"통계 생성: docs/stats.json, 퍼즐 {n}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true", help="(호환용, 효과 없음) 저장소 업로드는 GitHub Actions 워크플로가 커밋으로 처리한다")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--defer-notify", action="store_true", help="알림을 바로 보내지 않고 data/notify_queue.json 에 쌓는다")
    ap.add_argument("--send-queued", action="store_true", help="쌓인 알림을 게임 페이지 배포를 확인한 뒤 보낸다")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--test-notify", action="store_true", help="가장 최근 게임 알림을 보내 본다")
    ap.add_argument("--weekly-dry", action="store_true", help="주간 요약 문장을 출력만 한다")
    ap.add_argument("--weekly-now", action="store_true", help="주간 요약을 지금 보낸다 (보낸 주 기록은 바꾸지 않는다)")
    ap.add_argument("--quick", action="store_true", help="통계 API 로 새 게임 유무만 먼저 확인 (1분 간격 감시용). 할 일이 없으면 조용히 끝난다")
    a = ap.parse_args()
    cfg = load_env()
    if not cfg.get("CHESSCOM_USERNAME"):
        sys.exit(".env 에 CHESSCOM_USERNAME 이 없습니다")
    os.makedirs(DATA, exist_ok=True)
    if a.test_notify:
        con = db()
        g = con.execute("SELECT * FROM games WHERE analyzed=1 ORDER BY end_time DESC LIMIT 1").fetchone()
        if g:
            notify(cfg, dict(g), json.loads(g["summary"]), dashboard_url(cfg))
        return
    if a.weekly_dry or a.weekly_now:
        msg = weekly_message(db(), datetime.now(KST))
        if not msg:
            print("지난주에 분석된 래피드 게임이 없습니다")
        elif a.weekly_dry:
            print(msg[0] + "\n" + msg[1])
        elif send_ntfy(cfg, msg[0], msg[1], click=dashboard_url(cfg) + "index.html?w=7d", tags=["calendar"]):
            log(f"주간 요약 전송: {msg[0]}")
        return
    if a.send_queued:
        send_queued(db(), cfg)
        return
    lock = open(os.path.join(DATA, "pipeline.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("이전 실행이 아직 진행 중이라 건너뜁니다")
        return
    con = db()
    new_done = []
    if not a.render_only:
        try:
            new = fetch_new_games(con, cfg, quick=a.quick)
        except Exception as e:
            log(f"체스닷컴 수집 실패: {e}")
            new = []
        if new:
            log(f"새 래피드 게임 {len(new)}판")
        new_done = analyze_pending(con, cfg)
    # 실수 국면의 수순·복수 정답. 밀린 것이 있으면 한 번에 LINES_BATCH 개씩, 최근 게임부터.
    lines_n, lines_urls = 0, set()
    try:
        lines_n, lines_urls = enrich_lines(con, cfg)
    except Exception as e:
        log(f"수순 계산 실패: {e}")
    index = os.path.join(DOCS, "stats.json")
    code_changed = os.path.exists(index) and _read_code_hash() != code_hash()
    # 오프닝 연습 라인: 새 게임이 들어왔거나 코드가 바뀌었거나 지난번에 다 못 만들었을 때만 본다
    book_n = 0
    if new_done or code_changed or a.render_only or meta_get(con, "book_pending") != "0":
        try:
            book_n, book_left = enrich_book(con, cfg)
            meta_set(con, "book_pending", "1" if book_left and book_n else "0")   # 더 평가할 것이 없는데 남았으면 그만둔다
        except Exception as e:
            log(f"오프닝 연습 라인 계산 실패: {e}")
    if new_done:
        con.commit()
        con.execute("VACUUM")   # 커밋되는 DB 파일을 작게 유지
    pending_notify = [dict(r) for r in con.execute("SELECT * FROM games WHERE analyzed=1 AND notified=0")]
    if code_changed:
        log("코드가 바뀌어 통계를 다시 만듭니다")
    rendered = bool(new_done or lines_n or book_n or a.render_only or code_changed or not os.path.exists(index))
    if rendered:
        # 수순이 새로 계산된 게임의 상세 JSON 은 다시 내보낸다
        for url in set(new_done) | lines_urls:
            export_game(con, dict(con.execute("SELECT * FROM games WHERE url=?", (url,)).fetchone()))
        exported = export_missing_games(con)
        if exported:
            log(f"게임 상세 JSON 생성 {exported}개")
        render_all(con, cfg)
        if os.environ.get("GITHUB_ACTIONS") != "true":
            log("로컬 파일만 갱신했습니다. 사이트는 GitHub Actions 가 커밋해서 갱신합니다.")
    if a.defer_notify:
        queue_save(queue_load() + [g["url"] for g in pending_notify if g["url"] not in queue_load()])
    elif not a.no_notify:
        for g in pending_notify:
            notify(cfg, g, json.loads(g["summary"]), dashboard_url(cfg))
    con.execute("UPDATE games SET notified=1 WHERE analyzed=1 AND notified=0")
    con.commit()
    if not a.no_notify and not a.render_only:
        maybe_weekly(con, cfg)
    if not (a.quick and not new_done and not rendered and not pending_notify):
        log("완료")


if __name__ == "__main__":
    main()
