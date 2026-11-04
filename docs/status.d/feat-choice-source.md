# feat/choice-source (2026-11-04, ADR 0056) 전달 사항

## 전달한 것
- **요청** `SimilarChoice.source: "user" | "ai_prefill"`(`domain/models/request.py`)를 더했다. 보내지 않으면 `user` 다(옛 웹 캐시·CLI·MCP 의 명시적 선택).
  `ProposalRequest.choice_sources()` 는 doc_id → 출처를 돌려준다.
- **선택 기록** `similar_choice.choice_records(..., sources=)` 가 `similar_choices.jsonl` 의 줄마다 `source` 를 쓴다. 묶음 행이면 선택이 걸린 doc_id 의 출처를 쓴다.
  `choice_log.ALLOWED_KEYS` 에 `source` 를 더했고, `app._record_choices` 가 요청의 출처를 넘긴다. 서버 기본 선택은 지금처럼 기록하지 않는다.
  `source` 가 없는 옛 줄은 2026-11-04 이전 기록이며 출처를 모른다.
- **웹** 저장소에 `choiceSources`·`appliedChoiceSources` 를 두었다(sessionStorage 에 남고, 새 precheck 결과가 오면 비운다). 행 하나를 바꾸는 규칙은
  `model.chooseRow` 에 둔다. 고른 값이 기본 선택과 같으면 `ai_prefill`(지움 포함), 다르거나 기본 선택이 없는 행이면 `user` 다.
  `withDefaults` 는 미리 고른 행을 `ai_prefill` 로 둔다. `choiceList(map, sources)` 는 행마다 `source` 를 싣는다. 그래서 판정·[선택 적용]
  (비교표·활용 제안·과제안)·다시·더 만들기·다듬기 요청과 [다음] 뒤 생성 요청이 모두 출처를 보낸다. 옛 화면 상태는 `inferSources` 로 추정한다.
- **변하지 않은 것** 차단 게이트·유효 선택·`similar_count`·③ 판정표·비교표·활용 제안·과제안·생성 게이트(출처는 메타데이터), 기록 시점(생성 요청 때).

## 시험
- pytest: `tests/domain/test_choice_source.py`, `tests/entrypoints/test_choice_source_api.py`.
- vitest: `features/precheck/ChoiceSource.test.tsx`, `features/idea/storeSources.test.ts`. `PrecheckV3.test.tsx` 의 요청 본문 기대값에 출처를 더했다.
- e2e: `precheck-v3.spec.ts` — 행 하나를 바꾸고 [선택 적용] 하면 비교표 요청 본문의 출처가 user 1건, 나머지는 ai_prefill 이다(`page.waitForRequest`).

## API 영향
- `docs/openapi.json`·`web/src/api/schema.d.ts` 를 다시 만들었다. `SimilarChoice.source`(선택, enum user·ai_prefill, 기본 user)가 생겼다.
  응답 필드는 그대로다. schema.d.ts 에는 main 에서 빠져 있던 `/healthz` 설명 갱신(ADR 0055)도 함께 들어갔다.
