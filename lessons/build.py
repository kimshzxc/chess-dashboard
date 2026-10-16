"""교본 빌드: lessons/content.py → docs/lessons.json.
  ./venv/bin/python lessons/build.py            원고를 두어 보고 JSON 을 쓴다
  ./venv/bin/python lessons/build.py --eval     '직접 두어 보기' 국면의 모든 수를 스톡피시로 평가해 lessons/evals.json 에 쌓는다 (둬 본 수의 승률 표시용)
  ./venv/bin/python lessons/build.py --verify   스톡피시로 원고를 검수한다 (문제의 정답이 최선인지, 표시 없는 큰 실수가 수순에 없는지)"""
import argparse
import json
import os
import sys

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import content  # noqa: E402,F401  (장을 등록한다)
import dsl  # noqa: E402

OUT = os.path.join(ROOT, "docs", "lessons.json")
EVALS = os.path.join(HERE, "evals.json")   # {fen: {uci 앞 4글자: cp(둘 쪽 기준)}} '직접 두어 보기' 국면의 모든 수 평가 (--eval 이 채운다)
TRY_CP, LINE_CP, LOST, DEPTH, EVAL_DEPTH = 60, 130, 400, 16, 14


def load_evals():
    try:
        with open(EVALS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def build():
    evals = load_evals()
    chapters = []
    for c in dsl.CHAPTERS:
        blocks = [{k: v for k, v in b.items() if k != "_at"} for b in c["blocks"]]
        for b in blocks:
            if b["t"] == "try" and b["fen"] in evals:   # 국면 평가 = 가장 좋은 수의 값. 수를 두면 그 수의 값으로 바뀐다
                b["moves"] = evals[b["fen"]]
                b["cp"] = max(b["moves"].values())
        words = sum(len(str(b.get("x", "")) + "".join(b.get("items", []))) for b in blocks)
        steps = sum(len(l["plies"]) for b in blocks if b["t"] == "line" for l in b["lines"])
        chapters.append(dict(c, blocks=blocks, min=max(2, round(words / 450 + steps / 14 + sum(b["t"] in ("board", "try") for b in blocks) * 0.3))))
    return {"parts": dsl.PARTS, "chapters": chapters}


def score(info, turn):
    return info["score"].pov(turn).score(mate_score=10000)


def cp_of(info, turn):
    """파이프라인과 같은 눈금: 외통은 ±(10000 − 수×10), 나머지는 ±1500 안."""
    s = info["score"].pov(turn)
    if s.is_mate():
        m = s.mate()
        return (10000 - abs(m) * 10) if m > 0 else (-10000 + abs(m) * 10)
    return max(-1500, min(1500, s.score()))


def evaluate(engine_path):
    """아직 평가하지 않은 '직접 두어 보기' 국면의 합법 수 전부를 평가해 evals.json 에 더한다. 더한 국면 수를 돌려준다."""
    evals, fens = load_evals(), []
    for c in dsl.CHAPTERS:
        for b in c["blocks"]:
            if b["t"] == "try" and b["fen"] not in evals and b["fen"] not in fens:
                fens.append(b["fen"])
    if not fens:
        return 0
    eng = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        for fen in fens:
            bd = chess.Board(fen)
            out = {}
            for i in eng.analyse(bd, chess.engine.Limit(depth=EVAL_DEPTH), multipv=bd.legal_moves.count()):
                if i.get("pv"):
                    u, cp = i["pv"][0].uci()[:4], cp_of(i, bd.turn)
                    out[u] = max(cp, out.get(u, -99999))
            evals[fen] = dict(sorted(out.items()))
            print(f"[평가] {fen[:30]:30} {len(out)}수, 최선 {max(out.values()):+}")
    finally:
        eng.quit()
    with open(EVALS, "w", encoding="utf-8") as f:
        json.dump(evals, f, ensure_ascii=False, indent=0, sort_keys=True)
    return len(fens)


def verify(engine_path):
    eng = chess.engine.SimpleEngine.popen_uci(engine_path)
    bad = 0
    lim = chess.engine.Limit(depth=DEPTH)
    for c in dsl.CHAPTERS:
        for b in c["blocks"]:
            if b["t"] == "try":
                bd = chess.Board(b["fen"])
                top = eng.analyse(bd, lim, multipv=3)
                best = score(top[0], bd.turn)
                mine = score(eng.analyse(bd, lim, root_moves=[chess.Move.from_uci(b["uci"])]), bd.turn)
                good = [bd.san(t["pv"][0]) for t in top if best - score(t, bd.turn) <= TRY_CP]
                flag = "" if best - mine <= TRY_CP else "  <-- 정답이 최선이 아님"
                extra = [s for s in good if s != b["san"] and s not in [o["san"] for o in b["ok"]]]
                if extra and not b["mate"]:
                    flag += f"  (비슷한 수: {', '.join(extra)})"
                bad += "<--" in flag
                print(f"[문제] {b['_at']:22} {b['san']:8} {mine:+6} 최선 {bd.san(top[0]['pv'][0])} {best:+6}{flag}")
            elif b["t"] == "line":
                for ln in b["lines"]:
                    bd = chess.Board(ln["fen"])
                    prev = score(eng.analyse(bd, lim), bd.turn)
                    for p in ln["plies"]:
                        mover = bd.turn
                        bd.push(chess.Move.from_uci(p["uci"]))
                        cur = -10000 if bd.is_checkmate() else 0 if bd.is_game_over() else score(eng.analyse(bd, lim), bd.turn)
                        loss = prev + cur          # 둔 쪽 기준으로 잃은 값
                        marked = "?" in p["san"]
                        if loss >= LINE_CP and -LOST < prev < 9000 and not marked:   # 이미 진 쪽의 수는 따지지 않는다
                            bad += 1
                            print(f"[수순] {b['_at']:22} {ln['label']}: {p['num']}{p['san']} 이(가) {loss}cp 를 잃는데 표시가 없음")
                        if marked and loss < 60:
                            print(f"[수순] {b['_at']:22} {ln['label']}: {p['num']}{p['san']} 은 ? 표시지만 손실 {loss}cp")
                        prev = cur
                    print(f"       {b['_at']:22} {ln['label']}: 끝 형세 백 기준 {(prev if bd.turn else -prev):+}")
            elif b["t"] == "board":
                bd = chess.Board(b["fen"])
                if bd.is_game_over():
                    print(f"[그림] {b['_at']:22} {bd.result()} {'외통' if bd.is_checkmate() else '무승부 국면'}")
                else:
                    info = eng.analyse(bd, lim)
                    print(f"[그림] {b['_at']:22} {'백' if bd.turn else '흑'} 차례, 최선 {bd.san(info['pv'][0])}, 백 기준 {score(info, chess.WHITE):+}")
    eng.quit()
    print(f"\n문제 {bad}건" if bad else "\n검수 통과")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--engine", default=os.path.join(ROOT, "engine", "stockfish"))
    a = ap.parse_args()
    if a.eval:
        print(f"국면 {evaluate(a.engine)}개 평가 → lessons/evals.json")
    data = build()
    missing = sum(1 for c in data["chapters"] for b in c["blocks"] if b["t"] == "try" and "cp" not in b)
    if missing:
        print(f"평가가 없는 문제 {missing}개: --eval 로 채우면 둬 본 수의 승률이 표시됩니다")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(data['chapters'])}장, {os.path.getsize(OUT) // 1024}KB → docs/lessons.json")
    if a.verify:
        sys.exit(1 if verify(a.engine) else 0)
