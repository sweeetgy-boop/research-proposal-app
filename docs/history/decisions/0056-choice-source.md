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

## 2026-11-04 후속: event·중복 한 줄 규칙 (feat/choice-log-apply)

### 맥락
- 위 결정까지 선택 기록은 생성 요청(`POST /v1/runs`) 때만 남았다. ② 에서 제안자가 [선택 적용] 을 여러 번 누르며 판단을 바꿔도 기록에는
  마지막 생성 직전의 선택만 남았다. 판단이 어떻게 바뀌었는지가 평가 재료에서 빠졌다.
- 웹의 [선택 적용] 은 비교표(`/v1/precheck/comparison`)·활용 제안(`/differentiate`)·과제안(`/recommendations`)만 불렀다. 이 요청들은 화면에
  들어올 때·다시 열 때·과제안 다시 만들기 때도 나가므로, 여기서 적용을 추정하면 한 번 누른 것이 여러 줄이 된다.
  `endpoints-precheck.ts` 의 `/v1/precheck/choices` 도우미는 있었지만 쓰이지 않았다.

### 결정 (소유자 결정)
- **기록 시점** 줄마다 `event` 를 쓴다. `generate` 는 생성 요청 때(지금과 같다), `apply` 는 ② [선택 적용] 때다.
- **apply 신호** 웹은 [선택 적용] 을 누를 때마다 `POST /v1/precheck/choices?apply=true` 를 한 번 보낸다(적용한 선택 + 출처, 본문은
  `ProposalRequest`). 서버는 `apply=true` 일 때만 기록한다. 쿼리를 빼면(옛 호출·시험) 지금처럼 선택 반영만 돌려주고 기록하지 않는다.
  응답은 `apply` 유무와 상관없이 같다. 웹은 이 응답을 화면에 쓰지 않고, 실패해도 적용을 막지 않는다(오류 문구 없음).
  비교표·활용 제안·과제안 요청에서는 적용을 추정하지 않는다.
- **중복 한 줄** 같은 세션이 같은 선택을 잇따라 보내면 한 번만 쓴다.
  - 세션 = 로그인 주체 키(`_owner_key` — 직원·공용 계정은 가명 키, 관리 토큰은 run 저장소 키) + 아이디어 해시. 둘을 다시 해시한 16자
    (`similar_choice.session_key`)를 메모리에만 쓴다. 주체 키·사번은 기록 줄에 들어가지 않는다(세션 해시도 넣지 않는다).
  - 같은 선택 = 서명(`similar_choice.choice_signature`)이 같다. 서명은 **event** 와 기록 줄의 (doc_id, 선택, 출처) 집합의 해시다.
    점수·판정·시각·차단 해제·행 순서는 서명에 들지 않는다. 줄이 없는 요청(선택 없음)은 서명이 없고, 쓰지 않으며, 마지막 서명도 바꾸지 않는다.
  - 잇따름 = 그 세션이 마지막으로 **기록한** 서명과 비교한다(`is_repeat`). 사이에 다른 서명이 기록되면 다시 쓴다.
  - event 가 서명에 들어가므로 apply → generate(같은 선택)는 다른 사건이라 둘 다 남는다. apply → apply(같은 선택)는 한 번,
    generate → generate(같은 선택으로 다시 생성)도 한 번이다. 생성 뒤 같은 선택을 다시 적용하면 마지막 서명(generate)과 달라 남는다.
  - 상태는 API 프로세스 메모리(`entrypoints/api/choice_dedupe.ChoiceDedupe`, 최근 500 세션 LRU)다. 다시 띄우면 잊으므로 그 뒤 첫 기록은
    같은 선택이라도 한 번 더 남는다. 쓰기에 실패하면(`OSError`, 경고 로그만) 마지막 서명으로 삼지 않아 다음 요청이 다시 쓴다.
  - 규칙(서명·반복·세션 키)은 `domain/rules/similar_choice`, 상태는 진입점에 둔다.
- **허용 키** `choice_log.ALLOWED_KEYS` 에 `event` 를 더했다.
- **옛 줄** 2026-11-04 이전에 쓴 줄에는 `event` 가 없다. 그때는 생성 요청 때만 기록했으므로 `generate` 로 본다. 이 기능 전의 기록에는
  apply 가 없고, 생성 요청이 잇따라도 모두 남아 있다(중복 한 줄 규칙 전).
- **동작은 그대로** 차단 게이트·건수·③ 판정표·비교표·활용 제안·과제안·생성 게이트(409)·응답 본문은 바뀌지 않는다. 기록 실패는 막지 않는다.

### 결과
- 기록 한 줄(키는 이름 순, 값은 예):
  `{"at": "2026-11-04T06:00:00+00:00", "blocking": false, "choice": "unrelated", "doc_id": "alio:…", "event": "apply", "idea": "<해시 16자>",
  "judged_by": "argon", "judgment": "same", "keywords": 2, "merged_ids": [], "released": true, "rerank_score": 0.91, "rule_blocking": true,
  "similarity": 0.8612, "source": "user", "tier": "alio"}`
- openapi: `POST /v1/precheck/choices` 에 선택 쿼리 `apply`(boolean, 기본 false)가 생긴다. 요청 본문·응답은 그대로다.
- 시험: `tests/domain/test_choice_log_event.py`(event, 서명이 보는 것과 안 보는 것, 반복·재설정, 옛 줄, 세션 키),
  `tests/entrypoints/test_choice_dedupe.py`(apply·generate 순서, 세션별·LRU), `tests/entrypoints/test_choice_log_apply_api.py`(apply 한 묶음·반복 생략·
  바뀐 선택·generate·세션 분리·줄에 주체 키·사번·원문 없음·응답 동일·기록 실패 비치명), vitest `features/precheck/ApplyRecord.test.tsx`,
  e2e `precheck-v3`([선택 적용] 한 번에 apply 요청 한 번, 본문 = 비교표 요청의 선택·출처).
- 손대지 않은 것: Streamlit·CLI·MCP(그 경로에는 [선택 적용] 기록이 없다), 기록 파일 위치·권한.

- 소유자 확인(2026-11-04): 중복 한 줄 규칙은 생성 요청에도 그대로 적용한다(생성 횟수는 runs 기록으로 충분). "연달아"는 그 세션에서 **바로 앞에 기록한 선택**과 같을 때만이다 — A→B→A 는 세 묶음 모두 남는다(`tests/entrypoints/test_choice_dedupe.py`).
- 2026-11-04: 시험 계정 줄 표시·집계 제외 — 배포 확인용 임시 사번은 `rra auth staff add --test` 로 등록(`staff.json test_hmacs`, HMAC 표시만)하고, 그 세션(`Principal.test`)의 선택 기록·과제안 측정 줄에 `test: true` 를 붙인다(지우지 않고 표시, 그 밖의 줄은 키 없음). `rra feedback stats` 는 기본으로 시험 줄을 빼고 센다(`--include-test` 로 포함). 계기: 배포 확인 세션이 선택 기록 30줄·측정 1줄을 남겨 손으로 지웠다.
