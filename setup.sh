#!/usr/bin/env bash
# 새 컴퓨터/서버에서 처음 한 번 실행: venv, python-chess, 스톡피시 다운로드, 크론 등록.
set -e
cd "$(dirname "$0")"

echo "== 1. Python 가상환경 =="
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip chess

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

echo "== 4. 크론 등록 (10분마다) =="
job="*/10 * * * * cd $PWD && ./venv/bin/python pipeline.py >> logs/cron.log 2>&1"
mkdir -p logs data docs
{ crontab -l 2>/dev/null | grep -v 'chess-dashboard/venv/bin/python pipeline.py' || true; echo "$job"; } | crontab -
crontab -l | grep pipeline.py
echo "완료. 첫 실행: ./venv/bin/python pipeline.py"
