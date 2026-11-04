# ADR 0056 — ② 선택 기록에 출처(source): AI 미리 고름과 제안자 판단을 나눈다 (2026-11-04, feat/choice-source)

## 맥락
- ② 유사과제 행의 [유사함]/[관련 없음] 선택은 생성 요청(`POST /v1/runs`) 때 `data/feedback/similar_choices.jsonl` 에 한 줄씩 남는다
  (`domain/rules/similar_choice.choice_records` → `entrypoints/api/app._record_choices` → `adapters/logging/choice_log`). 임계치·AI 판정을
  평가하는 재료다.
- ADR 0039 부터 웹은 AI '다르다' 행에 [관련 없음] 을 미리 골랐다. ADR 0054 부터는 '같다'·'일부 겹침' 행에도 [유사함] 을 미리 고른다.
  웹은 미리 고른 값을 요청의 `similar_choices` 로 함께 보낸다. 그래서 기록에서는 제안자가 직접 누른 값과 AI 가 미리 고른 값이 구분되지 않았다.
  ADR 0054 의 '남은 것'에 적은 문제다.
- 평가에는 둘을 나눠야 한다. AI 판정을 사람 판단과 비교하려는데 미리 고른 값을 사람 판단으로 세면, AI 와 사람이 실제보다 더 일치하는
  것처럼 보인다.

## 선택지
1. 그대로 둔다. 기록으로는 AI 판정을 평가할 수 없다.
2. 웹이 미리 고른 값을 보내지 않는다. 서버는 선택이 없는 행에 같은 기본 선택을 쓰므로(ADR 0054) 동작은 같다. 하지만 ③ 특이사항
   판정표(`rows_for_writing`)는 요청 선택만 본다. 그래서 본문이 달라지고, 화면과 서버가 같은 선택을 들고 다니는 구조가 깨진다.
3. **선택마다 출처를 함께 보내고, 기록 줄마다 남긴다.** 동작은 바꾸지 않는다.

## 결정
3을 택한다(소유자 결정).
- **요청** `SimilarChoice.source: "user" | "ai_prefill"`(`domain/models/request.py`)를 둔다. 보내지 않으면 `user` 다. 옛 웹 캐시(새 번들 전 화면)나
  CLI·MCP 가 넘긴 선택은 명시적 선택이기 때문이다. 필드 설명에도 적었다. `ProposalRequest.choice_sources()` 는 doc_id → 출처를 돌려준다.
- **뜻** `user` 는 제안자가 직접 바꾼 값이다. AI 기본 선택과 다른 값을 눌렀거나, 기본 선택이 없는 행(규칙 판정·AI 실패·판정 전)에서
  고른 경우다. `ai_prefill` 은 AI 기본 선택이 그대로 남은 값이다. 선택을 지워 기본 선택으로 돌아간 행도, 기본 선택과 같은 값을 다시 누른 행도
  여기에 든다.
- **기록** `choice_records(..., sources=)` 는 줄마다 `source` 를 쓴다. 묶음 행이면 선택이 걸린 doc_id 의 출처를 쓰고, 출처가 없으면 `user` 를 쓴다.
  `choice_log.ALLOWED_KEYS` 에 `source` 를 더했다. 서버의 AI 기본 선택(`effective_choice`)은 지금처럼 기록하지 않는다. 기록은 요청에 실린
  선택만 남긴다.
- **옛 줄** 2026-11-04 이전에 쓴 줄에는 `source` 가 없다. 이 줄의 출처는 **모른다**. ADR 0039 이후의 웹 선택에는 미리 고른 값이
  섞여 있다. 평가할 때 `user` 로 보지 말고 따로 둔다.
- **동작은 그대로** 출처는 기록용 메타데이터다. 차단 게이트(`effective_blocking`), 유효 선택(`effective_choice`), `similar_count`,
  ③ 판정표(`rows_for_writing`), 비교표·활용 제안·과제안, 생성 게이트(409)는 출처를 보지 않는다. `prompt_view` 에도 들어가지 않는다
  (`similar_choices` 는 FORM_ONLY).
- **run** run 의 request.json 에 `similar_choices` 가 남으면 `source` 도 함께 남는다(`model_dump`).

## 웹
- 아이디어 저장소(`features/idea/store.ts`)에 `choiceSources`(doc_id → 출처)와 `appliedChoiceSources`([선택 적용] 때의 출처)를 둔다.
  선택과 함께 sessionStorage 에 남으므로 ② 를 닫았다 다시 열어도 그대로다. 새 유사과제 확인 결과가 오면 선택과 함께 비운다.
- `withDefaults` 가 미리 고른 행을 `ai_prefill` 로 표시한다. 이미 고른 행의 값과 출처는 건드리지 않는다. 행 하나를 바꾸는 규칙은
  `chooseRow` 한 곳에 둔다(`features/precheck/model.ts`). 고른 값이 기본 선택과 같으면 `ai_prefill`, 다르거나 기본 선택이 없으면 `user` 다.
  지우면 기본 선택으로 돌아가며 `ai_prefill` 이 된다. 묶음 행 구성원의 옛 선택과 출처는 함께 지운다.
- `choiceList(map, sources)` 는 행마다 `source` 를 싣는다. 그래서 `similar_choices` 를 싣는 모든 요청이 출처를 보낸다. AI 판정, [선택 적용] 의
  비교표·활용 제안·과제안, 과제안 다시·더 만들기, 다듬기, [다음] 뒤 입력에 저장되어 ③ 생성 요청까지 간다.
- 이 기능 전에 저장된 화면 상태(sessionStorage 에 `choiceSources` 없음)는 읽을 때 출처를 추정한다. 그 행의 기본 선택(`default_choices`)과 같은 값은
  `ai_prefill`, 다르면 `user` 다(`inferSources`). 지금 규칙과 같다. 다만 판정 전에 골랐고 뒤에 온 기본 선택과 값이 같은 행은
  `ai_prefill` 로 잘못 추정된다. 이런 경우는 드물다.

## 결과
- 기록 한 줄(키는 이름 순, 값은 예):
  `{"at": "2026-11-04T05:00:00+00:00", "blocking": false, "choice": "unrelated", "doc_id": "alio:…", "idea": "<해시 16자>", "judged_by": "argon",
  "judgment": "same", "keywords": 2, "merged_ids": [], "released": true, "rerank_score": 0.91, "rule_blocking": true, "similarity": 0.8612,
  "source": "user", "tier": "alio"}`
- openapi: `SimilarChoice` 에 선택 필드 `source`(enum user·ai_prefill, 기본 user)가 생긴다. 이 스키마를 쓰는 모든 요청 본문
  (ProposalRequest·RunIn·…)에 반영된다. 응답 필드는 바뀌지 않는다(`default_choices` 에는 출처가 없다).
- 시험: `tests/domain/test_choice_source.py`(줄마다 출처, 생략하면 user, 미리 고름과 직접 바꿈, 묶음 행, 출처가 동작을 바꾸지 않음),
  `tests/entrypoints/test_choice_source_api.py`(`_record_choices` 가 출처를 쓴다. 출처가 있든 없든 ② 응답·생성 게이트가 같다. run 요청에 출처가 남는다),
  vitest `features/precheck/ChoiceSource.test.tsx`·`features/idea/storeSources.test.ts`, e2e `precheck-v3`([선택 적용] 요청 본문의 출처).
- 손대지 않은 것: 기록 시점(생성 요청 때만), Streamlit·CLI·MCP 의 선택 경로(출처를 보내지 않으므로 `user`).
