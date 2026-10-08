#!/usr/bin/env python3
"""git 없이 저장소 main 의 최신 파일을 로컬로 받아온다 (.env 의 GITHUB_OWNER / GITHUB_REPO / GITHUB_TOKEN 사용).

  python tools/gh_pull.py            감시 루프가 만든 데이터만: data/chess.db, docs/stats.json, docs/puzzles.json, docs/games/ 등
  python tools/gh_pull.py --all      코드와 문서까지 전부 (로컬에서 고친 파일을 덮어쓴다. 먼저 gh_push.py --changed 로 확인)

로컬에서 파이프라인이나 화면을 시험하기 전에 실행하면, 로컬 DB 가 저장소와 갈라지지 않는다."""
import argparse, io, os, sys, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = ("data/chess.db", "docs/stats.json", "docs/puzzles.json", "docs/coach.json", "docs/book.json", "docs/pieces.svg", "docs/.code-hash", "docs/.nojekyll", "docs/games/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    cfg = {}
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    req = urllib.request.Request(f"https://api.github.com/repos/{cfg['GITHUB_OWNER']}/{cfg['GITHUB_REPO']}/tarball/main",
                                 headers={"Authorization": "Bearer " + cfg["GITHUB_TOKEN"], "User-Agent": "chess-dashboard-tools"})
    data = urllib.request.urlopen(req, timeout=300).read()
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            path = m.name.split("/", 1)[1] if "/" in m.name else m.name     # 맨 앞 폴더(owner-repo-sha) 제거
            if ".." in path.split("/") or path.startswith("/"):
                continue
            if not a.all and not path.startswith(GENERATED):
                continue
            dest = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(tar.extractfile(m).read())
            n += 1
    print(f"{n}개 파일을 받아왔습니다 ({'전체' if a.all else '데이터만'})")


if __name__ == "__main__":
    sys.exit(main())
