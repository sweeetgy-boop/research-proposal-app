# ADR 0055 — Argon(Gemini) 키 무효를 인증 실패로 분류하고 화면·/healthz 에 드러내기 (2026-11-04, fix/gemini-auth-visible)

## 맥락
- 사고 경과(KST, 운영 `data/cache/llm_budget.latency.jsonl`·`rra-api.err.log` 기준):
  - 2026-10-30 09:32 — 마지막 Argon 성공 호출.
  - 10-30 09:32 ~ 11-03 16:14 — Argon 호출 없음(시범 사용 없음). 이 사이 어느 시점에 키가 무효가 됐는지는 기록으로 알 수 없다.
  - 11-03 16:14:49 — 처음 관찰된 실패. 그 뒤 모든 Argon 호출이 실패했다.
  - 11-03 17:28 — 키 교체. 그 뒤 호출은 성공했고, 429(`LLMRateLimited`)가 한 번 있었다.
- Google 은 무효 키에 401/403 이 아니라 **HTTP 400** `INVALID_ARGUMENT` / reason `API_KEY_INVALID`, 본문 "API key not valid. Please pass a
  valid API key." 로 답한다. `openai_compat._request` 는 401/403 만 `LLMAuthError` 로 보았다. 그래서 400 은 일반 `LLMError` 가 됐다(재시도 없음).
- 로그에는 `same_judgment.failed origin=argon err=LLMError` 만 남았고, 응답 시간 기록에도 `"error": "LLMError"` 만 남았다. 같음 판정·추천·작성은
  ADR 0037·0038 의 정해진 순서대로 로컬 7B 로 대체돼 화면이 멀쩡해 보였다. 그래서 누구도 몰랐다(ADR 0053 결과에 관찰만 적어 둠).
- `usecases/recommend_projects._ask` 는 Argon 예외를 로그 없이 삼킨다. 이 파일은 같은 날 다른 작업(precheck 선택 집계·비교표)이 고치고 있어
  손대지 않는다. 그래서 유스케이스가 아니라 **어댑터와 상태 수준**에서 신호를 남긴다.

## 선택지
1. 유스케이스마다 Argon 실패 로그를 더한다. 호출 지점이 10곳이 넘고, 하나를 빠뜨리면 같은 일이 생긴다. 화면에는 여전히 보이지 않는다.
2. 주기적으로 Gemini 를 따로 불러 상태를 확인한다. 예산(일일 600회)을 쓰고 호출이 늘어난다.
3. 어댑터가 이미 하는 호출의 결과를 분류해 경고 한 줄과 상태 파일로 남긴다. `/healthz` 가 그 상태를 열거값으로 내고, 웹은 화면 위 알림 띠로 보인다.

## 결정
3을 택한다.
- **분류**(`adapters/llm/openai_compat.py`, `_payload.error_codes`): 400 이면서 본문에 "API key not valid" 또는 `API_KEY_INVALID` 가 있으면
  `LLMAuthError`(재시도 없음)로 본다. 401/403 은 그대로다. 429 는 `RESOURCE_EXHAUSTED`·quota 문구가 있으면 `LLMQuotaExceeded`(`LLMRateLimited` 하위,
  유스케이스의 rate_limit 기록 그대로), 그 밖은 `LLMRateLimited` 다. 재시도·백오프는 바꾸지 않는다. 예외에는 `code`(auth·quota·rate_limit·timeout·
  connection·server·http …)·`http_status`·`api_status`/`api_reason`(형식이 맞는 열거값만)을 단다. 인증 실패·429 예외 메시지에는 본문을 싣지 않는다.
- **경고 한 줄**: 실패 1건마다 `llm.failed provider=… stage=… kind=… http=… status=… reason=…`. 키·URL·쿼리·본문 글은 싣지 않는다(보안 D).
- **상태**(`application/ports/llm_status.LLMStatusPort`, `adapters/llm/status_file.FileLLMStatus`, 규칙 `domain/rules/llm_status`): gemini 어댑터가
  호출이 끝날 때마다 `ok | key_invalid | quota | unavailable` 를 `<data_dir>/cache/llm_status.json`(`_DATA_LOCATIONS` 의 `llm_status`)에 적는다.
  `since` 는 지금 상태가 시작된 시각, `checked_at` 은 마지막 갱신 시각이다. 429 는 두 종류 모두 quota 로 본다. 타임아웃·연결 실패·5xx·그 밖의 4xx 는
  unavailable 이다. 보내지 않은 호출(프롬프트 상한)·응답 형식 오류는 상태를 바꾸지 않는다. 추가 호출은 없고 예산도 그대로다. 같은 상태는 60초 안에 다시 쓰지 않는다.
- **응답 시간 기록**: `*.latency.jsonl` 행에 `error_code`(위 code)를 더한다. 본문은 그대로 없다.
- **`/healthz`**: `llm: {gemini: ok|key_invalid|quota|unavailable|unknown, since: ISO|null}` 를 더한다. 인증 없이 인터넷(Funnel)에서 보이므로
  열거값과 시각만 낸다. 공급자 주소·모델명·오류 문구·건수는 내지 않는다. `status`·`version` 은 그대로다(`tools/deploy.sh`·화면 하단).
- **화면**(`web/src/components/frame/ArgonStatusBanner.tsx`): 로그인한 모든 화면 위쪽 막대 아래에 띠 "AI(Argon) 연결 오류 — 로컬 모델로 대체 중"
  (`role="status"`)을 보인다. 사유 줄은 관리자에게만 보인다: key_invalid "API 키 확인 필요", quota "사용 한도 초과", unavailable "응답 없음".
  ok·unknown 이면 띠가 없고, 로그인 전에도 없다. 하단 버전과 같은 `/healthz` 캐시를 60초마다, 그리고 창으로 돌아올 때 다시 읽는다.
  관리자 여부는 로그인 응답의 `kind` 를 세션 저장소에 함께 둔 값(`getSessionRole`)으로 안다. 화면 문구일 뿐 권한 경계는 아니다.
- **가짜 모드**: 상태 파일 대신 `RRA_FAKE_GEMINI_STATUS`(기본 없음 → unknown)를 읽는다. 함께 쓰는 Playwright 서버에 켜면 모든 spec 에 띠가
  보이므로, e2e `argon-status.spec.ts` 는 `/healthz` 응답을 가로채 llm 만 바꾼다.
- **`rra llm-check`**: 분류된 실패는 본문 대신 "LLM 호출 실패: 인증 실패(API 키 무효) (HTTP 400 · INVALID_ARGUMENT · API_KEY_INVALID)" 한 줄을 낸다.

## 이유
- 실패 신호를 어댑터 한 곳에서 만들면 호출 지점이 늘어도 빠지지 않는다. 대체 순서(ADR 0037·0038)를 바꾸지 않고 "대체 중"이라는 사실만 드러낸다.
- 상태는 이미 하는 호출의 결과다. 그래서 예산·지연이 늘지 않는다. 대신 호출이 없으면 상태도 바뀌지 않는다(사고 때 나흘 동안 호출이 없었던 것과 같다).
- 열거값만 공개하므로 `/healthz` 로 알 수 있는 것은 "Argon 이 지금 되는가" 정도다. 키·주소·사용량은 알 수 없다.

## 결과
- pytest 2,424 → 2,461(+37: 녹화형 오류 본문 6종 분류·로그·상태, 상태 파일, 규칙, `/healthz`, 조립, llm-check). lint-imports 8 유지.
  vitest 223 → 233(+10: 띠 직원·관리자 3상태·숨김 4·다시 읽기). e2e 45 → 46 통과(+3 skip)(`argon-status.spec.ts`).
- 녹화형 fixture `tests/fixtures/llm/gemini_errors/`: 400 키 무효(사고 본문 모양, 키 없음)·401·403·429 할당량·429 일반·503.
- `docs/openapi.json`: 응답 모델은 그대로(`dict`)이고, `/healthz` 설명 문구만 바뀐다. 통합 때 `rra api schema` 로 다시 만든다.
- 남은 일: 그림 생성(`adapters/llm/image_gen.py`, Nano Banana)은 자체 요청 경로라 이번 분류·상태 기록 밖이다. 키 무효면 같은 키라 텍스트 호출 쪽 상태가
  먼저 알린다. `recommend_projects._ask` 의 무로그 삼킴은 그 파일 작업이 끝난 뒤 따로 고친다.

## 덧붙임 — 그림 생성·추천 단계도 같은 분류·기록 (2026-11-04, fix/argon-errors-all)

### 맥락
- 위 "남은 일" 두 가지: 그림 생성(`adapters/llm/image_gen.py`, Nano Banana Pro `gemini-3-pro-image`)은 자체 요청 경로라 400 키 무효가
  `LLMError("이미지 생성 실패 (400).")` 로 묻혔고 상태도 적지 않았다. `usecases/recommend_projects._ask` 는 Argon 예외를 로그 없이 삼켰다.
- 사용자 결정: 그림의 키 무효는 같은 키이므로 띠를 띄운다. 그림만의 할당량·응답 없음은 띠를 바꾸지 않는다 — 그림 대체는 기본 그림이지
  로컬 모델이 아니라서 "로컬 모델로 대체 중" 문구와 맞지 않는다.

### 결정
- **그림 분류**(`image_gen._post_with_retry`): 텍스트와 같은 `_payload.error_codes`·`is_key_invalid`·`is_quota_exhausted` 를 쓴다.
  400 `API_KEY_INVALID`·401·403 → `LLMAuthError`(재시도 없음), 429 할당량 → `LLMQuotaExceeded`, 그 밖 429 → `LLMRateLimited`, 타임아웃 →
  `LLMTimeout`, 연결 실패 `code=connection`, 5xx `code=server`, 그 밖 4xx `code=http`, 200 인데 JSON 아님·상한 초과 → `LLMResponseInvalid`.
  보내기 전 거절(형식·크기·프롬프트 상한)은 `code=not_sent`. 재시도 횟수·백오프·`limiter.note_429`·일일 상한(`figures.daily_image_cap`)·
  캐시·기본 그림 대체는 그대로다. 예외 메시지에 본문·키는 여전히 없다.
- **경고 한 줄**: 텍스트와 같은 모양 `llm.failed provider=gemini stage=figure_image kind=… http=… status=… reason=…`
  (형식 문자열 `_payload.FAILURE_LOG`·`failure_args` 를 둘이 함께 쓴다). 요청 1건(재시도 포함)당 1줄, 보내지 않은 호출은 줄이 없다.
- **상태 규칙**(`domain/rules/llm_status.text_status_from_image`, 조립이 텍스트와 같은 `FileLLMStatus` 를 넘긴다):
  | 그림 결과 | `gemini_image` | `gemini`(띠·`/healthz`) |
  |---|---|---|
  | key_invalid(400 키 무효·401·403) | key_invalid | key_invalid |
  | ok | ok | 지금 key_invalid 일 때만 ok, 그 밖은 그대로 |
  | quota(429 두 종류) | quota | 그대로 |
  | unavailable(타임아웃·연결·5xx·그 밖 4xx) | unavailable | 그대로 |
  | 응답 형식 오류·보내지 않음 | 그대로 | 그대로 |
  `gemini_image` 는 상태 파일에만 있고 `/healthz`(`public_view` 는 `gemini` 만 읽는다)·띠에는 나오지 않는다.
- **응답 시간 기록**: 그림 경로는 `*.latency.jsonl` 을 쓰지 않는다(일일 상한 카운터만). 그래서 `error_code` 를 더할 곳이 없다 — 바꾸지 않았다.
- **추천 단계**(`recommend_projects._ask`): Argon 이 예외·해석 실패로 끝나면 `recommend.argon_failed kind=<어댑터 code | 예외 클래스 |
  invalid> fallback=local|none`(WARNING) 한 줄, 로컬도 실패하면 `recommend.local_failed kind=…`. 키가 없어 처음부터 로컬이면
  argon_failed 대신 local_failed 다. 추천이 끝날 때마다(건너뜀 포함) `recommend.done provider= fallback_local= calls= kept= discarded=
  skipped_reason= retry_used=` 한 줄 — 로컬 대체·호출/해석 실패로 끝났으면 WARNING, 아니면 INFO(운영 로그는 `rra.api` 밖은 WARNING 부터
  남는다). 열거값·건수만, 예외 메시지(본문·URL 이 섞일 수 있다)·키는 싣지 않는다. 카드 겹침 다시 받기(`_check_cards.again`)도 같은
  `_ask` 를 지나므로 같은 줄이 남는다.
- **상태 기록은 어댑터에서 한 번**: 추천 단계 LLM 은 `build_llm(stage="recommend")` = `OpenAICompatLLM`(+ `BudgetedLLM`)이라
  `llm.failed` 줄·`llm_status.json`·`error_code` 를 이미 남긴다(조립 시험으로 확인). 유스케이스는 `llm.failed` 를 다시 쓰지 않는다.
- **같은 무로그 삼킴**: `usecases/differentiate._ask` 도 같은 모양이라 `differentiate.argon_failed|local_failed kind= fallback=` 를 더했다.
  `card_overlap.failed`·`argon_first.failed` 줄에는 `kind=`(어댑터 code)만 더했다.

### 결과
- 그림 키 무효가 와도 띠가 뜬다(텍스트 호출이 없을 때도). 그림 할당량 소진은 띠를 바꾸지 않고 `gemini_image` 에만 남는다.
- 추천이 로컬로 대체되면 운영 로그에 이유 한 줄과 요약 한 줄이 남는다.
