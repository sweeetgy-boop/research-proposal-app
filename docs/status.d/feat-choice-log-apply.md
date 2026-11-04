# feat/choice-log-apply (2026-11-04, ADR 0056 후속) 전달 사항

## 전달한 것
- **기록 시점** `similar_choice.choice_records(..., event=)` 가 줄마다 `event` 를 쓴다(`generate` 기본 | `apply`). `choice_log.ALLOWED_KEYS` 에 `event` 를 더했다.
  `event` 가 없는 옛 줄은 2026-11-04 이전의 생성 요청 기록이다(generate 로 본다).
- **apply 신호** `POST /v1/precheck/choices?apply=true` — 선택이 있으면 event=apply 로 기록한다. 쿼리가 없으면 기록하지 않는다(옛 동작). 응답은 같다.
  웹 `routes/Precheck.tsx applyChoices` 가 [선택 적용] 을 누를 때마다 `endpoints-precheck.applyChoices` 를 한 번 부른다(실패는 무시).
- **중복 한 줄** 같은 세션(`_owner_key` + 아이디어 해시 → `session_key` 16자, 메모리에만)이 마지막으로 기록한 서명(`choice_signature` = event + (doc_id, 선택, 출처)
  집합)과 같으면 쓰지 않는다(`is_repeat`). 상태는 `entrypoints/api/choice_dedupe.ChoiceDedupe`(LRU 500, 재시작하면 잊음). 쓰기 실패(OSError)는 경고만 남기고
  서명을 기억하지 않는다. 생성 요청도 같은 규칙이다(같은 선택으로 잇따라 생성하면 한 번).
- **변하지 않은 것** 차단 게이트·건수·③ 판정표·비교표·활용 제안·과제안·생성 게이트·응답 본문, 기록 파일 위치·권한, Streamlit·CLI·MCP 경로.
  `composition.py` 는 고치지 않았다(상태는 `create_app` 안).

## 시험
- pytest: `tests/domain/test_choice_log_event.py`, `tests/entrypoints/test_choice_dedupe.py`, `tests/entrypoints/test_choice_log_apply_api.py`.
- vitest: `features/precheck/ApplyRecord.test.tsx`.
- e2e: `precheck-v3.spec.ts` — [선택 적용] 한 번에 `/v1/precheck/choices?apply=true` 요청 한 번(200), 본문 선택·출처 = 비교표 요청, 과제안 더 만들기는 보내지 않는다.

## API 영향
- `docs/openapi.json`·`web/src/api/schema.d.ts` 를 다시 만들었다. `POST /v1/precheck/choices` 에 선택 쿼리 `apply`(boolean, 기본 false)가 생겼다. 요청 본문·응답은 그대로다.
