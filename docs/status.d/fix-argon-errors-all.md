## 그림 생성·추천 단계 Argon 오류도 같은 분류·기록 (fix/argon-errors-all, 2026-11-04, ADR 0055 덧붙임)

- 계기: ADR 0055 "남은 일" — 그림 생성(`adapters/llm/image_gen.py`)은 자체 요청 경로라 400 키 무효가 일반 `LLMError` 로 묻히고 상태도
  적지 않았다. `usecases/recommend_projects._ask` 는 Argon 예외를 로그 없이 삼켰다.
- 그림: 텍스트와 같은 `_payload` 분류(400 `API_KEY_INVALID`·401·403 → `LLMAuthError`, 429 할당량 → `LLMQuotaExceeded`, 그 밖 429 →
  `LLMRateLimited`, 타임아웃 → `LLMTimeout`, 연결 `connection`, 5xx `server`), 같은 경고 한 줄 `llm.failed provider=gemini
  stage=figure_image …`(형식 `_payload.FAILURE_LOG`·`failure_args` 공용). 재시도·백오프·일일 상한·캐시·기본 그림 대체는 그대로.
- 상태 규칙(`domain/rules/llm_status.text_status_from_image`): 그림 결과는 `gemini_image` 에(`/healthz`·띠에는 안 나옴). 키 무효는
  `gemini` 에도 올린다(띠가 뜸). 그림 성공은 `gemini` 가 key_invalid 일 때만 ok 로 되돌린다. 그림 할당량·응답 없음은 `gemini` 를 바꾸지
  않는다. 조립 `build_image_generator` 가 텍스트와 같은 `build_llm_status` 를 넘긴다. 그림 경로는 `*.latency.jsonl` 을 쓰지 않아 `error_code` 는 없다.
- 추천: `recommend.argon_failed kind=<code|클래스|invalid> fallback=local|none`(WARNING), 로컬 실패 `recommend.local_failed kind=…`,
  끝날 때마다 `recommend.done provider= fallback_local= calls= kept= discarded= skipped_reason= retry_used=`(대체·실패면 WARNING, 아니면 INFO).
  상태 기록·`llm.failed` 는 추천 단계 LLM(openai_compat)이 이미 한다(조립 시험으로 확인) — 유스케이스는 다시 쓰지 않는다.
- 같은 무로그 삼킴: `usecases/differentiate._ask` 에 `differentiate.argon_failed|local_failed` 를 더했다. `card_overlap.failed`·
  `argon_first.failed` 줄에는 `kind=` 만 더했다.
- 프론트엔드 영향(API): 없음(`/healthz` 모양 그대로, `gemini_image` 는 내지 않는다). `docs/openapi.json` 변경 없음.
- 시험: pytest 2492 → 2517(+25), vitest 234 그대로, e2e 46 통과(+3 skip) 그대로, lint-imports 8.
- 배포 뒤 확인: 그림이 기본 그림으로 대체될 때 `rra-api.err.log` 에 `llm.failed provider=gemini stage=figure_image` 한 줄이 있는지,
  `data/cache/llm_status.json` 에 `gemini_image` 항목이 생기는지.
