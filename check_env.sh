#!/usr/bin/env bash
# .env 값 형식, GitHub 토큰 권한, ntfy 알림 전송을 확인합니다. 토큰 값은 출력하지 않습니다.
cd "$(dirname "$0")" || exit 1

echo "== 1. .env 형식 검사 =="
bad=0
while IFS= read -r line; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  if [[ "$line" == *" = "* || "$line" == *"= "* || "$line" == *" ="* ]]; then echo "  등호 옆 공백: ${line%%=*}"; bad=1; fi
  if [[ "$line" == *\"* || "$line" == *\'* ]]; then echo "  따옴표 포함: ${line%%=*}"; bad=1; fi
  if [[ "$line" == *"여기에"* ]]; then echo "  아직 안 채움: ${line%%=*}"; bad=1; fi
done < .env
[[ $bad -eq 0 ]] && echo "  형식 OK"

set -a; . ./.env; set +a
echo "  CHESSCOM_USERNAME=$CHESSCOM_USERNAME"
echo "  GITHUB_OWNER=$GITHUB_OWNER  GITHUB_REPO=$GITHUB_REPO"
echo "  NTFY_TOPIC=$NTFY_TOPIC"
echo "  GITHUB_TOKEN: 앞 11자=${GITHUB_TOKEN:0:11}  길이=${#GITHUB_TOKEN}"
[[ "${GITHUB_TOKEN:0:11}" == "github_pat_" || "${GITHUB_TOKEN:0:4}" == "ghp_" ]] || echo "  경고: 토큰이 github_pat_ 또는 ghp_ 로 시작하지 않음"

echo "== 2. GitHub 저장소 접근 =="
resp=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/$GITHUB_OWNER/$GITHUB_REPO")
code=$(echo "$resp" | tail -1); body=$(echo "$resp" | sed '$d')
echo "  HTTP $code"
if [[ "$code" == "200" ]]; then
  echo "$body" | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("permissions",{}); print("  공개여부:", "private" if d["private"] else "public"); print("  기본 브랜치:", d["default_branch"]); print("  push 권한:", p.get("push"))'
elif [[ "$code" == "404" ]]; then
  echo "  저장소를 못 찾음: 아이디/저장소 이름이 틀렸거나 토큰에 이 저장소 접근 권한이 없음"
elif [[ "$code" == "401" ]]; then
  echo "  토큰 인증 실패: 토큰이 잘못 복사됐거나 만료됨"
fi

echo "== 3. 저장소 쓰기 권한 =="
echo "  위 2번의 'push 권한' 이 True 면 tools/gh_push.py 로 올릴 수 있습니다 (시험 파일은 만들지 않습니다)."
echo "  워크플로 파일을 고쳐 올리려면 토큰에 Workflows 쓰기 권한도 필요합니다."

echo "== 4. ntfy 알림 테스트 =="
ncode=$(curl -s -o /dev/null -w "%{http_code}" -H "Title: 체스 대시보드" \
  -d "설정 테스트 알림입니다. 이게 보이면 연결 성공." "https://ntfy.sh/$NTFY_TOPIC")
echo "  HTTP $ncode  (200이면 전송됨, 휴대폰 ntfy 앱에서 '$NTFY_TOPIC' 구독 후 확인)"
