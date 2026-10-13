"""교본(docs/lessons.json) 원고용 작은 표기법. content.py 가 이 함수들로 장을 쓴다.
수순은 전부 python-chess 로 두어 보고 FEN·UCI 를 채우므로, 둘 수 없는 수가 원고에 있으면 빌드가 실패한다."""
import io

import chess
import chess.pgn

PARTS, CHAPTERS = [], []
NAG = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!"}


def part(pid, name, sub):
    PARTS.append({"id": pid, "name": name, "sub": sub})


def chapter(cid, title, sub, blocks, cats=(), rep=()):
    if any(c["id"] == cid for c in CHAPTERS):
        raise ValueError("장 id 중복: " + cid)
    for i, b in enumerate(blocks):
        b["_at"] = f"{cid}#{i}"
    CHAPTERS.append({"id": cid, "part": PARTS[-1]["id"], "title": title, "sub": sub,
                     "cats": list(cats), "rep": list(rep), "blocks": blocks})


def _board(fen=None, after=None):
    b = chess.Board(fen) if fen else chess.Board()
    if not b.is_valid():
        raise ValueError(f"잘못된 국면: {fen} ({b.status()!r})")
    if after:
        g = _game(after, fen)
        for m in g.mainline_moves():
            b.push(m)
    return b


def _game(pgn, fen=None):
    head = f'[FEN "{fen}"]\n[SetUp "1"]\n\n' if fen else ""
    g = chess.pgn.read_game(io.StringIO(head + pgn.strip() + " *"))
    if g is None or g.errors:
        raise ValueError(f"둘 수 없는 수순: {pgn!r} {g.errors if g else ''}")
    if not list(g.mainline_moves()):
        raise ValueError(f"빈 수순: {pgn!r}")
    return g


def _plies(pgn, fen=None):
    g = _game(pgn, fen)
    b, out = g.board(), []
    for i, node in enumerate(g.mainline()):
        m, mover, no = node.move, b.turn, b.fullmove_number
        san = b.san(m) + "".join(NAG[n] for n in sorted(node.nags) if n in NAG)
        b.push(m)
        out.append({"san": san, "uci": m.uci(), "fen": b.fen(), "c": " ".join(node.comment.split()),
                    "num": f"{no}." if mover else (f"{no}..." if i == 0 else "")})
    return {"fen": g.board().fen(), "intro": " ".join(g.comment.split()), "plies": out}


def P(x):
    return {"t": "p", "x": x}


def H(x):
    return {"t": "h", "x": x}


def TIP(x, k="기억할 것"):
    return {"t": "tip", "x": x, "k": k}


def UL(*items):
    return {"t": "list", "items": list(items)}


def B(cap, fen=None, after=None, arrows="", marks="", flip=False):
    """그림 한 장. arrows 는 'e2e4 g1f3' 같은 UCI 나열, marks 는 강조할 칸."""
    b = _board(fen, after)
    for a in arrows.split():
        chess.parse_square(a[:2]), chess.parse_square(a[2:4])
    for s in marks.split():
        chess.parse_square(s)
    return {"t": "board", "fen": b.fen(), "cap": cap, "arrows": arrows.split(), "marks": marks.split(), "flip": flip}


def L(cap, pgn, fen=None, flip=False, label="본선", more=()):
    """한 수씩 넘겨 보는 수순. {} 안은 그 수의 해설, 수 뒤의 ? ! 는 그대로 표시된다. more = [(이름, 수순)] 은 갈래."""
    lines = [dict(_plies(pgn, fen), label=label)]
    for lab, p in more:
        lines.append(dict(_plies(p, fen), label=lab))
    return {"t": "line", "cap": cap, "flip": flip, "lines": lines}


def T(q, answer, x, fen=None, after=None, flip=False, ok=()):
    """직접 두어 보는 한 수 문제. answer 는 SAN, ok 는 함께 정답으로 받는 수."""
    b = _board(fen, after)
    m = b.parse_san(answer)
    def after(mv):
        c = b.copy()
        c.push(mv)
        return c

    alts = [{"uci": b.parse_san(s).uci(), "san": s, "after": after(b.parse_san(s)).fen()} for s in ok]
    a = after(m)
    return {"t": "try", "fen": b.fen(), "q": q, "uci": m.uci(), "san": b.san(m), "ok": alts, "x": x,
            "after": a.fen(), "flip": flip or not b.turn, "mate": a.is_checkmate()}
