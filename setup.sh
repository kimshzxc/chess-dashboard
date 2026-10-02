#!/usr/bin/env bash
# 로컬에서 시험하려고 처음 한 번 실행: venv, 의존성, 스톡피시 다운로드.
# 평소 운영은 GitHub Actions 가 한다. 이 컴퓨터에서 직접 돌리려면 --cron 을 붙인다 (Actions 와 동시에 쓰면 알림이 두 번 온다).
set -e
cd "$(dirname "$0")"

echo "== 1. Python 가상환경 =="
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

echo "== 2. 스톡피시 =="
mkdir -p engine
if [ ! -x engine/stockfish ]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)  asset=stockfish-linux-x86-64-universal.tar.gz ;;
    Linux-aarch64) asset=stockfish-linux-arm64-universal.tar.gz ;;
    Darwin-*)      asset=stockfish-macos-universal.tar.gz ;;
    *) echo "지원하지 않는 플랫폼입니다. engine/stockfish 에 바이너리를 직접 넣으세요."; exit 1 ;;
  esac
  tag=$(curl -sL https://api.github.com/repos/official-stockfish/Stockfish/releases/latest | grep -o '"tag_name": *"[^"]*"' | cut -d'"' -f4)
  echo "  다운로드 $tag / $asset"
  curl -sL -o engine/sf.tgz "https://github.com/official-stockfish/Stockfish/releases/download/$tag/$asset"
  tar -xzf engine/sf.tgz -C engine
  bin=$(find engine -type f -name 'stockfish-*' ! -name '*.tgz' | head -1)
  mv "$bin" engine/stockfish && chmod +x engine/stockfish && rm -rf engine/sf.tgz engine/stockfish-*/ 2>/dev/null || true
fi
(echo uci; echo quit) | ./engine/stockfish | head -1

echo "== 3. 설정 파일 =="
if [ ! -f .env ]; then
  cat > .env <<'EOF'
CHESSCOM_USERNAME=
GITHUB_OWNER=
GITHUB_REPO=chess-dashboard
GITHUB_TOKEN=
NTFY_TOPIC=
EOF
  chmod 600 .env
  echo "  .env 를 만들었습니다. 값을 채운 뒤 다시 실행하세요."; exit 0
fi
echo "  .env 있음"

mkdir -p logs data docs
if [ "${1:-}" = "--cron" ]; then
  echo "== 4. 크론 등록 (10분마다) =="
  echo "  주의: GitHub Actions 감시를 켜 둔 채로 쓰면 같은 게임 알림이 두 번 옵니다."
  job="*/10 * * * * cd $PWD && ./venv/bin/python pipeline.py >> logs/cron.log 2>&1"
  { crontab -l 2>/dev/null | grep -v 'chess-dashboard/venv/bin/python pipeline.py' || true; echo "$job"; } | crontab -
  crontab -l | grep pipeline.py
else
  echo "== 4. 크론은 등록하지 않았습니다 (운영은 GitHub Actions). 이 컴퓨터에서 돌리려면: bash setup.sh --cron =="
fi
echo "완료. 최신 데이터 받기: ./venv/bin/python tools/gh_pull.py   로컬 시험: ./venv/bin/python pipeline.py --render-only"
