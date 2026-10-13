"""교본 빌드: lessons/content.py → docs/lessons.json.
  ./venv/bin/python lessons/build.py            원고를 두어 보고 JSON 을 쓴다
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
TRY_CP, LINE_CP, LOST, DEPTH = 60, 130, 400, 16


def build():
    chapters = []
    for c in dsl.CHAPTERS:
        blocks = [{k: v for k, v in b.items() if k != "_at"} for b in c["blocks"]]
        words = sum(len(str(b.get("x", "")) + "".join(b.get("items", []))) for b in blocks)
        steps = sum(len(l["plies"]) for b in blocks if b["t"] == "line" for l in b["lines"])
        chapters.append(dict(c, blocks=blocks, min=max(2, round(words / 450 + steps / 14 + sum(b["t"] in ("board", "try") for b in blocks) * 0.3))))
    return {"parts": dsl.PARTS, "chapters": chapters}


def score(info, turn):
    return info["score"].pov(turn).score(mate_score=10000)


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
    ap.add_argument("--engine", default=os.path.join(ROOT, "engine", "stockfish"))
    a = ap.parse_args()
    data = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(data['chapters'])}장, {os.path.getsize(OUT) // 1024}KB → docs/lessons.json")
    if a.verify:
        sys.exit(1 if verify(a.engine) else 0)
