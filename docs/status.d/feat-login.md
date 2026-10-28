# 레인 A — feat/login (2026-10-27, 로그인 방식 변경: 직원 사번·공용 계정) 전달 사항

## 현황 행 (docs/status.md 용)
| 2026-10-27 | 레인 A 로그인 | 직원(사번 HMAC)·공용 계정(아이디·scrypt)·관리 토큰 3종 로그인, run 소유자 격리(남의 run 404, 관리자는 전부), 공용 계정 internal 제외, 사용자별 일일 상한(공용 10·직원 20), 잠금(계정 5회·IP 20회/10분·전체 50회 지연), 외부 검토 LLM 일일 300회 상한(초과 시 검토 없이 진행 + 알림), `rra auth` CLI, 웹 로그인 두 탭. **사람 작업: 사번 등록·공용 계정 설정(아래 절차)** | PR #TBD |

## 전달한 것
- **domain** `models/principal.py`(Principal kind admin|staff|guest, 가명 ID), `rules/auth_policy.py`(가명 `staff:<HMAC 앞 12자>`·`guest:<아이디>`,
  run 저장소 키 `staff-…`/`guest-…`/`local`, `LoginGuard` 잠금·지연, `daily_run_limit`·`daily_limit_reached`, 실패 문구 하나).
- **application** `ports/auth.py`(`AuthStorePort`·`DailyBudgetPort`·`BudgetExhausted`), `usecases/login.py`(`Login.staff/guest/status`, `LoginFailed`
  에 delay_sec), `services/scoped_repository.py`(`PublicOnlyRepository` — internal 제외), `RunManager`: `submit(scope, daily_limit)`·
  `RunState.scope`·`generate_public`·`review_budget`(소진이면 `draft_review_skipped=budget`, `review_skipped=True`, 최종 검토는
  `ReviewBudgetExhausted` 409)·`list_all_runs`·`find_owner`. `RunStorePort.list_users` 는 기존 것을 쓴다.
- **adapters** `auth/file_store.py`(`<data_dir>/auth/`: `secret` 32바이트 hex, `staff.json` HMAC 목록, `guest.json` scrypt n=2^14; 폴더 700·
  파일 600, 원문 없음, 상수 시간 비교), `llm/daily_budget.py`(`FileDailyBudget` `<data_dir>/cache/llm_budget.json` 날짜별 카운터,
  `BudgetedLLM` 래퍼 — composition 이 gemini provider 의 모든 단계에 끼운다), `security/sessions.py`(Session.principal·`create(principal)`),
  미들웨어가 `scope["state"]["rra_principal"]`(토큰=admin, 세션=그 주체). 접속자 IP 는 레인 W 의 `client_ip`(`rra_client_ip` 우선).
  가짜 모드 `adapters/fake/auth.py`(e2e 고정 계정 E2E-0001·E2E-0002·e2e/e2e-password-1 — 실제 data/auth 미사용).
- **설정** `config/auth.yaml`(store_dir·guest.include_internal=false·limits·lockout, 비밀 없음), `config/llm.yaml budget`(gemini_daily_calls 300·
  counter 경로), `config_loader.auth_config`·`llm_budget`, `_DATA_LOCATIONS` 에 `auth`·`llm_budget`. `.gitignore` 에 `/data/auth/`.
- **REST** `POST /v1/session` 본문 `{kind: token|staff|guest, token?|staff_no?|id?,password?}`(옛 `{token}` 호환) → `{csrf, expires_in, kind, label}`,
  `GET /v1/session`(kind·label·staff_enabled·guest_enabled만), 모든 run 경로가 소유자 검사(SSE·render-check·finalize 포함), 관리자는
  `GET /v1/runs` 에서 전 사용자 run, `POST /v1/runs` 429(일일 상한), precheck 응답 `llm_budget_exhausted: true`(예산 소진 시 추천·차별화 생략),
  `BudgetExhausted` → 503. 공용 계정은 `guest_services`(internal 제외 저장소로 조립한 precheck·search·recommend·differentiate·compare·brief·
  policy_suggest·notice_match·ntis_insights)를 쓴다.
- **CLI** `rra auth staff add|remove|count`, `rra auth guest set --id <아이디>|disable`, `rra auth status` — 값은 getpass 로만, 출력·기록 없음.
- **web** `routes/Login.tsx` 탭 "철도연구원 직원(사번)" / "그 외 사용자(아이디·비밀번호)", 토큰은 "관리자" 링크 아래. 상단(Layout) 에
  로그인 종류 라벨(직원/공용 계정/관리자)만. 세션 저장은 CSRF + 라벨(`rra-session-kind`). `src/api/schema.d.ts` 재생성(통합 담당이
  `docs/openapi.json` 갱신 뒤 `npm run gen:api` 한 번 더). e2e `login.spec.ts`(직원·공용 계정, 남의 run 404), helpers `loginStaff`·`loginGuest`.
  캡처 `docs/screens/23-login-staff.png`·`24-login-guest.png`, `docs/history/screens/2026-10-27-feat-login-*.png`.
- **테스트** +26: `tests/domain/test_auth_policy.py`, `tests/application/test_login.py`, `tests/adapters/test_auth_file_store.py`(700/600·원문 없음·
  scrypt·예산), `tests/entrypoints/test_api_login.py`(등록·미등록 사번, 공용 성공·실패, 계정·IP 잠금, 소유자 분리, internal 제외, 일일 상한,
  사번 원문 미기록, 예산 소진 알림), `tests/test_auth_repo_hygiene.py`(git 추적 없음). `pytest -q -n auto` 1,723 통과·16 skip, `lint-imports`
  8 kept, `ruff check` 통과, Vitest 57(+2, axe 0), Playwright 13 통과(포트 8101, 가짜 모드).

## 판단 (자동 진행)
- run 격리는 디렉터리(저장소 키) 단위: `runs/staff-<hmac12>/`, `runs/guest-<id>/`. 관리자는 기존 `runs/local/`. 기존 run(소유자 없음)은 관리자만.
- `RunStorePort` 의 사용자 키 규칙(`[a-z0-9][a-z0-9_-]{0,31}`) 때문에 가명 ID `staff:…` 의 `:` 를 저장소 키에서 `-` 로 바꿨다(Principal.id 는 명세대로 `staff:`).
- Gemini 일일 상한은 "검토 횟수"가 아니라 **gemini provider 의 실제 호출 수**(검토·차별화·추천·브리핑 모두)를 하나의 파일 카운터로 센다.
  소진 시 검토는 건너뛰고(`draft_review_skipped=budget` 이 `flow` 에 실려 화면 알림, `review_skipped` 라 바로 마무리 가능), 최종 검토 요청은 409,
  그 밖의 단계는 503. precheck 자동 추천·차별화는 생략하고 `llm_budget_exhausted` 로 알린다.
- 공용 계정의 internal 제외는 저장소 래퍼(`PublicOnlyRepository`)로 하고, 생성 파이프라인은 같은 유스케이스를 공개 저장소로 한 번 더 조립
  (`generate_public`, reranker 공유). `auth.yaml guest.include_internal: true` 면 래퍼 없이 기존과 같다.
- 공용 아이디는 소문자·숫자·_·- 2~20자, 비밀번호 8자 이상(CLI 검사). 사번 형식은 영숫자·하이픈 2~32자 — 실제 사번 체계가 다르면 `valid_staff_no` 만 고친다.
- 잠금 상태는 프로세스 메모리(재시작이면 초기화). 가짜 모드의 고정 계정은 e2e 전용.
- `max_queued_runs`(3)는 저장소 키별이라 자동으로 사용자별이다. 시범 6 은 [D] 에서.
- 가짜 모드(`RRA_FAKE_LLM=1`) `rra api` 는 **원본 .venv 의 설치본**을 실행한다 — worktree 코드로 e2e 를 돌리려면 `RRA_BIN` 을
  `PYTHONPATH=src python -m rra.entrypoints.cli` 래퍼로 준다(이번 검사도 그렇게 했다).

## 내가 할 일 (사람) — CLI 등록 절차 (운영 Mac mini, 저장소 루트, 값은 화면에 남지 않는다)
1. `rra auth status` — 비밀 키·등록 현황 확인(처음이면 "비밀 키: 없음").
2. 직원 사번 등록: 명부 파일로 `rra auth staff import --file <xlsx|csv> [--pad N] [--replace] [--dry-run]`(2026-10-28 A2, `docs/pilot-guide.md` §6)
   또는 한 명씩 `rra auth staff add` → "사번:" 입력. 처음 실행 때 `data/auth/secret`(600) 이 자동으로 생긴다.
   개수 확인 `rra auth staff count`. 삭제는 `rra auth staff remove`.
3. 공용 계정: `rra auth guest set --id <아이디>` → 비밀번호 두 번 입력(8자 이상). 끄기 `rra auth guest disable`.
4. `ls -la data/auth` 로 폴더 700·파일 600 확인(`rra auth status` 가 아니면 경고를 낸다). `git status` 에 data/auth 가 나오지 않는지 확인.
5. API 재기동 없이 즉시 반영된다(파일을 매번 읽는다). 비밀 키(`data/auth/secret`)를 지우면 모든 가명이 바뀌어 기존 run 소유권이 끊긴다 — 백업 대상에 포함.
6. 필요하면 `config/auth.yaml` 의 `limits`(일일 상한)·`lockout`·`guest.include_internal`, `config/llm.yaml budget.gemini_daily_calls` 조정.

## 남은 것
- Lighthouse 는 돌리지 않았다(axe 는 Vitest 로 0 확인). `docs/openapi.json` 재생성 뒤 `npm run gen:api` 재실행(통합 담당).
- 잠금 상태 영속화(현재 메모리), 사번 체계 확정 후 `valid_staff_no` 조정, 비밀 키 교체 절차.
