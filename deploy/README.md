# 배포 (M6 Mac mini 32GB) — launchd 4종(+터널 1) + 127.0.0.1 바인딩 + 역프록시

처음 설치하는 사람 기준의 순서다. 모든 서비스는 사용자 launchd 에이전트(`~/Library/LaunchAgents`)로 돌고,
비밀은 `.env`(권한 600)에만 둔다. 외부 공개는 2026-10-28 시범부터 **Tailscale Funnel** `https://rra.taile5afcf.ts.net`(ADR 0047, 켜고 끄기는
사람 작업, `docs/pilot-guide.md` §1.5). Cloudflare Tunnel + Access(§6, ADR 0024)는 DNS 때문에 띄우지 못한 이전 계획이다.

## 0. 전제 (보안 G·H)

- `rra api` 와 `mlx_lm.server` 는 **127.0.0.1 에만 바인딩**한다. 포트를 외부에 직접 열지 않는다.
- 외부(동료 PC)에서 쓰려면 HTTPS 를 종단하는 역프록시 뒤에서만 — 지금은 Tailscale Funnel(이전 계획: Cloudflare Tunnel).
  앱은 그 뒤에서도 자체 로그인(직원 사번·공용 계정·관리 토큰 `RRA_API_TOKEN`, ADR 0026)을 그대로 요구한다.
- plist 에는 토큰·키를 적지 않는다. `WorkingDirectory` 의 `.env` 를 settings 가 읽는다.
- 파일 업로드 엔드포인트는 없다. 알리오·사내 자료는 로컬 폴더(`data/inbox/…`)로만.

## 1. 설치 순서 (Mac mini, 처음 한 번)

```bash
# 1) 도구
xcode-select --install                                  # git 등
curl -LsSf https://astral.sh/uv/install.sh | sh          # uv (~/.local/bin)
uv tool install mlx-lm                                   # mlx_lm.server (~/.local/bin/mlx_lm.server)

# 2) 저장소·가상환경 (경로는 plist 와 같아야 한다: /Users/<계정>/projects/research-proposal-app)
mkdir -p ~/projects && cd ~/projects
git clone <저장소 URL> research-proposal-app && cd research-proposal-app
uv venv --python 3.12 && uv pip install -e ".[dev,adapters]"   # adapters = 임베딩(sentence-transformers·torch)

# 3) 모델 내려받기 (HF 캐시). 이후 서비스는 HF_HUB_OFFLINE=1 로 돈다
.venv/bin/python -c "from huggingface_hub import snapshot_download as d; d('mlx-community/Qwen2.5-7B-Instruct-4bit'); d('intfloat/multilingual-e5-base')"

# 4) .env — 권한 600 이 아니면 기동을 거부한다
cp .env.example .env && chmod 600 .env
#    RRA_API_TOKEN=<긴 무작위 문자열>  (openssl rand -hex 32)
#    RRA_GEMINI_API_KEY=…            (검토·차별화 제안. 없으면 검토 건너뜀·차별화는 로컬 모델)
#    RRA_SCIENCEON_*·RRA_NTIS_KEY·RRA_KIPRIS_KEY (있는 것만. docs/external-apis.md)

# 5) 자료 반입 (선택): 개발기 DB 사본과 inbox 폴더를 복사
#    data/rra.sqlite, data/inbox/own/*.xls(x), data/inbox/own_docs/<연도>/…, config/templates/proposal_korail.hwpx(실물 양식)

# 6) 검사
.venv/bin/pytest -q && .venv/bin/lint-imports && .venv/bin/ruff check src tests
```

plist 의 경로는 `/Users/chan/projects/research-proposal-app` 로 채워져 있다. 계정·위치가 다르면 네 파일의
`ProgramArguments`·`WorkingDirectory`·`EnvironmentVariables`·로그 경로를 함께 바꾼다
(`sed -i '' 's#/Users/chan#/Users/<계정>#g' deploy/launchd/*.plist`).

## 2. launchd 등록 (3 + 1종, 공개할 때 + 터널 1종)

| 파일 | 역할 | 일정 | 바인딩 |
|---|---|---|---|
| `com.rra.mlx.plist` | 로컬 LLM (`mlx_lm.server`, Qwen2.5-7B-Instruct-4bit) — 2026-10-28 부터 주 작성은 Argon, 로컬은 오류 섹션 대체·L2 로컬 2차 검토 | 상시 (KeepAlive) | 127.0.0.1:8080 |
| `com.rra.api.plist` | REST API (`rra api`) | 상시 (KeepAlive) | 127.0.0.1:8000 |
| `com.rra.backup.plist` | DB 사본 (`rra db backup --keep 7`, VACUUM INTO, 600) | 매일 03:30 | — |
| `com.rra.ingest.plist` | 야간 적재 (`rra ingest --skip-unavailable`: OpenAlex·inbox·키 있는 자료원) | 매일 02:30 | — |
| `com.rra.tunnel.plist` | *(이전 계획, 등록 안 함)* Cloudflare Tunnel (`cloudflared tunnel --config ~/.cloudflared/config.yml run rra`) — rra.ai-edu-lab.co.kr → 127.0.0.1:8000 | 상시 (KeepAlive), **Access 확인 뒤에만** | 아웃바운드만 (포트 열지 않음) |

```bash
cp deploy/launchd/com.rra.{mlx,api,backup,ingest}.plist ~/Library/LaunchAgents/
for s in mlx api backup ingest; do launchctl load -w ~/Library/LaunchAgents/com.rra.$s.plist; done
launchctl list | grep com.rra            # 4개가 보이면 등록됨 (PID 가 있으면 실행 중)
# 공개(시범)까지 했을 때만 — cloudflared 설치·login·create·route dns·Access 설정이 끝난 뒤 (docs/deploy-exposure.md §5.3·5.4)
cp deploy/launchd/com.rra.tunnel.plist ~/Library/LaunchAgents/ && launchctl load -w ~/Library/LaunchAgents/com.rra.tunnel.plist
```

순서: mlx → api (api 는 mlx 없이도 뜨지만 생성은 실패한다). 해제는 `launchctl unload -w …`.

**맥 항상 켜짐 (`com.rra.awake.plist`, 시범 2026-10-28)** — `/usr/bin/caffeinate -dimsu` 를 상시 실행(RunAtLoad·KeepAlive)해
화면·유휴·디스크·시스템 잠자기를 막는다. 덮개를 닫으면(외부 모니터 없이) 그래도 잠들 수 있으니 덮개는 열어 둔다.
```bash
cp deploy/launchd/com.rra.awake.plist ~/Library/LaunchAgents/ && launchctl load -w ~/Library/LaunchAgents/com.rra.awake.plist
launchctl list | grep com.rra.awake          # PID 가 보이면 실행 중
pmset -g assertions | grep -i caffeinate     # PreventUserIdleSystemSleep·PreventSystemSleep 가 caffeinate 로 잡혀 있어야 한다
launchctl unload -w ~/Library/LaunchAgents/com.rra.awake.plist   # 끄기 (다시 잠들 수 있게)
```
Streamlit 화면(`rra ui`, 127.0.0.1:8501)은 시연 때만 손으로 띄운다.

## 3. 점검 명령

```bash
curl -s http://127.0.0.1:8080/v1/models | head -c 200      # mlx 서버 — Qwen 이 목록에 있어야 한다
.venv/bin/rra llm-check --stage compose                      # 로컬 모델 왕복 + served_model 확인
.venv/bin/rra llm-check --provider gemini                    # Argon 왕복 (키 있을 때)
curl -s http://127.0.0.1:8000/healthz                        # {"status":"ok"} — 인증 없이
curl -s -H "X-RRA-Token: $RRA_API_TOKEN" -H 'content-type: application/json' \
     -d '{"current_state":"…","root_cause":"…","limitation":"…","goal":"…"}' \
     http://127.0.0.1:8000/v1/precheck                      # 유사과제 알림
.venv/bin/rra sources check                                  # ScienceON·NTIS·KIPRIS 키 유무(값 없음)·왕복·record_tag 진단
.venv/bin/rra ingest --source openalex --skip-unavailable --limit 20   # 적재 1회 수동 실행
.venv/bin/rra db backup --out data/backups --keep 7          # 사본 1회 수동 실행 → data/backups 에 7벌까지
.venv/bin/rra runs purge --dry-run                            # 만료 run (security.yaml retention_days, 180일)
tail -n 50 ~/Library/Logs/rra-{mlx,api,backup,ingest,tunnel}.err.log
/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel status   # 443 에 "(Funnel on)" — 공개 경로 확인은 이 맥 밖에서(pilot-guide §1.5)
# (이전 계획) curl -sI https://rra.ai-edu-lab.co.kr | head -3   # Cloudflare 터널 기동 뒤: 302 → cloudflareaccess.com
```

## 4. REST API 요약 (`rra api`)

인증: 모든 `/v1/*` 에 `X-RRA-Token: <토큰>` 또는 `Authorization: Bearer <토큰>`(401, 관리 토큰), 세션 쿠키 + CSRF 는 프론트엔드용
(`POST /v1/session {kind: token|staff|guest}`, 2026-10-28~ 직원 사번·공용 계정, ADR 0026).
본문 상한 `security.yaml input_limits.api_max_body_bytes`(기본 64KB, 초과 413). 오류는 problem+json.
응답 헤더: `Content-Security-Policy: default-src 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. CORS 없음.

| 엔드포인트 | 설명 |
|---|---|
| `POST /v1/precheck` · `POST /v1/precheck/differentiate` | 유사과제 알림 · 차별화 제안 (기능 1·2) |
| `GET/POST /v1/search` | 하이브리드 검색 (청크 `trust: untrusted`, `similarity`) |
| `GET /v1/sources/status` | 자료원별 적재 건수·최근 적재일 |
| `POST /v1/runs` → 202, `GET /v1/runs`, `GET /v1/runs/{id}`, `GET …/events`(SSE), `POST …/resume` | 생성·조회·재개 |
| `GET …/draft`, `GET …/versions`, `POST …/revert`, `POST …/edits`, `POST …/confirm` | 초안·버전·편집·확정 |
| `POST/GET …/review` | Argon 검토 (점수·의견·전송 범위) |
| `GET …/render-check`, `POST …/finalize`, `POST …/reopen` | 렌더 전 점검 · 최종 마무리(HWPX) · 다시 열기 |
| *(아래는 2026-10-27~29 추가 — 2026-10-29 16:06 기준 전체 71 경로)* | |
| `GET/POST/DELETE /v1/session` | 로그인(직원 사번·공용 계정·관리 토큰)·상태·로그아웃 |
| `POST /v1/ideas/structure`·`/structure/merge` | ① 간편 입력 → 네 칸·보완 질문 답 합치기 |
| `POST /v1/ideas/policy-suggestions` | ① 정책 근거 추천 — 응답 `rank`(1 = 팝업 미리 체크), 요청 `exclude_doc_ids`(다시 받기), LLM 없음, 자동 삽입 없음(ADR 0052) |
| `POST /v1/ideas/policy-cards`(`/polish`), `POST …/runs/{id}/policy-cards`(`/polish`), `POST …/runs/{id}/policy-choice` | ③ 정책적 중요도 작성안·다듬기, ④ 고른 안·직접 입력 → 새 버전 |
| `POST /v1/precheck?stage=rule` → `/precheck/judgment`·`/choices`·`/recommendations`(`/more`·`/{id}/apply`)·`/comparison`·`/brief`·`/clarify`·`/ntis-outcomes`·`/plan/polish` | ② 표 먼저 → AI 판정·선택·과제안·비교표·브리핑·보강 질문(ADR 0039) |
| `GET /v1/search/docs` | 위쪽 통합 검색·자료 검색(문서 단위, 공용 계정 internal 제외, ADR 0050) |
| `GET …/sections-progress`, `GET/POST …/figures`(`/techniques`·`/{fid}`·`/{fid}/image`) | 섹션 진행, 그림(백그라운드 작업·확인·말로 고치기, ADR 0029·0045) |
| `POST …/sections/{key}/rewrite`(`/apply`), `GET/POST …/sections/{key}/questions`·`answers`, `GET …/changes` | ④ AI 다시 쓰기·보완 질문·변경 n건(ADR 0037) |
| `GET …/local-review`, `POST …/local-review/{sid}/apply`·`dismiss`·`retry` | L2 로컬 2차 검토 제안 [반영]/[무시](ADR 0040) |
| `POST/GET …/final-review`(`/cancel`), `GET …/submit-check`, `POST …/evidence-decisions`(`/bulk-approve`), `GET …/sentences/{sid}/evidence` | ⑤ 최종 검토·⑥ 제출 전 점검·근거 판단 |
| `GET …/request`, `POST …/request/preview`, `POST …/regenerate` | 입력 변경 → 관련 섹션만·전체 다시 쓰기(ADR 0035) |
| `GET …/usage`, `POST …/feedback` | 사용 기록·만족도(개인정보 없음) |

전체 스키마: `docs/openapi.json` (`rra api schema`).

## 4.5 재배포 (시범 기간, 2026-10-28)

main 을 운영 API 에 반영하는 명령은 `tools/deploy.sh` 하나다 — main 최신 확인 → web 빌드(바뀐 경우) → 생성 중 run 확인
(`rra runs active`, `--wait`/`--force`) → `data/deploy/version.json` → `launchctl kickstart -k gui/$(id -u)/com.rra.api` →
healthz·로그인 화면·외부 주소 확인 → `docs/history/deploys/` 기록. 규칙(자동 재시작 금지, 반영 대기 목록, 보안·접속 오류는 즉시)은
`docs/pilot-guide.md` §6.3. 화면 하단과 `/healthz` 의 `version` 이 배포된 커밋을 보여 준다.

## 5. 보존·백업·재색인 (보안 I)

- `rra runs purge` 는 만료 run 을 지운다(주 1회 launchd 로 돌려도 된다 — 아직 plist 없음).
- `rra db backup --out data/backups --keep 7` 은 `rra-YYYYMMDD-HHMMSS.sqlite` 사본을 만들고 7벌만 남긴다
  (`tests/deploy/test_launchd_plists.py` 가 plist 의 `--keep 7` 과 회전을 함께 검사한다).
- 임베딩 모델을 바꾸면 기동 때 `db.embedding_model_mismatch` 경고 → `rra reindex`.

## 6. 외부 공개

**현재(2026-10-28~)**: Tailscale Funnel `https://rra.taile5afcf.ts.net` → 127.0.0.1:8000 → 앱 로그인. `config/api.yaml public_origin` 이 이 주소,
Funnel 뒤 접속자 IP 는 127.0.0.1 peer 일 때만 `X-Forwarded-For` 맨 오른쪽(`trust_forwarded_from_loopback`, #79). `com.rra.awake`(caffeinate)로
맥이 잠들지 않게 한다. 확인·장애 대처는 `docs/pilot-guide.md` §1.5, 결정은 ADR 0047.

**이전 계획 (Cloudflare Tunnel + Access, 2026-10-27 — 띄우지 않음)**

- 공개 주소 `https://rra.ai-edu-lab.co.kr` → Cloudflare Access(이메일 일회용 코드) → 터널 → 127.0.0.1:8000 → 앱 로그인(토큰). 이중 인증.
- 앱 설정은 `config/api.yaml`(`public_origin`, `trust_cf_connecting_ip`) — 비밀 아님. `.env` 는 그대로.
- 터널 설정 초안 `deploy/cloudflared/config.example.yml`, 상시 실행 `deploy/launchd/com.rra.tunnel.plist`. 절차·막힌 점(DNS 가 Gabia,
  cloudflared 미설치)·Access 확인·Tailscale 대체 경로는 `docs/deploy-exposure.md` §5.
