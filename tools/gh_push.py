#!/usr/bin/env python3
"""git 없이 파일들을 GitHub 저장소 main 에 커밋 하나로 올린다 (.env 의 GITHUB_OWNER / GITHUB_REPO / GITHUB_TOKEN 사용).

  python tools/gh_push.py -m "메시지" pipeline.py docs/app.js ...       지정한 파일 올리기 (저장소 루트 기준 경로)
  python tools/gh_push.py -m "메시지" --delete old/file.txt ...          파일 지우기
  python tools/gh_push.py --changed                                     로컬과 저장소가 다른 추적 파일 목록만 보기

감시 워크플로가 같은 브랜치에 계속 커밋하므로, 브랜치가 그사이 움직였으면 최신 커밋 위에 다시 만들어 재시도한다.
감시 루프가 만드는 파일(data/chess.db, docs/stats.json, docs/puzzles.json, docs/games/, docs/pieces.svg, docs/.code-hash)은
로컬 것이 낡았을 수 있으니 올리지 않는다. 필요하면 --force-data 를 준다.
워크플로 파일(.github/workflows/)을 올리려면 토큰에 Workflows 쓰기 권한이 있어야 한다."""
import argparse, base64, hashlib, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = ("data/chess.db", "docs/stats.json", "docs/puzzles.json", "docs/coach.json", "docs/book.json", "docs/pieces.svg", "docs/.code-hash", "docs/.nojekyll", "docs/games/")


def env():
    cfg = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


class Repo:
    def __init__(self, cfg):
        self.base = f"/repos/{cfg['GITHUB_OWNER']}/{cfg['GITHUB_REPO']}"
        self.token = cfg["GITHUB_TOKEN"]

    def api(self, method, path, data=None):
        req = urllib.request.Request("https://api.github.com" + self.base + path, method=method,
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                                              "Content-Type": "application/json", "User-Agent": "chess-dashboard-tools"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def head(self):
        st, ref = self.api("GET", "/git/ref/heads/main")
        assert st == 200, ref
        st, c = self.api("GET", f"/git/commits/{ref['object']['sha']}")
        return ref["object"]["sha"], c["tree"]["sha"]

    def tree(self, sha):
        st, t = self.api("GET", f"/git/trees/{sha}?recursive=1")
        assert st == 200, t
        return {e["path"]: e["sha"] for e in t["tree"] if e["type"] == "blob"}


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("-m", "--message")
    ap.add_argument("--delete", nargs="*", default=[])
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--force-data", action="store_true")
    a = ap.parse_args()
    repo = Repo(env())
    if a.changed:
        _, tree_sha = repo.head()
        remote = repo.tree(tree_sha)
        for path, sha in sorted(remote.items()):
            local = os.path.join(ROOT, path)
            if path.startswith(GENERATED):
                continue
            if not os.path.exists(local):
                print("저장소에만 있음 ", path)
            elif blob_sha(open(local, "rb").read()) != sha:
                print("다름           ", path)
        return
    if not a.message or not (a.files or a.delete):
        ap.error("-m 메시지와 올릴 파일(또는 --delete)이 필요합니다")
    files = [os.path.relpath(os.path.abspath(f), ROOT) for f in a.files]
    blocked = [f for f in files if f.startswith(GENERATED)]
    if blocked and not a.force_data:
        sys.exit("감시 루프가 만드는 파일은 올리지 않습니다 (--force-data 로 강제): " + ", ".join(blocked))
    entries = []
    for f in files:
        data = open(os.path.join(ROOT, f), "rb").read()
        st, b = repo.api("POST", "/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        assert st == 201, (f, st, b)
        mode = "100755" if os.access(os.path.join(ROOT, f), os.X_OK) and f.endswith((".sh", ".py")) and f.startswith(("setup", "check", "tools/")) else "100644"
        entries.append({"path": f, "mode": mode, "type": "blob", "sha": b["sha"]})
    for f in a.delete:
        entries.append({"path": f, "mode": "100644", "type": "blob", "sha": None})
    for attempt in range(6):
        head, tree_sha = repo.head()
        st, t = repo.api("POST", "/git/trees", {"base_tree": tree_sha, "tree": entries})
        assert st == 201, (st, t)
        st, c = repo.api("POST", "/git/commits", {"message": a.message, "tree": t["sha"], "parents": [head]})
        assert st == 201, (st, c)
        st, r = repo.api("PATCH", "/git/refs/heads/main", {"sha": c["sha"]})
        if st == 200:
            print(f"커밋 {c['sha'][:8]} (부모 {head[:8]}) · 파일 {len(files)}개 올림, {len(a.delete)}개 삭제")
            return
        print(f"브랜치가 그사이 움직였습니다 ({st}). 다시 시도합니다")
        time.sleep(4)
    sys.exit("푸시 실패")


if __name__ == "__main__":
    main()
