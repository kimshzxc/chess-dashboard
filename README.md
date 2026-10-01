# chess-dashboard

체스닷컴 래피드 기보를 10분마다 자동 수집해 스톡피시로 분석하고, 통계 대시보드를 GitHub Pages에 올리며, 게임이 끝날 때마다 휴대폰(ntfy)으로 요약을 보냅니다.

## 구성

| 파일 | 역할 |
|---|---|
| `pipeline.py` | 수집 → 분석 → 통계 → 대시보드 생성 → 알림 → GitHub 업로드 (크론이 실행) |
| `render.py` | 통계 JSON을 모바일 대시보드 HTML로 변환 |
| `setup.sh` | 새 환경 초기 설치 (venv, 스톡피시, 크론) |
| `import_existing.py` | 예전 분석 결과를 DB로 가져오기 (1회용) |
| `check_env.sh` | `.env` 값과 토큰/알림 연결 확인 |
| `.env` | 사용자명, GitHub 토큰, ntfy 주제 (git에 올라가지 않음) |
| `data/chess.db` | 모든 게임과 수별 분석 결과 (SQLite). 이 파일만 복사하면 이식 완료 |
| `docs/` | 생성된 대시보드. GitHub Pages가 이 폴더를 서비스 |
| `.github/workflows/pipeline.yml` | GitHub Actions 스케줄 (10분마다 서버에서 실행) |
| `logs/cron.log` | 실행 기록 |

## 명령

```
./venv/bin/python pipeline.py               # 전체 실행
./venv/bin/python pipeline.py --render-only # 대시보드만 다시 만들어 업로드
./venv/bin/python pipeline.py --no-push --no-notify   # 로컬 테스트
tail -f logs/cron.log                       # 크론 로그 보기
```

## GitHub Actions 운영 (기본)

`.github/workflows/pipeline.yml` 이 10분마다 GitHub 서버에서 파이프라인을 돌립니다. 로컬 컴퓨터를 켜 둘 필요가 없습니다.

- 저장소 Settings → Secrets and variables → Actions 에 `CHESSCOM_USERNAME`, `NTFY_TOPIC` 두 개가 있어야 합니다.
- `data/chess.db` 와 `docs/` 는 실행이 끝날 때마다 저장소에 커밋됩니다. 스톡피시는 첫 실행 때 내려받아 캐시합니다.
- Actions 탭 → chess pipeline → Run workflow 로 수동 실행할 수 있고, "대시보드만 다시 생성"을 켜면 `--render-only` 와 같습니다.
- 코드를 고치면 `pipeline.py`, `render.py` 를 커밋하기만 하면 다음 실행에서 대시보드가 다시 만들어집니다 (`docs/.code-hash` 로 변경을 감지).
- 로컬에서도 돌릴 수는 있지만, Actions 와 동시에 돌리면 DB 가 갈라지므로 둘 중 하나만 쓰세요. 로컬에서 쓰려면 먼저 저장소에서 최신 `data/chess.db` 를 받아오세요.
- GitHub 스케줄은 정확하지 않아 10~30분 늦게 돌 수 있습니다.

## 다른 컴퓨터로 옮기기

1. 이 폴더 전체(`venv/`, `engine/` 제외 가능)를 복사
2. `bash setup.sh` 실행 (venv, 스톡피시 다운로드, 크론 등록)
3. `.env` 채우기 → `bash check_env.sh` 로 확인
4. `./venv/bin/python pipeline.py`

`data/chess.db` 를 함께 복사하면 기존 분석을 다시 돌리지 않습니다.

## 분석 기준

- Stockfish 19, depth 14, 모든 수 평가
- 대실수: 100분율 승률 기준이 아닌 센티폰 300 이상 손실. 실수: 100~299. 정확도: 리체스 공식
- 기물 방치: 내 수 다음 상대 최선수가 내 기물(폰 제외)을 잡는 경우
- 오프닝 = 1~10수, 엔드게임 = 폰과 킹 제외 기물 가치 합 14 이하
