"""기물 SVG 세트를 docs/pieces.svg 심볼 묶음으로 만든다. 대시보드 HTML/CSS/JS 는 docs/ 에 정적 파일로 있다."""
import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
PIECE_SETS = (("maestro", "50"), ("cburnett", "45"), ("merida", "50"), ("alpha", "2048"), ("california", "400"))


def grain_uri():
    import base64
    path = os.path.join(ROOT, "pieces", "grain.png")
    if not os.path.exists(path):
        return ""
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def _namespace_ids(inner, prefix):
    """SVG 내부 id(그라디언트/필터/클립패스)에 접두어를 붙인다.
    60개 기물 SVG가 한 문서에 들어가면 id="a" 같은 이름이 겹쳐서
    흑 기물의 url(#a)가 백 기물의 그라디언트를 가리키게 된다."""
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    if not ids:
        return inner
    inner = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', inner)
    inner = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}-{m.group(1)})' if m.group(1) in ids else m.group(0), inner)
    inner = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda m: f'{m.group(1)}="#{prefix}-{m.group(2)}"' if m.group(2) in ids else m.group(0), inner)
    return inner


def piece_symbols():
    """pieces/<set>/*.svg → <symbol id="<set>-wK"> 묶음."""
    out = []
    for name, vb in PIECE_SETS:
        for p in ("wK", "wQ", "wR", "wB", "wN", "wP", "bK", "bQ", "bR", "bB", "bN", "bP"):
            path = os.path.join(ROOT, "pieces", name, f"{p}.svg")
            if not os.path.exists(path):
                continue
            svg = open(path, encoding="utf-8").read()
            m = re.search(r'viewBox="([^"]*)"', svg)
            viewbox = m.group(1) if m else f"0 0 {vb} {vb}"
            inner = re.sub(r"^.*?<svg[^>]*>", "", svg, count=1, flags=re.S)
            inner = re.sub(r"</svg>\s*$", "", inner, flags=re.S)
            inner = _namespace_ids(inner, f"{name}-{p}")
            out.append(f'<symbol id="{name}-{p}" viewBox="{viewbox}">{inner}</symbol>')
    g = grain_uri()
    if g:
        out.append(f'<image id="grain-img" href="{g}" x="0" y="0" width="800" height="800" preserveAspectRatio="none"/>')
    return '<svg width="0" height="0" style="position:absolute"><defs>' + "".join(out) + "</defs></svg>"



def write_pieces(docs):
    """docs/pieces.svg 생성 (내용이 같으면 파일을 건드리지 않는다)."""
    path = os.path.join(docs, "pieces.svg")
    svg = piece_symbols()
    if not os.path.exists(path) or open(path, encoding="utf-8").read() != svg:
        open(path, "w", encoding="utf-8").write(svg)
