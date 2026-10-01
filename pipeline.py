#!/usr/bin/env python3
"""체스닷컴 래피드 기보 자동 수집 → 스톡피시 분석 → 통계 → 대시보드 → 알림 → GitHub 업로드.

사용법:
  python pipeline.py                 전체 실행 (크론용)
  python pipeline.py --no-push       GitHub 업로드 생략
  python pipeline.py --no-notify     알림 생략
  python pipeline.py --render-only   새 게임 수집/분석 없이 대시보드만 다시 생성
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
DEPTH = 14
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
    if not os.path.exists(p):
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
    CREATE TABLE IF NOT EXISTS pv_cache(fen TEXT, played TEXT, data TEXT, PRIMARY KEY(fen, played));
    """)
    cols = {r[1] for r in con.execute("PRAGMA table_info(games)")}
    if "pushed" not in cols:
        con.execute("ALTER TABLE games ADD COLUMN pushed INTEGER DEFAULT 0")
        con.commit()
    return con


# ---------------------------------------------------------------- fetch
def http_json(url, cfg, headers=None):
    h = {"User-Agent": UA.format(owner=cfg.get("GITHUB_OWNER", "x"), repo=cfg.get("GITHUB_REPO", "x"))}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


OUTCOME_DRAW = {"agreed", "insufficient", "stalemate", "repetition", "timevsinsufficient", "50move"}


def fetch_new_games(con, cfg):
    me = cfg["CHESSCOM_USERNAME"].lower()
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
    url, pgn_text, my_color, sf = args
    eng = chess.engine.SimpleEngine.popen_uci(sf)
    eng.configure({"Hash": 32, "Threads": 1})
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


LINE_DEPTH = 16


def engine_lines(eng, fen, played_san):
    """실수 국면의 정답 수순과, 내가 둔 수 뒤 상대의 반격 수순."""
    b = chess.Board(fen)
    info = eng.analyse(b, chess.engine.Limit(depth=LINE_DEPTH))
    best_line = pv_steps(b, info.get("pv", []))
    refutation = []
    try:
        b2 = b.copy()
        b2.push_san(played_san)
        if not b2.is_game_over():
            info2 = eng.analyse(b2, chess.engine.Limit(depth=LINE_DEPTH))
            refutation = pv_steps(b2, info2.get("pv", []), 5)
    except Exception:
        pass
    return dict(best_line=best_line, refutation=refutation)


def enrich_lines(con, cfg, min_wp=25):
    """승률 손실이 큰 내 수마다 정답/반격 수순을 계산해 캐시한다 (판마다 최악의 수는 항상 포함)."""
    rows = con.execute("""SELECT p.fen, p.san FROM plies p WHERE p.mine=1 AND p.wp_loss>=?
                          AND NOT EXISTS (SELECT 1 FROM pv_cache c WHERE c.fen=p.fen AND c.played=p.san)""", (min_wp,)).fetchall()
    worst_rows = []
    for g in con.execute("SELECT summary FROM games WHERE analyzed=1"):
        w = (json.loads(g[0]) or {}).get("worst")
        if w and w.get("fen"):
            worst_rows.append((w["fen"], w["san"]))
    rep = con.execute("""SELECT fen, san FROM plies WHERE mine=1 AND move<=15 GROUP BY fen, san
                         HAVING count(*)>=2 AND avg(loss)>=60""").fetchall()
    rows = list(rows) + [r for r in rep if not con.execute("SELECT 1 FROM pv_cache WHERE fen=? AND played=?", (r[0], r[1])).fetchone()]
    todo = {(r[0], r[1]) for r in rows} | {w for w in worst_rows
            if not con.execute("SELECT 1 FROM pv_cache WHERE fen=? AND played=?", w).fetchone()}
    if not todo:
        return 0
    log(f"수순 계산 {len(todo)}개 국면 (depth {LINE_DEPTH})")
    eng = chess.engine.SimpleEngine.popen_uci(stockfish_path(cfg))
    eng.configure({"Hash": 128, "Threads": WORKERS})
    try:
        for i, (fen, san) in enumerate(sorted(todo)):
            data = engine_lines(eng, fen, san)
            con.execute("INSERT OR REPLACE INTO pv_cache(fen,played,data) VALUES(?,?,?)", (fen, san, json.dumps(data)))
            if i % 25 == 24:
                con.commit()
                log(f"  {i + 1}/{len(todo)}")
        con.commit()
    finally:
        eng.quit()
    return len(todo)


def cached_lines(con, fen, san):
    r = con.execute("SELECT data FROM pv_cache WHERE fen=? AND played=?", (fen, san)).fetchone()
    return json.loads(r[0]) if r else dict(best_line=[], refutation=[])


PLY_COLS = ("ply", "move", "mover", "mine", "san", "best", "is_best", "cp_before", "cp_after", "loss", "wp_loss",
            "clock", "spent", "capture", "chk", "piece", "phase", "fen")


def store_analysis(con, url, plies):
    con.execute("DELETE FROM plies WHERE url=?", (url,))
    con.executemany(f"INSERT INTO plies(url,{','.join(PLY_COLS)}) VALUES(?,{','.join('?' * len(PLY_COLS))})",
                    [(url, *[p.get(c) for c in PLY_COLS]) for p in plies])
    con.execute("UPDATE games SET analyzed=1, summary=? WHERE url=?", (json.dumps(summarize(plies)), url))
    con.commit()


def analyze_pending(con, cfg):
    sf = stockfish_path(cfg)
    rows = con.execute("SELECT url,pgn,my_color FROM games WHERE analyzed=0 ORDER BY end_time").fetchall()
    if not rows:
        return []
    log(f"분석 대기 {len(rows)}판 (depth {DEPTH}, {WORKERS} 프로세스)")
    tasks = [(r["url"], r["pgn"], r["my_color"], sf) for r in rows]
    done = []
    t0 = time.time()
    with Pool(min(WORKERS, len(tasks))) as pool:
        for url, plies in pool.imap_unordered(analyze_game, tasks):
            store_analysis(con, url, plies)
            g = dict(con.execute("SELECT * FROM games WHERE url=?", (url,)).fetchone())
            export_game(con, g)
            done.append(url)
            log(f"  분석 완료 {url} ({time.time() - t0:.0f}s)")
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
        g["plies"] = [dict(r) for r in con.execute("SELECT * FROM plies WHERE url=? ORDER BY ply", (g["url"],))]
    return games


def median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


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
                             path=opening_path(gs, c), trouble=opening_trouble(gs, con),
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

    # --- 최근 게임 / 최악의 실수
    def with_lines(w):
        if not w or not w.get("fen"):
            return w
        w = dict(w)
        if not w.get("uci"):
            w["uci"] = uci_of(w["fen"], w["san"])
            w["best_uci"] = uci_of(w["fen"], w["best"]) if w.get("best") else None
        w.update(cached_lines(con, w["fen"], w["san"]) if con else dict(best_line=[], refutation=[]))
        try:
            b = chess.Board(w["fen"]); b.push_san(w["san"]); w["after_fen"] = b.fen()
        except Exception:
            w["after_fen"] = None
        return w
    S["recent"] = []
    for g in games[-25:][::-1]:
        evals = [max(-1000, min(1000, p["cp_after"] if p["mine"] else -p["cp_after"])) for p in g["plies"]]
        S["recent"].append(dict(url=g["url"], date=g["date"], color=g["my_color"], opp=g["opp"], opp_elo=g["opp_elo"],
                                my_elo=g["my_elo"], outcome=g["outcome"], my_result=g["my_result"], opp_result=g["opp_result"],
                                eco_name=g["eco_name"][:35], evals=evals,
                                **{k: g["summary"].get(k) for k in ("accuracy", "blunders", "mistakes", "hung", "missed_mate",
                                                                    "my_final_clock", "opp_final_clock", "n_moves")},
                                worst=with_lines(g["summary"].get("worst"))))
    worst = []
    for g in games:
        for p in g["plies"]:
            if p["mine"] and p["wp_loss"] >= 30:
                worst.append(dict(url=g["url"], date=g["date"], opp=g["opp"], color=g["my_color"], move=p["move"], mover=p["mover"],
                                  san=p["san"], best=p["best"], cp_before=p["cp_before"], cp_after=p["cp_after"], wp_loss=p["wp_loss"],
                                  clock=p["clock"], spent=p["spent"], phase=p["phase"], fen=p["fen"]))
    worst.sort(key=lambda w: (-w["wp_loss"], w["date"]))
    S["worst"] = [with_lines(w) for w in worst[:15]]
    # 유형별 대표 실수 (기물 방치 / 외통 놓침 / 유리한 판 붕괴) 각 5개
    S["examples"] = dict(hung=[], missed_mate=[], collapse=[])
    for g in games[::-1]:
        pl = g["plies"]
        for i, p in enumerate(pl):
            if not p["mine"]:
                continue
            base = dict(url=g["url"], date=g["date"], opp=g["opp"], color=g["my_color"], move=p["move"], mover=p["mover"],
                        san=p["san"], best=p["best"], cp_before=p["cp_before"], cp_after=p["cp_after"], wp_loss=p["wp_loss"],
                        clock=p["clock"], spent=p["spent"], phase=p["phase"], fen=p["fen"])
            if len(S["examples"]["missed_mate"]) < 5 and p["cp_before"] >= 9970 and p["cp_after"] < 9000:
                S["examples"]["missed_mate"].append(base)
            elif len(S["examples"]["hung"]) < 5 and p["loss"] >= 300 and (p["clock"] or 999) >= 60 and \
                    opp_best_captures(p, pl[i + 1] if i + 1 < len(pl) else None) in (2, 3, 4, 5):
                S["examples"]["hung"].append(base)
            elif len(S["examples"]["collapse"]) < 5 and p["cp_before"] >= 300 and p["cp_after"] <= -100:
                S["examples"]["collapse"].append(base)
    for k in S["examples"]:
        S["examples"][k] = [with_lines(w) for w in S["examples"][k]]
    S["weaknesses"] = weaknesses(S, games)
    return S


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
        best = Counter(p["best"] for p, _ in lst).most_common(1)[0][0]
        p0, g0 = max(lst, key=lambda x: x[1]["end_time"])  # 가장 최근 예
        w = dict(url=g0["url"], date=g0["date"], opp=g0["opp"], color=g0["my_color"], move=p0["move"], mover=p0["mover"],
                 san=san, best=best, cp_before=p0["cp_before"], cp_after=p0["cp_after"], wp_loss=p0["wp_loss"],
                 clock=p0["clock"], spent=p0["spent"], phase=p0["phase"], fen=fen, n=len(lst), avg_loss=round(avg),
                 uci=uci_of(fen, san), best_uci=uci_of(fen, best))
        w.update(cached_lines(con, fen, san) if con else dict(best_line=[], refutation=[]))
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
}


def metric_series(games, key, arg=None):
    """보완점 지표를 게임 단위 시계열 [{d: 날짜, v: 분자, n: 분모}] 로."""
    out = []
    for g in games:
        s = g["summary"]; mine = [p for p in g["plies"] if p["mine"]]
        if key == "clock20":
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


def weaknesses(S, games=None):
    """통계에서 규칙 기반으로 보완점 문장을 뽑는다. 각 항목에 key/arg를 붙여 추이 분석 지표와 연결한다."""
    out = []
    tm, ov, cv, tc = S["time"], S["overview"], S["conversion"], S["tactics"]
    c20 = next((c for c in tm["clock_at"] if c["move"] == 20), None)
    if c20 and c20["me"] is not None and c20["opp"] is not None and c20["opp"] - c20["me"] >= 60:
        out.append(dict(level="critical", title="시간 관리", key="clock20",
                        text=f"20수 시점에 상대보다 평균 {fmt_clock(c20['opp'] - c20['me'])} 뒤처집니다. "
                             f"시간패 {tm['timeouts']}판(이기던 판 {tm['timeouts_winning']}). "
                             f"시간이 뒤진 채 20수를 맞은 판 승률 {tm['behind_at_20']['score']}%."))
    if tm["long_thinks_opening"] >= max(5, ov["games"] * 0.15):
        out.append(dict(level="serious", title="오프닝 장고", key="long_think_opening",
                        text=f"1~10수에서 45초 이상 고민한 수가 {tm['long_thinks_opening']}번입니다. "
                             "자주 두는 오프닝의 처음 8수는 외워서 10초 안에 두세요."))
    bc = {b["label"]: b["rate"] for b in tm["blunder_by_clock"]}
    if bc.get("0-30s") and bc.get("300-600s") and bc["0-30s"] >= 2 * bc["300-600s"]:
        out.append(dict(level="serious", title="시간 압박 실수", key="blunder_low_clock",
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
                out.append(dict(level="warning", title=f"{name} 오프닝", key="opening", arg=[c, o["moves"]],
                                text=f"{o['moves']} ({o['name']}) {o['n']}판 승률 {o['score']}%, "
                                     f"15수 안 대실수 {o['early_blunders']}회. 이 라인의 기본 계획을 하나 정해 두세요."))
    ph = {p["phase"]: p for p in S["phase"]}
    if "endgame" in ph and "middlegame" in ph and ph["endgame"]["accuracy"] - ph["middlegame"]["accuracy"] >= 4:
        out.append(dict(level="good", title="엔드게임은 강점", key="endgame_acc",
                        text=f"엔드게임 정확도 {ph['endgame']['accuracy']}%로 중반전({ph['middlegame']['accuracy']}%)보다 높습니다. "
                             "유리할 때 엔드게임으로 가는 전략이 유효합니다."))
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
        if p["mine"] and cls in ("mist", "blun", "miss"):
            r = con.execute("SELECT data FROM pv_cache WHERE fen=? AND played=?", (p["fen"], p["san"])).fetchone()
            if r:
                lines[str(p["ply"])] = json.loads(r[0])
        board.push(mv)
        fens.append(board.fen())
    summary = json.loads(g["summary"]) if isinstance(g.get("summary"), str) else (g.get("summary") or {})
    data = dict(id=game_id(g["url"]), url=g["url"], date=g["date"], white=g["white"], black=g["black"], welo=g["welo"], belo=g["belo"],
                my_color=g["my_color"], result=g["result"], outcome=g["outcome"], termination=g["termination"],
                eco_name=g["eco_name"], summary=summary, plies=out, fens=fens, lines=lines)
    os.makedirs(os.path.join(DOCS, "games"), exist_ok=True)
    path = os.path.join(DOCS, "games", f"{data['id']}.json")
    json.dump(data, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    return path


def export_missing_games(con):
    n = 0
    for g in con.execute("SELECT * FROM games WHERE analyzed=1"):
        g = dict(g)
        if not os.path.exists(os.path.join(DOCS, "games", f"{game_id(g['url'])}.json")):
            export_game(con, g)
            n += 1
    return n


# ---------------------------------------------------------------- notify
def notify(cfg, game, summary, dashboard_url):
    topic = cfg.get("NTFY_TOPIC")
    if not topic:
        return
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
    body = json.dumps({"topic": topic, "title": f"래피드 {res}{'(' + detail + ')' if detail else ''} · 레이팅 {game['my_elo']}",
                       "message": "\n".join(lines),
                       "click": f"{dashboard_url.rstrip('/')}/game.html?id={game_id(game['url'])}",
                       "actions": [{"action": "view", "label": "대시보드", "url": dashboard_url},
                                   {"action": "view", "label": "체스닷컴", "url": game["url"]}],
                       "tags": ["trophy" if game["outcome"] == "W" else "x"]}, ensure_ascii=False).encode()
    req = urllib.request.Request("https://ntfy.sh/", data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        log(f"알림 전송: {game['url']}")
    except Exception as e:
        log(f"알림 실패: {e}")


# ---------------------------------------------------------------- github
def gh_request(cfg, method, path, data=None):
    token = cfg.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 없음")
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "chess-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, (json.load(r) if r.length != 0 else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def push_file(cfg, repo_path, local_path, message):
    owner, repo = cfg["GITHUB_OWNER"], cfg["GITHUB_REPO"]
    content = open(local_path, "rb").read()
    st, cur = gh_request(cfg, "GET", f"/repos/{owner}/{repo}/contents/{repo_path}")
    body = {"message": message, "content": base64.b64encode(content).decode()}
    if st == 200 and "sha" in cur:
        if cur.get("content") and base64.b64decode(cur["content"].replace("\n", "")) == content:
            return "unchanged"
        body["sha"] = cur["sha"]
    st, resp = gh_request(cfg, "PUT", f"/repos/{owner}/{repo}/contents/{repo_path}", body)
    if st not in (200, 201):
        raise RuntimeError(f"업로드 실패 {repo_path}: HTTP {st} {resp.get('message')}")
    return "updated"


def ensure_pages(cfg):
    owner, repo = cfg["GITHUB_OWNER"], cfg["GITHUB_REPO"]
    st, cur = gh_request(cfg, "GET", f"/repos/{owner}/{repo}/pages")
    if st == 200:
        return cur.get("html_url")
    st, resp = gh_request(cfg, "POST", f"/repos/{owner}/{repo}/pages", {"source": {"branch": "main", "path": "/docs"}})
    if st in (201, 409):
        log("GitHub Pages 활성화됨 (main 브랜치 /docs)")
        return f"https://{owner}.github.io/{repo}/"
    log(f"GitHub Pages 자동 활성화 실패(HTTP {st}). 저장소 Settings → Pages 에서 Branch: main, Folder: /docs 로 직접 설정하세요.")
    return f"https://{owner}.github.io/{repo}/"


def cleanup_test_file(cfg):
    owner, repo = cfg["GITHUB_OWNER"], cfg["GITHUB_REPO"]
    st, cur = gh_request(cfg, "GET", f"/repos/{owner}/{repo}/contents/chess-dashboard-test.txt")
    if st == 200 and "sha" in cur:
        gh_request(cfg, "DELETE", f"/repos/{owner}/{repo}/contents/chess-dashboard-test.txt",
                   {"message": "remove setup test file", "sha": cur["sha"]})


def push_dashboard(cfg):
    url = ensure_pages(cfg)
    cleanup_test_file(cfg)
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    for name in ("index.html", "stats.json", ".nojekyll", "game.html"):
        r = push_file(cfg, f"docs/{name}", os.path.join(DOCS, name), f"update dashboard {stamp}")
        log(f"  {name}: {r}")
    return url


def push_games(con, cfg, limit=120):
    """아직 안 올라간 게임 JSON 업로드 (한 번에 최대 limit개, 다음 크론에서 이어서)."""
    rows = con.execute("SELECT url FROM games WHERE analyzed=1 AND pushed=0 ORDER BY end_time DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return 0
    log(f"게임 상세 업로드 {len(rows)}개")
    n = 0
    for (url,) in rows:
        gid = game_id(url)
        local = os.path.join(DOCS, "games", f"{gid}.json")
        if not os.path.exists(local):
            continue
        try:
            push_file(cfg, f"docs/games/{gid}.json", local, f"game {gid}")
            con.execute("UPDATE games SET pushed=1 WHERE url=?", (url,))
            con.commit()
            n += 1
        except Exception as e:
            log(f"  실패 {gid}: {e}")
            break
    return n


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


def render_all(con, cfg):
    from render import render_html
    now = datetime.now(KST)
    windows = {
        "all": compute_stats(load_games(con), con),
        "30d": compute_stats(load_games(con, int((now - timedelta(days=30)).timestamp())), con),
        "7d": compute_stats(load_games(con, int((now - timedelta(days=7)).timestamp())), con),
    }
    payload = dict(username=cfg["CHESSCOM_USERNAME"], generated=now.strftime("%Y-%m-%d %H:%M"), windows=windows)
    os.makedirs(DOCS, exist_ok=True)
    json.dump(payload, open(os.path.join(DOCS, "stats.json"), "w"), ensure_ascii=False)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(render_html(payload))
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")
    open(os.path.join(DOCS, ".code-hash"), "w").write(code_hash())
    from render import render_game_page
    open(os.path.join(DOCS, "game.html"), "w", encoding="utf-8").write(render_game_page())
    log("대시보드 생성: docs/index.html, docs/game.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--test-notify", action="store_true", help="가장 최근 게임 알림을 보내 본다")
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
            new = fetch_new_games(con, cfg)
        except Exception as e:
            log(f"체스닷컴 수집 실패: {e}")
            new = []
        if new:
            log(f"새 래피드 게임 {len(new)}판")
        new_done = analyze_pending(con, cfg)
    pending_notify = [dict(r) for r in con.execute("SELECT * FROM games WHERE analyzed=1 AND notified=0")]
    index = os.path.join(DOCS, "index.html")
    code_changed = os.path.exists(index) and _read_code_hash() != code_hash()
    if code_changed:
        log("코드가 바뀌어 대시보드를 다시 만듭니다")
    if new_done or a.render_only or code_changed or not os.path.exists(index):
        try:
            enrich_lines(con, cfg)
        except Exception as e:
            log(f"수순 계산 실패: {e}")
        # 실수 수순이 새로 계산됐을 수 있으니 새 게임 JSON 은 다시 내보낸다
        for url in new_done:
            export_game(con, dict(con.execute("SELECT * FROM games WHERE url=?", (url,)).fetchone()))
        exported = export_missing_games(con)
        if exported:
            log(f"게임 상세 JSON 생성 {exported}개")
        render_all(con, cfg)
        if not a.no_push:
            try:
                url = push_dashboard(cfg)
                log(f"업로드 완료 → {url}")
            except Exception as e:
                log(f"GitHub 업로드 실패: {e}")
    if not a.no_push:
        try:
            n = push_games(con, cfg)
            if n:
                log(f"게임 상세 {n}개 업로드")
        except Exception as e:
            log(f"게임 상세 업로드 실패: {e}")
    if not a.no_notify:
        for g in pending_notify:
            notify(cfg, g, json.loads(g["summary"]), dashboard_url(cfg))
    con.execute("UPDATE games SET notified=1 WHERE analyzed=1 AND notified=0")
    con.commit()
    log("완료")


if __name__ == "__main__":
    main()
