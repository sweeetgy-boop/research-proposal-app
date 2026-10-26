# 배포 (M6 Mac mini) — launchd + 127.0.0.1 바인딩 + 역프록시

## 전제 (보안 G·H)

- `rra api` 와 `mlx_lm.server` 는 **127.0.0.1 에만 바인딩**한다. 포트를 외부에 직접 열지 않는다.
- 외부(동료 PC)에서 쓰려면 **HTTPS 를 종단하는 역프록시 뒤**에서만 공개한다.
  권장: Tailscale(`tailscale serve https / http://127.0.0.1:8000`) 또는 Cloudflare Tunnel.
  역프록시가 TLS·접근 제어(Tailscale ACL / Cloudflare Access)를 맡고, 앱은 그 뒤에서도
  **자체 토큰(`RRA_API_TOKEN`)을 그대로 요구**한다 (이중 인증).
- 바인딩 주소는 `RRA_API_HOST`/`--host` 로 바꿀 수 있지만 기본은 127.0.0.1 이고, 다른 주소를 주면
  CLI 가 경고를 찍는다. `0.0.0.0` 은 역프록시 없이 쓰지 않는다.
- 비밀은 `.env`(권한 600)에만. plist 에 토큰을 적지 않는다 (`WorkingDirectory` 의 `.env` 를 읽는다).
- 파일 업로드 엔드포인트는 없다. 알리오 filedrop 은 로컬 폴더(`data/inbox/`)로만.

## REST API (`com.rra.api.plist`)

```bash
cp deploy/launchd/com.rra.api.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.rra.api.plist
curl -s http://127.0.0.1:8000/healthz                     # {"status":"ok"} — 인증 없이, 내부 정보 없음
curl -s -H "X-RRA-Token: $RRA_API_TOKEN" \
     -H 'content-type: application/json' \
     -d '{"current_state":"…","root_cause":"…","limitation":"…","goal":"…"}' \
     http://127.0.0.1:8000/v1/precheck
```

plist 의 경로는 이 저장소 위치(`/Users/chan/projects/research-proposal-app`)로 채워져 있다.
다른 위치에 두면 `ProgramArguments`·`WorkingDirectory`·`EnvironmentVariables`·로그 경로를 함께 바꾼다.

| 엔드포인트 | 설명 |
|---|---|
| `POST /v1/precheck` | 제안 입력 → 유사과제 경보 (`notice`, `blocking`, `alerts[]`) |
| `GET /v1/search?q=&k=&orgs=` | 하이브리드 검색. 청크마다 `trust: untrusted` |
| `POST /v1/runs` → 202 | 생성 큐 등록 `{run_id, status, progress, …}` (대기열 초과 429) |
| `GET /v1/runs/{id}` | 상태·step (초안 본문 없음) |
| `POST /v1/runs/{id}/resume` → 202 | 중단된 run 재개 |
| `GET /v1/runs/{id}/draft` | 문장별 근거가 붙은 초안 |
| `POST /v1/runs/{id}/confirm` | `{task_type?, utilization?[], strategy?[]}` 확정 |
| `GET /v1/runs/{id}/file` | HWPX (하단 제안자 칸 빈칸) |
| `POST /v1/runs/{id}/file` | 본문 `{proposed_on, proposer{rank,name,phone}, head{…}}` 로 제안자 정보를 넣은 HWPX — 파일에만 들어가고 서버에 저장되지 않는다 |

인증: 모든 `/v1/*` 에 `X-RRA-Token: <토큰>` 또는 `Authorization: Bearer <토큰>`. 없으면 401.
본문 상한: `config/security.yaml` `input_limits.api_max_body_bytes`(기본 64KB), 초과 413.
응답 헤더: `Content-Security-Policy: default-src 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. CORS 헤더는 없다(동일 출처만).

## LLM 서버 (보안 H)

`mlx_lm.server --host 127.0.0.1 --port 8080 --model <safetensors 모델>` 을 같은 방식의 launchd 에이전트로
띄운다(`com.rra.mlx.plist` 는 운영 모델이 확정되면 추가). 인증이 없으므로 외부 노출 금지.

## 보존 (보안 I)

`rra runs purge --dry-run` 으로 만료 run(`security.yaml retention_days`, 기본 180일)을 확인하고
`rra runs purge` 로 지운다. launchd `StartCalendarInterval` 로 주 1회 돌려도 된다.

## DB 백업·재색인

`rra db backup --out data/backups --keep 7` 은 `VACUUM INTO` 로 일관된 사본(`rra-YYYYMMDD-HHMMSS.sqlite`,
권한 600)을 만들고 같은 폴더에 7벌만 남긴다. 일일 실행은 `deploy/launchd/com.rra.backup.plist`(03:30).
임베딩 모델을 바꾸면 기동 때 `db.embedding_model_mismatch` 경고가 나고, `rra reindex` 가 모든 청크를
현재 모델로 다시 색인한다 (문서·FTS 는 그대로).
