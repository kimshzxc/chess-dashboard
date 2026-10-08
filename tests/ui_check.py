#!/usr/bin/env python3
"""화면을 실제로 눌러 보는 점검. 헤드리스 크롬을 DevTools 프로토콜로 조작해 탭 전환, 그래프 툴팁, 시트,
게임 페이지 이동, 퍼즐 채점, 설치형 웹앱 동작을 확인한다. 스크린샷만으로는 눌렀을 때의 결함이 보이지 않는다.

  python tests/ui_check.py                                         로컬 docs/ 를 임시 서버로 띄워 점검
  python tests/ui_check.py --base https://<owner>.github.io/<repo>/   배포된 사이트 점검 (읽기만 한다)
  python tests/ui_check.py --shots DIR                             주요 화면 스크린샷을 DIR 에 저장

필요: google-chrome 또는 chromium, `pip install websocket-client chess`.
로컬 점검은 docs/ 에 stats.json, puzzles.json, games/ 가 있어야 한다 (`python tools/gh_pull.py`).
실패가 하나라도 있으면 종료 코드 1."""
import argparse, base64, functools, http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request

try:
    import websocket
except ImportError:
    sys.exit("websocket-client 가 필요합니다: pip install websocket-client")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = "abcdefgh"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail != "" else ""), flush=True)


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class LocalServer:
    """docs/ 를 서빙. stop() 으로 내려서 오프라인 상황을 만들 수 있다."""
    def __init__(self, directory):
        self.directory, self.port, self.httpd = directory, free_port(), None

    def start(self):
        http.server.ThreadingHTTPServer.allow_reuse_address = True
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), functools.partial(QuietHandler, directory=self.directory))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close(); self.httpd = None


class CDP:
    def __init__(self, port):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        t = json.load(urllib.request.urlopen(req))
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30)
        self.id, self.events, self.on_event = 0, [], None
        for d in ("Page", "Runtime", "Log", "Network"):
            self.call(d + ".enable")

    def _recv(self):
        m = json.loads(self.ws.recv())
        if "method" in m:
            self.events.append(m)
            if self.on_event:
                self.on_event(m)
        return m

    def send(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        return self.id

    def call(self, method, **params):
        mid = self.send(method, **params)
        while True:
            m = self._recv()
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def pump(self, secs):
        end = time.time() + secs
        self.ws.settimeout(0.2)
        while time.time() < end:
            try:
                self._recv()
            except websocket.WebSocketTimeoutException:
                pass
        self.ws.settimeout(30)

    def ev(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300])
        return r["result"].get("value")

    def viewport(self, w, h, mobile=True):
        self.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=mobile)
        self.call("Emulation.setTouchEmulationEnabled", enabled=mobile)

    def wait(self, expr, timeout=12, interval=0.2):
        end, last = time.time() + timeout, None
        while time.time() < end:
            try:
                last = self.ev(expr)
                if last:
                    return last
            except Exception:
                last = None
            self.pump(interval)
        return last

    def go(self, url, ready, timeout=20):
        self.call("Page.navigate", url=url)
        return self.wait(ready, timeout)

    def rect(self, sel, scroll="center"):
        s = f'e.scrollIntoView({{block:"{scroll}",inline:"center",behavior:"instant"}});' if scroll else ""
        return self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e) return null; {s} const r=e.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2,r.width,r.height,r.left,r.top];}})()")

    def tap_xy(self, x, y, settle=0.35):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
        self.pump(settle)

    def touch_xy(self, x, y, settle=0.35):
        """손가락으로 눌렀다 떼기 (pointerType=touch). 떼면 pointerout/leave 가 뒤따른다."""
        self.call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
        self.call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        self.pump(settle)

    def tap(self, sel, scroll="center", fx=0.5, y_target=None):
        """요소를 누른다. y_target 을 주면 요소가 화면의 그 높이에 오도록 스크롤한 뒤 누른다 (고정 영역 밑을 피할 때)."""
        if y_target is not None:
            ok = self.ev(f"(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e) return false; const r=e.getBoundingClientRect(); window.scrollBy({{top:r.top+r.height/2-{y_target},behavior:'instant'}}); return true;}})()")
            if not ok:
                return False
            scroll = None
        r = self.rect(sel, scroll)
        if not r or r[2] <= 0:
            return False
        self.pump(0.1)
        r = self.rect(sel, None)
        self.tap_xy(r[4] + r[2] * fx, r[1])
        return True

    def shot(self, path):
        open(path, "wb").write(base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"]))

    def errors(self):
        out = []
        for m in self.events:
            me, p = m.get("method"), m.get("params", {})
            if me == "Runtime.exceptionThrown":
                out.append("EXC " + (p["exceptionDetails"].get("exception", {}).get("description") or p["exceptionDetails"].get("text", ""))[:200])
            elif me == "Runtime.consoleAPICalled" and p.get("type") in ("error", "assert"):
                out.append("CONSOLE " + " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))[:200])
            elif me == "Log.entryAdded" and p["entry"].get("level") == "error":
                out.append("LOG " + p["entry"].get("text", "")[:120] + " " + p["entry"].get("url", "")[-60:])
        self.events = []
        return out


def fen_set(fen, flip):
    out = set()
    for ri, row in enumerate(fen.split()[0].split("/")):
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
            else:
                x, y = (7 - f, 7 - ri) if flip else (f, ri)
                out.add((("w" if ch.isupper() else "b") + ch.upper(), x * 100, y * 100)); f += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="점검할 사이트 주소 (기본: 로컬 docs/ 를 임시 서버로)")
    ap.add_argument("--shots", help="스크린샷 저장 폴더")
    a = ap.parse_args()
    chrome = next((shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(n)), None)
    if not chrome:
        sys.exit("google-chrome 또는 chromium 이 필요합니다")
    server = None
    if a.base:
        base = a.base.rstrip("/") + "/"
    else:
        server = LocalServer(os.path.join(ROOT, "docs")); server.start()
        base = f"http://127.0.0.1:{server.port}/"
    shots = a.shots
    if shots:
        os.makedirs(shots, exist_ok=True)
    prof, port = tempfile.mkdtemp(prefix="uicheck-"), free_port()
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
                             f"--remote-debugging-port={port}", "--remote-allow-origins=*", f"--user-data-dir={prof}", "--window-size=390,844", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1); break
            except Exception:
                time.sleep(0.2)
        run(CDP(port), base, server, shots)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        if server:
            server.stop()
        shutil.rmtree(prof, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)} / {len(RESULTS)} 통과" + ("" if not bad else "\n실패: " + "; ".join(bad)))
    sys.exit(1 if bad else 0)


def run(c, base, server, shots):
    fetch_json = lambda path: json.load(urllib.request.urlopen(urllib.request.Request(base + path, headers={"User-Agent": "ui-check"}), timeout=30))
    stats, puzzles = fetch_json("stats.json"), fetch_json("puzzles.json")
    S = stats["windows"]["all"]
    snap = (lambda name: c.shot(os.path.join(shots, name + ".png"))) if shots else (lambda name: None)
    q = lambda t="": f"{'&' if '?' in t else '?'}t={int(time.time() * 1000)}"
    VIS = "[...document.querySelectorAll('#main>section')].filter(s=>!s.hidden).map(s=>s.dataset.view||'?')"
    OVER = "[document.documentElement.scrollWidth, window.innerWidth]"
    READY = "document.querySelectorAll('#main>section').length>0"
    TIP = lambda cid: f"(()=>{{const t=document.querySelector('#{cid}')?.parentElement.querySelector('.tip'); return t&&t.classList.contains('on')?t.textContent:''}})()"
    c.viewport(390, 844)

    # ------------------------------------------------------------ 대시보드
    print("== 대시보드")
    check("대시보드가 뜬다", c.go(base + "index.html" + q(), READY))
    v = c.ev(VIS); check("홈에는 홈 섹션만 보인다", v and set(v) == {"home"}, v)
    o = c.ev(OVER); check("가로 넘침 없음 (홈)", o[0] <= o[1], o)
    check("히어로 레이팅 숫자", str(S["overview"]["rating"]) in (c.ev("document.querySelector('.herocard .big')?.textContent") or ""))
    r = c.rect("#rchart"); c.pump(0.2); r = c.rect("#rchart", None)
    c.touch_xy(r[0], r[1])
    check("레이팅 그래프: 누르면 값이 뜨고 손을 떼도 남는다", c.ev(TIP("rchart")), c.ev(TIP("rchart")))
    c.touch_xy(r[0] + 60, r[1]); t2 = c.ev(TIP("rchart"))
    check("레이팅 그래프: 다른 곳을 누르면 그 값으로 바뀐다", t2, t2)
    hero = c.rect(".herocard .k", None); c.touch_xy(hero[0], hero[1])
    check("레이팅 그래프: 그래프 밖을 누르면 사라진다", not c.ev(TIP("rchart")))
    snap("home")
    co = S.get("coach") or {}
    if co.get("cats"):
        check("홈은 레이팅이 맨 위, 그다음이 집중 과제", c.ev("[...document.querySelectorAll('#main>section:not([hidden])')].map(s=>s.id||s.className)")[:2] == ["hero", "s-coach"])
        check("집중 과제가 비중 순으로 나온다", c.ev("document.querySelectorAll('#s-coach .frow').length") == len(co["focus"])
              and c.ev("[...document.querySelectorAll('#s-coach .frow .shr b')].map(e=>parseFloat(e.textContent))") == [x["share"] for x in co["cats"] if x["key"] in co["focus"]],
              c.ev("[...document.querySelectorAll('#s-coach .frow .nm b')].map(e=>e.textContent)"))
        check("직전 판 피드백과 두기 전 질문", c.ev("!!document.querySelector('#s-coach .lastg')") and c.ev("[...document.querySelectorAll('#s-coach .frow .q')].filter(e=>e.textContent.trim()).length") == len(co["focus"]),
              (c.ev("document.querySelector('#s-coach .lastg .v')?.innerText") or "")[:50])
        dots = c.ev("[...document.querySelectorAll('#s-coach .frow')].map(f=>[f.querySelectorAll('.seq i').length, f.querySelectorAll('.seq i.hit').length])")
        want = [[x["recent"]["k"], x["recent"]["games"]] for x in co["cats"] if x["key"] in co["focus"]]
        check("집중 과제: 최근 판 점이 데이터와 같다", dots == want, dots)
        key = co["focus"][-1]
        c.tap(f'#s-coach .frow[data-opencat="{key}"]'); c.pump(0.8)
        check("집중 과제를 누르면 복기 탭에서 그 유형이 펼쳐진다", c.ev("document.querySelector('#tabbar a.on')?.dataset.tab") == "mistakes" and c.ev("document.querySelector('#s-cats .cat.open')?.id") == "cat-" + key
              and c.ev("!!document.querySelector('#s-cats .cat.open .viewer svg.board')") and c.ev("!document.querySelector('#s-cats').hidden"))
        c.ev("history.back()"); c.pump(0.8)
        check("뒤로 가면 홈", c.ev("document.querySelector('#tabbar a.on')?.dataset.tab") == "home")
    hints = [w for w in S["weaknesses"] if w["level"] == "hint"]
    lv = c.ev("[...document.querySelectorAll('.weak')].map(e=>e.classList.contains('hint'))")
    check("근거 약한 보완점은 '표본 부족'으로 뒤에 모인다", lv == sorted(lv) and sum(lv) == len(hints)
          and (not hints or c.ev("document.querySelector('.weak.hint .ic')?.textContent") == "표본 부족"), f"hint {sum(lv or [])}/{len(lv or [])}")
    check("보완점 카드를 누르면 시트가 열린다", c.tap(".weak") and c.wait("document.querySelector('#sheet').classList.contains('open') && !!document.querySelector('#sheet .verdict')", 3),
          c.ev("document.querySelector('#sheet-title').textContent"))
    if c.ev("!!document.querySelector('#tchart')"):
        r = c.rect("#tchart"); c.pump(0.2); r = c.rect("#tchart", None); c.touch_xy(r[0], r[1])
        check("추이 그래프: 누르면 값이 뜬다", c.ev(TIP("tchart")), c.ev(TIP("tchart")))
    snap("sheet")
    check("시트 닫기", c.tap("#sheet-x", None) and c.wait("!document.querySelector('#sheet').classList.contains('open')", 3))
    if hints:
        i = S["weaknesses"].index(hints[0])
        c.go(base + f"index.html?weak={i}" + q("?"), "document.querySelector('#sheet').classList.contains('open')", 12)
        check("표본 부족 카드의 시트에 근거 안내가 있다", c.ev("!!document.querySelector('#sheet .evnote')"), c.ev("document.querySelector('#sheet .evnote')?.textContent.slice(0,40)"))
        c.tap("#sheet-x", None)
    for tab in ("games", "mistakes", "stats"):
        c.ev("window.scrollTo(0,600)"); c.pump(0.3)
        ok = c.tap(f'#tabbar a[data-tab="{tab}"]', None); c.pump(0.9)
        v = c.ev(VIS)
        check(f"{tab} 탭: 그 섹션만 보이고 맨 위로 간다", ok and v and set(v) == {tab} and c.ev("document.querySelector('#tabbar a.on')?.dataset.tab") == tab and c.wait("window.scrollY<5", 3),
              f"{len(v or [])} sections")
        o = c.ev(OVER); check(f"가로 넘침 없음 ({tab})", o[0] <= o[1], o)
        if tab == "games":
            n0 = c.ev("[...document.querySelectorAll('#s-recent .game')].filter(g=>g.offsetParent).length")
            c.tap('[data-fold="fold-recent"]')
            n1 = c.ev("[...document.querySelectorAll('#s-recent .game')].filter(g=>g.offsetParent).length")
            check("나머지 판 펼치기", n1 > n0, f"{n0} → {n1}")
            c.tap("#s-recent [data-expand]")
            check("장면 보기: 보드가 그려진다", c.wait("!!document.querySelector('#s-recent .viewer svg.board')", 3))
            cap0 = c.ev("document.querySelector('#s-recent .viewer .cap')?.textContent"); c.tap("#s-recent .viewer [data-go='1']")
            check("장면 보기: 다음 수로 넘어간다", cap0 != c.ev("document.querySelector('#s-recent .viewer .cap')?.textContent"))
            c.tap('#tabs button[data-w="7d"]', None); c.pump(0.8); v = c.ev(VIS)
            check("기간을 바꿔도 탭이 유지된다", (v and set(v) == {"games"}) or c.ev("!!document.querySelector('#main .empty')"), v)
            c.tap('#tabs button[data-w="all"]', None); c.pump(0.8)
        if tab == "mistakes":
            check("복기 보드가 그려진다", c.ev("document.querySelectorAll('#main>section:not([hidden]) svg.board').length") > 0)
            check("SVG id 가 겹치지 않는다 (흑 기물 색)", c.ev("new Set([...document.querySelectorAll('svg [id]')].map(e=>e.id)).size === document.querySelectorAll('svg [id]').length"))
            mis = c.ev("""(()=>{let bad=0; for(const k in VIEWERS){ const L=VIEWERS[k].spec.lines.find(l=>l.label==='정답 수순'); if(!L) continue;
                const cap=L.states[0].caption||''; const m=cap.match(/정답 ([^<\\s]+)/); if(m && L.states[1] && L.states[1].san!==m[1]) bad++; } return bad;})()""")
            check("정답 수와 정답 수순의 첫 수가 같다", mis == 0, f"불일치 {mis}")
            if co.get("cats"):
                check("유형 카드 수와 순서가 데이터와 같다", c.ev("[...document.querySelectorAll('#s-cats .cat')].map(e=>e.id.slice(4))") == [x["key"] for x in co["cats"]])
                snap("cats")
                k2 = co["cats"][1]["key"] if len(co["cats"]) > 1 else co["cats"][0]["key"]
                c.tap(f'#cat-{k2} .cath'); c.pump(0.5)
                check("다른 유형을 누르면 그것만 펼쳐진다", c.ev("[...document.querySelectorAll('#s-cats .cat.open')].map(e=>e.id)") == ["cat-" + k2]
                      and c.ev(f"document.querySelectorAll('#cat-{k2} .diag li').length") >= 1 and c.ev(f"!!document.querySelector('#cat-{k2} .rule')"))
                c.tap(f'#cat-{k2} [data-cattrend]'); ok = c.wait("document.querySelector('#sheet').classList.contains('open') && !!document.querySelector('#sheet .verdict')", 3)
                check("유형의 추이 분석 시트", ok, c.ev("document.querySelector('#sheet-title').textContent")); c.tap("#sheet-x", None); c.pump(0.4)
            c.ev("window.scrollTo(0,0)"); c.tap('#subtabs button[data-sub="open"]', None); c.pump(0.5)
            check("오프닝별 보기로 전환", c.ev("!document.querySelector('#s-open').hidden && document.querySelector('#s-cats').hidden") and set(c.ev(VIS)) == {"mistakes"})
            o = c.ev(OVER); check("가로 넘침 없음 (오프닝별)", o[0] <= o[1], o)
            ops = S["openings"].get("w") or []
            if ops:
                check("오프닝 프로필: 15수 안 실수와 수별 막대", str(ops[0]["mist"]["per_game"]) in (c.ev("document.querySelector('#op-w .tiles3')?.innerText") or "")
                      and c.ev("document.querySelectorAll('#op-w .mhist rect').length") == sum(1 for v in ops[0]["mist"]["by_move"] if v), c.ev("document.querySelector('#op-w .tiles3')?.innerText.replace(/\\n/g,' ').slice(0,60)"))
                snap("openings")
            if c.ev("!!document.querySelector('.opitem[data-op=\"w\"][data-i=\"1\"]')"):
                c.tap('.opitem[data-op="w"][data-i="1"]')
                check("오프닝 선택 전환", c.ev("document.querySelector('.opitem[data-op=\"w\"][data-i=\"1\"]').classList.contains('on')")
                      and str(ops[1]["mist"]["per_game"]) in (c.ev("document.querySelector('#op-w .tiles3')?.innerText") or ""))
            c.ev("window.scrollTo(0,0)"); c.tap('#subtabs button[data-sub="worst"]', None); c.pump(0.5)
            check("큰 실수 보기로 전환", c.ev("!document.querySelector('#s-worst').hidden && document.querySelector('#s-open').hidden"))
            c.tap('#subtabs button[data-sub="cats"]', None); c.pump(0.4)
        if tab == "stats":
            R = S.get("repertoire") or {}
            nrows = sum(len(R[cc][sd]) for cc in "wb" for sd in ("mine", "opp") if R.get(cc) and R[cc].get("base"))
            if nrows:
                check("오프닝 성적표: 묶음 수가 데이터와 같다", c.ev("document.querySelectorAll('#s-rep .oprow').length") >= nrows, nrows)
                r0 = R["w"]["mine"][0]
                check("오프닝 성적표: 첫 줄의 승률", f"{r0['score']}%" == c.ev("document.querySelector('#s-rep .oprow[data-rep=\"w|mine|0\"] .os b').textContent"), r0["key"])
                snap("rep")
                c.tap('#s-rep .repcard:not(#rep-sum) .oprow[data-rep="w|mine|0"]'); ok = c.wait("document.querySelector('#sheet').classList.contains('open') && document.querySelectorAll('#sheet .diag li').length>0", 3)
                check("오프닝을 누르면 코칭 시트: 판정·진단·할 일", ok and r0["key"] in c.ev("document.querySelector('#sheet-title').textContent") and c.ev("!!document.querySelector('#sheet .verdict')")
                      and c.ev("document.querySelectorAll('#sheet .tiles3 .tile').length") == 3, c.ev("document.querySelector('#sheet .verdict')?.innerText.slice(0,60)"))
                o = c.ev("[document.querySelector('#sheet-body').scrollWidth, document.querySelector('#sheet-body').clientWidth]"); check("가로 넘침 없음 (오프닝 코칭)", o[0] <= o[1], o)
                if r0["trouble"]:
                    c.tap("#sheet [data-expand]"); check("코칭 시트의 반복 실수: 보드가 그려진다", c.wait("!!document.querySelector('#sheet .viewer svg.board')", 3))
                snap("rep_sheet")
                c.tap("#sheet-x", None); c.pump(0.4)
            check("취약·강점 오프닝 요약이 통계 탭에 있다", not nrows or c.ev("!document.querySelector('#s-coach .oprow') && !document.querySelector('#s-open .oprow[data-rep]')"))
            cut = c.ev("[...document.querySelectorAll('#main>section:not([hidden]) .bar span')].filter(s=>s.getBoundingClientRect().width>0 && s.getBoundingClientRect().right > s.closest('.card').getBoundingClientRect().right-4).length")
            check("막대 옆 글씨가 카드 안에 들어온다", cut == 0, cut)
            snap("stats")
    c.ev("history.back()"); c.pump(0.8)
    check("뒤로 가기로 이전 탭", c.ev("document.querySelector('#tabbar a.on')?.dataset.tab") == "mistakes")
    c.tap('#tabbar a[data-tab="home"]', None); c.pump(0.8)
    c.tap("#tbtn", None); c.tap('.sw[data-mode="light"]')
    check("밝은 톤 적용", c.ev("document.documentElement.dataset.mode") == "light"); snap("light")
    c.go(base + "index.html" + q(), READY)
    check("밝은 톤이 새로고침 뒤에도 유지", c.ev("document.documentElement.dataset.mode") == "light")
    c.tap("#tbtn", None); c.tap('.sw[data-mode="dark"]'); check("짙은 톤으로 복귀", (c.ev("document.documentElement.dataset.mode") or "dark") == "dark")
    c.go(base + "index.html#stats", READY); v = c.ev(VIS); check("주소의 #stats 로 바로 열기", v and set(v) == {"stats"})
    errs = c.errors(); check("대시보드에서 오류 없음", not errs, errs[:4])

    # ------------------------------------------------------------ 게임 페이지
    print("== 게임 페이지")
    gid = S["recent"][0]["url"].rstrip("/").rsplit("/", 1)[-1]
    G = fetch_json(f"games/{gid}.json"); n = len(G["plies"]); ply = min(17, n)
    CUR = "+(document.querySelector('#strip .mv.cur')?.dataset.jump||0)"
    check("게임 페이지가 뜬다", c.go(base + f"game.html?id={gid}&ply={ply}" + q("?"), "!!document.querySelector('#board svg.board')"))
    check("주소의 ply 로 그 수에서 시작", c.ev(CUR) == ply, c.ev(CUR))
    o = c.ev(OVER); check("가로 넘침 없음 (게임)", o[0] <= o[1], o)
    c.pump(1.5)
    s = c.ev("(()=>{const st=document.querySelector('#strip'),m=st.querySelector('.mv.cur'); const a=st.getBoundingClientRect(), b=m.getBoundingClientRect(); return [a.left,a.right,b.left,b.right]})()")
    check("현재 수가 수 스트립에 보인다", s and s[2] >= s[0] - 1 and s[3] <= s[1] + 1, s)
    cats = sorted({p["cat"] for p in G["plies"] if p.get("cat")})
    check("이 판의 교훈: 유형별로 묶인다", c.ev("document.querySelectorAll('#lessons .lesson').length") == len(cats) and c.ev("document.querySelectorAll('#lessons .lmv').length") == sum(1 for p in G["plies"] if p.get("cat")),
          f"{len(cats)}유형")
    if cats:
        c.tap("#lessons .lmv", y_target=640); j = c.ev("+document.querySelector('#lessons .lmv').dataset.jump")
        check("교훈의 수를 누르면 그 장면으로 가고 유형이 표시된다", c.ev(CUR) == j and c.ev("!!document.querySelector('#info .ctag')"), c.ev("document.querySelector('#info .ctag')?.textContent"))
        snap("game_lessons")
        c.ev(f"document.querySelector('#strip .mv[data-jump=\"{ply}\"]').click()"); c.pump(0.3)
    c.tap(".stick .vctl [data-go='1']", None); check("다음 수", c.ev(CUR) == min(n, ply + 1))
    c.tap(".stick .vctl [data-go='0']", None); check("처음으로", c.ev(CUR) == 0)
    c.tap(".stick .vctl [data-go='9']", None); check("끝으로", c.ev(CUR) == n)
    Y = 640   # 고정된 보드 아래에서 누른다
    lab0 = c.ev("[...document.querySelectorAll('#board svg text')].map(t=>t.textContent).join('')"); c.tap("#optflip", y_target=Y)
    check("판 뒤집기", lab0 != c.ev("[...document.querySelectorAll('#board svg text')].map(t=>t.textContent).join('')")); c.tap("#optflip", y_target=Y)
    c.tap("#graph", y_target=Y, fx=0.25); check("평가 그래프를 누르면 그 수로", abs(c.ev(CUR) - n * 0.25) <= 2, c.ev(CUR))
    if any(p.get("clock") is not None for p in G["plies"]):
        check("시계 그래프가 있다", c.ev("document.querySelectorAll('#cchart path').length") >= 2 and c.ev("document.querySelectorAll('.legend .lk').length") == 2)
        c.tap("#cchart", y_target=Y, fx=0.5)
        check("시계 그래프를 누르면 그 수로 가고 두 시계 값이 뜬다", abs(c.ev(CUR) - n * 0.5) <= max(3, n * 0.12) and c.ev("document.querySelectorAll('#cchart ~ .tip.on .row').length") == 2,
              f"cur={c.ev(CUR)} / {n}, tip='{c.ev(TIP('cchart'))}'")
        cx = c.ev("+document.querySelector('#ccur').getAttribute('x1')"); c.tap(".stick .vctl [data-go='1']", None)
        check("시계 그래프의 현재 수 표시선이 따라 움직인다", c.ev("+document.querySelector('#ccur').getAttribute('x1')") > cx)
        snap("game_clock")
    if c.ev("!!document.querySelector('.key[data-jump]')"):
        c.tap(".key[data-jump]", y_target=Y); check("핵심 실수를 누르면 그 장면으로", c.ev(CUR) == c.ev("+document.querySelector('.key[data-jump]').dataset.jump"))
    c.tap(f".mlist .mv[data-jump='{min(n, 21)}']", y_target=Y); check("수 목록에서 이동", c.ev(CUR) == min(n, 21))
    b = c.ev("(()=>{const r=document.querySelector('#board svg.board').getBoundingClientRect(); return [Math.round(r.top),Math.round(r.bottom),window.innerHeight]})()")
    check("스크롤해도 보드가 화면에 남는다", b[0] >= 0 and b[1] <= b[2], b)
    c.ev("window.scrollTo({top:0,behavior:'instant'})"); c.pump(0.4); r = c.rect("#board svg.board", None); cur0 = c.ev(CUR)
    c.call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": r[0] + 60, "y": r[1]}]); c.call("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": r[0] - 40, "y": r[1]}])
    c.call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[]); c.pump(0.4)
    check("보드를 왼쪽으로 밀면 다음 수", c.ev(CUR) == min(n, cur0 + 1), f"{cur0} → {c.ev(CUR)}")
    errs = c.errors(); check("게임 페이지에서 오류 없음", not errs, errs[:4])
    c.go(base + "game.html?id=999" + q("?"), "!!document.querySelector('#main .empty')"); check("없는 게임은 안내문", "찾을 수 없습니다" in (c.ev("document.querySelector('#main').textContent") or "")); c.errors()

    # ------------------------------------------------------------ 퍼즐
    print("== 퍼즐")
    import chess
    BYID = {p["id"]: p for p in puzzles}
    LS = lambda k: f"JSON.parse(localStorage.getItem('{k}')||'null')"
    PZREADY = "!!document.querySelector('#pzboard svg.board') || !!document.querySelector('#main .empty') || !!document.querySelector('#main .done')"

    def current():
        dom = c.ev("[...document.querySelectorAll('#pzboard svg.board use')].filter(u=>u.hasAttribute('x')).map(u=>[u.getAttribute('href').split('-').pop(), +u.getAttribute('x'), +u.getAttribute('y')])")
        dom = set(map(tuple, dom or []))
        td = c.ev(LS("puzzle-day")) or {}
        p = (td.get("pz") or {}).get((td.get("ids") or [None] * 99)[td.get("idx", 0)] if td.get("ids") and td.get("idx", 0) < len(td["ids"]) else None)
        return p if p and fen_set(p["fen"], p["color"] == "b") == dom else None

    def sq_xy(p, sq):
        r = c.ev("(()=>{const r=document.querySelector('#pzboard svg.board').getBoundingClientRect(); return [r.left,r.top,r.width]})()")
        fx, ry = FILES.index(sq[0]), 8 - int(sq[1])
        if p["color"] == "b":
            fx, ry = 7 - fx, 7 - ry
        return r[0] + (fx + 0.5) * r[2] / 8, r[1] + (ry + 0.5) * r[2] / 8

    def tap_sq(p, sq):
        c.tap_xy(*sq_xy(p, sq))

    def center_board():
        c.ev("document.querySelector('#pzboard').scrollIntoView({block:'center',behavior:'instant'})"); c.pump(0.3)

    if not puzzles:
        check("퍼즐이 없으면 안내문", c.go(base + "puzzle.html" + q(), PZREADY) and c.ev("!!document.querySelector('#main .empty')"))
    else:
        check("퍼즐 페이지가 뜬다", c.go(base + "puzzle.html" + q(), "!!document.querySelector('#pzboard svg.board')"))
        o = c.ev(OVER); check("가로 넘침 없음 (퍼즐)", o[0] <= o[1], o)
        td0 = c.ev(LS("puzzle-day")); check("오늘의 묶음이 저장된다", td0 and len(td0["ids"]) == td0["daily"] <= 10 and all(i in td0["pz"] for i in td0["ids"]), f"{td0 and td0['daily']}문제")
        center_board(); p = current(); check("화면의 국면이 저장된 첫 문제와 같다", p, p and (p["id"], p["best"], [a["san"] for a in p.get("alts", [])]))
        board = chess.Board(p["fen"]); frm, to = p["best_uci"][:2], p["best_uci"][2:4]
        tap_sq(p, frm)
        dots = c.ev("document.querySelectorAll('#pzboard svg.board > circle').length"); legal_from = len({m.uci()[:4] for m in board.legal_moves if m.uci()[:2] == frm})
        check("내 기물을 누르면 갈 수 있는 칸이 표시된다", dots == legal_from and c.ev("document.querySelectorAll('#pzboard svg.board rect[fill=\"var(--sq-hl)\"]').length") == 1, f"{dots} == {legal_from}")
        own = {(x, y) for (pc, x, y) in fen_set(p["fen"], False) if pc[0] == p["color"]}
        legal4 = {m.uci()[:4] for m in board.legal_moves}
        illegal = next((f + str(r) for r in range(1, 9) for f in FILES if (FILES.index(f) * 100, (8 - r) * 100) not in own and frm + f + str(r) not in legal4), None)
        tap_sq(p, illegal)
        check("둘 수 없는 칸을 누르면 채점하지 않고 안내만 한다", c.ev("!document.querySelector('#pzresult .result')") and c.ev("document.querySelector('#pztoast').classList.contains('on')")
              and c.ev("document.querySelectorAll('#pzboard svg.board rect[fill=\"var(--sq-hl)\"]').length") == 1, f"{frm}{illegal}")
        accepted = {p["best_uci"][:4]} | {x["uci"][:4] for x in p.get("alts", [])}
        wrong = next((m for m in sorted(legal4) if m not in accepted and m[:2] == frm), None) or next(m for m in sorted(legal4) if m not in accepted)
        if wrong[:2] != frm:
            tap_sq(p, wrong[:2])
        tap_sq(p, wrong[2:4]); c.pump(0.5)
        check("둘 수 있지만 나쁜 수는 오답", c.ev("!!document.querySelector('#pzresult .result.ng')"), c.ev("document.querySelector('#pzresult .result')?.innerText.slice(0,46)"))
        check("진행 점과 기록이 바로 갱신된다", c.ev("document.querySelectorAll('.prog .dots i.ng').length") == 1 and "0 / 1" in (c.ev("document.querySelector('.streakcard').innerText") or ""),
              (c.ev("document.querySelector('.streakcard').innerText") or "").replace("\n", " ")[:60])
        rv = c.ev(LS("puzzle-review")) or {}
        check("틀린 문제가 내일 복습으로 잡힌다", p["id"] in rv and rv[p["id"]]["step"] == 0 and "복습으로 다시" in (c.ev("document.querySelector('#pzresult').innerText") or ""), rv.get(p["id"], {}).get("due"))
        check("정답 수순 뷰어가 붙는다", c.ev("!!document.querySelector('#pzresult .viewer svg.board')"))
        snap("puzzle_wrong")
        hist0 = c.ev(LS("puzzle-history"))
        c.go(base + "puzzle.html" + q(), "!!document.querySelector('#pzboard svg.board')"); c.pump(0.4)
        check("새로고침하면 푼 상태로 열리고 다시 채점되지 않는다", "이미 푼 문제" in (c.ev("document.querySelector('#pzresult')?.innerText") or "") and c.ev(LS("puzzle-history")) == hist0)
        center_board(); tap_sq(p, frm); tap_sq(p, to); c.pump(0.3)
        check("푼 문제는 다시 눌러도 기록이 늘지 않는다", c.ev(LS("puzzle-history")) == hist0)
        c.tap("#next"); c.pump(0.6)
        check("다음 문제로", "2 / " in (c.ev("document.querySelector('.prog').innerText") or ""))
        center_board(); p2 = current(); check("둘째 문제 확인", p2 and p2["id"] != p["id"], p2 and (p2["id"], p2["best"], [x["san"] for x in p2.get("alts", [])]))
        use = (p2.get("alts") or [None])[0]
        mv = use["uci"] if use else p2["best_uci"]
        tap_sq(p2, mv[:2]); tap_sq(p2, mv[2:4]); c.pump(0.5)
        txt = c.ev("document.querySelector('#pzresult .result')?.innerText") or ""
        check("정답" + (" (최선과 비슷한 다른 수도 인정)" if use else ""), c.ev("!!document.querySelector('#pzresult .result.ok')") and (not use or "도 좋은 수" in txt), txt[:50])
        check("정답이면 보드에 표시가 붙는다", "ok" in (c.ev("document.querySelector('#pzboard').className") or ""))
        snap("puzzle_ok")
        c.tap("#next"); c.pump(0.5); c.tap("#giveup"); c.pump(0.5)
        check("모르겠어요: 정답 공개", "정답 공개" in (c.ev("document.querySelector('#pzresult .result')?.innerText") or ""))
        # 하루 중 puzzles.json 이 바뀌어도 오늘의 문제는 그대로인지: 응답을 바꿔치기해서 확인
        td1 = c.ev(LS("puzzle-day"))
        c.call("Network.setBypassServiceWorker", bypass=True); c.call("Network.setCacheDisabled", cacheDisabled=True)
        fake = base64.b64encode(json.dumps(list(reversed(puzzles))[: max(1, len(puzzles) - 7)]).encode()).decode()

        def on_event(m):
            if m.get("method") == "Fetch.requestPaused":
                c.send("Fetch.fulfillRequest", requestId=m["params"]["requestId"], responseCode=200,
                       responseHeaders=[{"name": "Content-Type", "value": "application/json"}], body=fake)
        c.on_event = on_event
        c.call("Fetch.enable", patterns=[{"urlPattern": "*puzzles.json*"}])
        c.go(base + "puzzle.html" + q(), PZREADY); c.pump(0.4)
        td2 = c.ev(LS("puzzle-day"))
        check("새 게임으로 퍼즐 목록이 바뀌어도 오늘의 문제와 진행은 그대로", td2 and td2["ids"] == td1["ids"] and td2["idx"] == td1["idx"] and td2["res"] == td1["res"])
        c.call("Fetch.disable"); c.on_event = None; c.call("Network.setBypassServiceWorker", bypass=False); c.call("Network.setCacheDisabled", cacheDisabled=False)
        # 복습 문제가 다음 날 먼저 나오는지: 기한이 지난 복습 항목만 남기고 오늘의 묶음을 지운다
        c.ev(f"(()=>{{const r={LS('puzzle-review')}; for(const k in r) r[k].due='2000-01-01'; localStorage.setItem('puzzle-review',JSON.stringify(r)); localStorage.removeItem('puzzle-day');}})()")
        c.go(base + "puzzle.html" + q(), "!!document.querySelector('#pzboard svg.board')"); c.pump(0.4)
        td3 = c.ev(LS("puzzle-day")); due_ids = set((c.ev(LS("puzzle-review")) or {}).keys())
        check("기한이 된 복습 문제가 먼저 나오고 '복습' 표시가 붙는다", td3["ids"][0] in due_ids and c.ev("document.querySelector('.task .rv')?.textContent") == "복습", td3["ids"][0])
        center_board(); pr = current(); tap_sq(pr, pr["best_uci"][:2]); tap_sq(pr, pr["best_uci"][2:4]); c.pump(0.5)
        rv2 = c.ev(LS("puzzle-review")) or {}
        check("복습을 맞히면 다음 간격(3일 뒤)으로 넘어간다", rv2.get(pr["id"], {}).get("step") == 1, rv2.get(pr["id"], {}).get("due"))
        # 오늘의 묶음을 다 풀면 끝 화면
        c.ev(f"(()=>{{const d={LS('puzzle-day')}; d.idx=d.daily; d.cont=false; localStorage.setItem('puzzle-day',JSON.stringify(d));}})()")
        c.go(base + "puzzle.html" + q(), PZREADY)
        check("오늘의 묶음을 마치면 끝 화면", "오늘의 퍼즐 끝" in (c.ev("document.querySelector('#main').innerText") or ""))
        c.tap("#more"); c.pump(0.6)
        check("더 풀기로 추가 문제", c.ev("!!document.querySelector('#pzboard svg.board')") or "모두 풀었습니다" in (c.ev("document.querySelector('#main').innerText") or ""), (c.ev("document.querySelector('.prog')?.innerText") or "").replace("\n", " "))
        pcats = {}
        for x in puzzles:
            if x.get("cat"):
                pcats[x["cat"]] = pcats.get(x["cat"], 0) + 1
        if pcats:
            k = max(pcats, key=pcats.get); day0 = c.ev(LS("puzzle-day")); hist1 = c.ev(LS("puzzle-history"))
            check("유형 연습 페이지가 뜬다", c.go(base + f"puzzle.html?cat={k}" + q("?"), "!!document.querySelector('#pzboard svg.board')")
                  and f"/ {pcats[k]}" in (c.ev("document.querySelector('.prog').innerText") or ""), (c.ev("document.querySelector('.prog').innerText") or "").replace("\n", " "))
            o = c.ev(OVER); check("가로 넘침 없음 (유형 연습)", o[0] <= o[1], o)
            td = c.ev("JSON.parse(sessionStorage.getItem('puzzle-practice'))")
            check("유형 연습은 그 유형의 퍼즐만 낸다", td and len(td["ids"]) == pcats[k] and all(BYID[i]["cat"] == k for i in td["ids"]))
            pp = td["pz"][td["ids"][0]]; center_board(); tap_sq(pp, pp["best_uci"][:2]); tap_sq(pp, pp["best_uci"][2:4]); c.pump(0.5)
            check("유형 연습 채점: 정답과 유형·규칙 표시", c.ev("!!document.querySelector('#pzresult .result.ok')") and c.ev("!!document.querySelector('#pzresult .result .ctag')"))
            hist2 = c.ev(LS("puzzle-history"))
            check("유형 연습은 오늘의 묶음을 건드리지 않고 기록에는 남는다", c.ev(LS("puzzle-day")) == day0 and sum(h["n"] for h in hist2.values()) == sum(h["n"] for h in hist1.values()) + 1)
            snap("puzzle_practice")
            check("모드 칩으로 오늘의 퍼즐로 돌아간다", c.ev("document.querySelector('.pzmodes a').getAttribute('href')") == "puzzle.html" and c.ev("document.querySelector('.pzmodes a.on')?.getAttribute('href')") == f"puzzle.html?cat={k}")
        errs = c.errors(); check("퍼즐 페이지에서 오류 없음", not errs, errs[:4])
        c.go(base + "index.html" + q(), "!!document.querySelector('.pz')")
        check("홈의 퍼즐 카드에 연속 일수", "연속" in (c.ev("document.querySelector('.pz').innerText") or ""))

    # ------------------------------------------------------------ 설치형 웹앱
    print("== 설치형 웹앱")
    c.go(base + "index.html" + q(), READY)
    check("서비스 워커가 등록되고 활성화된다", c.wait("navigator.serviceWorker.getRegistration().then(r=>!!(r&&r.active))", 10))
    man = c.ev("fetch(document.querySelector('link[rel=manifest]').href).then(r=>r.json()).then(m=>[m.display,m.icons.length,m.start_url])")
    check("매니페스트", man and man[0] == "standalone" and man[1] >= 2, man)
    icons = c.ev("Promise.all(['icon-192.png','icon-512.png','apple-touch-icon.png'].map(u=>fetch(u).then(r=>r.status)))")
    check("아이콘 파일", icons == [200, 200, 200], icons)
    for page, ready in (("index.html", READY), (f"game.html?id={gid}", "!!document.querySelector('#board svg.board')"), ("puzzle.html", PZREADY)):
        c.go(base + page, ready)   # 오프라인용으로 한 번씩 받아 둔다
    c.go(base + "index.html", READY); c.wait("navigator.serviceWorker.controller!==null", 5)
    if server:
        server.stop(); c.pump(0.5)
        check("오프라인: 대시보드가 마지막 화면으로 뜬다", c.go(base + "index.html", READY, 25) and c.ev("!!document.querySelector('.herocard .big')"))
        check("오프라인: 게임 페이지", c.go(base + f"game.html?id={gid}&ply=3", "!!document.querySelector('#board svg.board')", 25))
        check("오프라인: 퍼즐 페이지", c.go(base + "puzzle.html", PZREADY, 25))
        server.start()
    c.errors()
    c.viewport(360, 640); c.go(base + "index.html" + q(), READY); c.pump(0.4)
    o = c.ev(OVER); check("가로 넘침 없음 (작은 폰 360px)", o[0] <= o[1], o)
    c.go(base + f"game.html?id={gid}&ply=5" + q("?"), "!!document.querySelector('#board svg.board')")
    check("화면이 낮으면 보드 고정을 끈다", c.ev("getComputedStyle(document.querySelector('.stick')).position") == "static")
    c.viewport(1280, 800, mobile=False); c.go(base + "index.html" + q(), READY); c.pump(0.4); snap("desktop")


if __name__ == "__main__":
    main()
