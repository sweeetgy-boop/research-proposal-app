# 계약 메모 — 문제 정의 카드 1차 (ADR 0065, 2026-11-10)

제안문을 AI 1회로 진단해 '문제 정의 카드'를 만들고, 유추 검색·새로움 확인·장벽 점검·과제명 추천이 장소어가 아니라
문제 기준으로 돌게 한다. 레인 A(진단·검증·수정·기록)·B(유추·과제안·KIPRIS·보완 질문)·C(웹)가 서로 기다리지 않도록 정한 계약.
**이 파일과 아래 "0단계 파일"은 0단계(통합 담당, 메인 세션)만 고친다.** 레인이 계약을 바꿔야 하면 멈추고 보고한다.

0단계 파일: 이 파일, `docs/history/decisions/0065-problem-card.md`, `src/rra/domain/models/problem_card.py`,
`src/rra/domain/models/request.py`(`problem_card` 칸), `src/rra/domain/models/novel.py`(`NovelTitle.principles`),
`src/rra/application/usecases/problem_card_contract.py`, `config/problem_card.yaml`(키 이름 — 값은 통합 담당이 바꾼다),
`config/llm.yaml` 의 `stages.diagnose`, `src/rra/config_loader.py`(`problem_card_config`·`card_edits` 경로),
`web/src/api/types-problem-card.ts`, `web/src/api/types-novel.ts`(`principles`),
`src/rra/domain/rules/card_queries.py`(카드 → 질의·지문)와 그 시험 두 파일.

## 0. 소유자 결정 (2026-11-10)
1. 유추 정렬 = 대상어 겹침 → 기능 문장 재순위 → 자료원당 2건 우선, 모자라면 순위대로. 대상어에는 사다리 **일반화 단**의 대상어도 포함(비둘기 → 조류).
2. 진단은 뒤에서 채운다. 목표 중앙값 6초 안팎. 화면은 기다리지 않는다.
3. 분류 코드 확인은 1차에 저장 특허의 실제 IPC + KIPRIS 건수. 공식 코드표는 1회 내려받기 허용(출처·날짜 기록) — 1차 필수 아님.
4. 모순은 novel 갈래에만. 차별화 갈래는 카드 저장만.
5. 관리자 전용(403) 규칙·통계 화면은 2차.
6. 과제안 다시 만들기는 **모두 버튼**(모순 수정 포함, 자동 실행 없음).
7. 항목마다 '근거 있음(제안문에 있음) / 추정(AI 가 채움)'. 근거가 없으면 비워 둔다. 추정은 보완 질문으로 확인.
8. 수정 짝은 저장하되 1차에서는 **본인 수정만** 지시문 예시로. 공용 계정(guest) 수정은 저장·학습 제외.
9. 안전망: 카드가 없거나(느림·실패) 스위치가 꺼져 있으면 종전 방식. **스위치 기본값 꺼짐.** 기존 세션·24시간 캐시 키는 그대로.
10. 레인 A 가 끝나면 4사례 실제 AI 카드를 손 예시와 나란히 보고 → 소유자 확인 뒤에만 스위치를 켠다.
11. 자료원 응답 24시간 캐시는 카드·종전 질의가 공유한다(나누지 않음). 세션·메모만 가른다(4.1절).
12. 완료 기준의 'OpenAlex 1건 이상'은 유추 검색 기준으로 잰다.

2차 설계 제안에 넣을 것(1차 범위 밖 — 구현하지 않는다): 조건부 분석 실행, 사전 후보(장소어·동의어·기능 문장↔IPC)와 승인 절차, 관리자 통계·403,
다른 사용자 수정의 일반화(수정 유형만), 공식 코드표, **새로움 확인에 카드(영문 기능 문장 포함)를 쓰는 방안 — ② 판정과 기준을 어떻게 맞출지 포함**.

## 1. 레인과 파일 소유권 (같은 파일을 두 레인이 고치지 않는다)

| 레인 | 일 | 소유 파일 |
|---|---|---|
| A `feat/card-a-diagnose` | 진단(AI 1회)·규칙 검증·수정 반영·수정 짝/card_edit 기록·본인 예시·가짜 모드·REST | `domain/rules/problem_card.py`·`triz.py`·`card_edits.py`(새), `usecases/diagnose_problem.py`·`edit_problem_card.py`(새), `adapters/classification/`(새), `adapters/logging/card_edit_log.py`(새)·`choice_log.py`(허용 칸), `adapters/llm/prompts/diagnose.md`, `ports/prompt_library.py`·`adapters/llm/prompt_files.py`·`tests/fakes.py`(`diagnose()` 추가), `adapters/fake/`(진단 응답), `adapters/persistence/`(코드 건수 조회 메서드 추가만), `entrypoints/api/problem_card_routes.py`(새, `register(...)`), `composition.py` 새 함수 `build_problem_diagnosis`·`build_card_editor` |
| B `feat/card-b-analogy` | 카드 기반 유추 질의·정렬, 영문 → OpenAlex, 모순 → novel 장벽·과제명, KIPRIS 분류 검색·건수, 보완 질문 | `usecases/novelty.py`, `domain/rules/novelty.py`, `domain/rules/analogy_rank.py`(새), `usecases/recommend_novel.py`·`recommend_projects.py` 의 novel 경로, `domain/rules/novel_recommendation.py`, `adapters/llm/prompts/recommend_novel.md`, `usecases/clarify_input.py`, `adapters/sources/kipris/`, `adapters/sources/live.py`, `usecases/live_search.py`, `config/novelty.yaml`, `entrypoints/views.py` 의 novel payload(`principles`), `composition.build_novelty`·`build_live_sources` 본문 |
| C `feat/card-c-web` | ① 카드 4줄·전문가 분석 펼치기·수정·[과제안 다시 만들기] 표시·발명 원리 표시 | `web/src/features/idea/ProblemCard*.tsx`(새)·`store.ts`·`web/src/routes/Idea.tsx`, `web/src/api/problemCard.ts`(새), `web/src/features/precheck/NovelPlans.tsx`·`web/src/routes/Precheck.tsx`(stale 표시만), `web/src/lib/labels.ts`, `web/e2e/problem-card.spec.ts`(새) |

공용 파일 규칙은 2026-11-09 과 같다(`docs/contracts/wave-1109.md` 1절): `entrypoints/api/app.py`·`application/ports/__init__.py`·`entrypoints/cli.py`·
`docs/status.md`·`timeline.md`·`openapi.json`·`README.md`·`CLAUDE.md` 는 레인이 고치지 않는다. 라우트 등록·조립 연결·`domain/rules/problem_labels.py`
새 코드는 PR 설명 "통합 때 메인이 반영할 조립 변경" 절에 코드 조각으로 적는다. 레인은 조각 파일(`docs/history/timeline.d/2026-11-10-<브랜치>.md`·
`docs/status.d/<브랜치>.md`·`docs/history/progress.d/<브랜치>.md`)만 쓴다. 레인 A·B 가 서로의 모듈을 import 하지 않는다 — 잇는 것은 조립.

## 2. 카드 (`domain/models/problem_card.py`)
- 글 칸 `CardText{value, origin: ai|user, basis: 근거 있음|추정, ai_value, needs_check}`. `value=""` 허용.
- `facets`(현상·대상·**장소**·원인·피해·원하는 결과), `function_ko`·`function_en`, `ladder[구체·일반화·추상화]`,
  `terms{objects_ko, actions_ko, objects_en, actions_en}`, `contradiction{improve, worsen, principles[{number 1~40, name}]}`,
  `causes[≤2]`, `ipc[≤3]`·`science_class[≤2]`(`ClassCode{code, label, origin, verified: table|corpus|kipris|unverified, count}`),
  `nature{kind: 단순|난해|복잡, mode: 도입형|실증형|연구형}`, `signals[]`, `methods[]`, `checks[]`.
- 화면 4줄 = 기능 문장(`function_ko`) · 원인(`causes[0]`) · 모순 · 분류(`ipc`+`science_class`).
- **basis 규칙(레인 A, 규칙으로 판정 — AI 의 자기 신고를 믿지 않는다)**: 항목 글의 핵심 낱말이 제안 입력(가제·현황·원인·한계·목표)에
  있으면 `근거 있음`, 아니면 `추정`. 모순·분류 코드·사다리 일반화/추상화 단은 성격상 대개 `추정`.
- **문제어 규칙**: `objects_*` = 구체 단 + 일반화 단의 대상어. 추상화 단의 말·`facets.place` 의 낱말·`novelty.yaml place_ko`·일반어는 넣지 않는다.
  레인 A 가 채우고 검증(장소어가 섞이면 뺀다), 레인 B 가 읽는다.
- **검증(레인 A, `domain/rules/problem_card.py`)**: JSON 객체만 파싱 · 입력에 없는 숫자·기관명·법령명이 든 칸은 비움(기존
  `recommendation` 규칙 재사용) · 한자·가나 칸은 비움 · 영문 기능 문장에 한글이 있으면 비움 · 발명 원리는 번호 1~40 만, 이름은
  고정 목록(`domain/rules/triz.py`)으로 **바꿔 쓴다** · 분류 코드는 `ClassCodeCheck` 결과를 `verified`·`count`·`label` 에 · 제안자의
  원인 칸과 AI 근본 원인이 낱말로 겹치지 않으면 `causes[0].needs_check=True` + `checks=["cause_mismatch"]` · 신호는 열거값만.
- 기능 문장이 비면 진단 실패(`failed`, reason `invalid`) — 카드 없이 진행.

## 3. 진단·수정 REST (레인 A 구현, 레인 C 호출)
카드는 run 을 만들기 전 ① 화면의 상태다 — 서버는 카드를 세션에 저장하지 않는다(웹 `IdeaState.problemCard` → 요청 몸통).

### 3.1 `POST /v1/ideas/diagnose`
요청 `{title_hint?, current_state, root_cause, limitation, goal, previous?: ProblemCard}` (모르는 칸 거부).
응답 200:
```json
{"status": "ok", "card": {…ProblemCard…}, "lines": {"function": "…", "cause": "…", "contradiction": "… ↔ …", "codes": "A01M 29/00 · …"},
 "signal_labels": [{"signal": "unclear_cause", "label": "원인이 뚜렷하지 않거나 여러 가지"}],
 "reason": null, "reason_label": null, "provider": "gemini", "model": "…", "fallback_local": false, "seconds": 5.8}
```
- `status: "off"`(설정 꺼짐)·`"failed"`(실패·시간 초과)면 `card: null` — 화면은 카드를 보이지 않고 그대로 진행한다. 오류 응답(5xx)으로 만들지 않는다.
- 네 칸 중 빈 칸이 있으면 422(기존 필수 슬롯 문구). 클라이언트가 끊으면 취소(`cancel_on_disconnect`).
- `previous` 의 `origin=user` 항목은 그대로 두고 나머지만 채운다.
- 선택 칸 `refresh`(요청)·`reused`(응답) — 같은 제안문의 카드 재사용·고정은 4.4절.

### 3.2 `POST /v1/ideas/diagnose/edit`
요청 `{request: {네 칸+가제}, before: ProblemCard, after: ProblemCard, fields: CardField[]}`.
- 서버는 `fields` 의 항목을 `origin=user`(+ `ai_value` 보존)로 만들고 `CARD_DEPENDENTS` 대로 **그 항목에 기대는 것만** 다시 계산한다.
  - `function_ko` → `derive`(영문·사다리·문제어 중 user 가 아닌 것만 AI 1회로 다시) / `contradiction` → 원리 재검증 /
    `ipc`·`science_class` → 코드 확인 / `cause` → '확인 필요' 재판정.
- 응답 `{card, lines, reruns: Rerun[], plans_stale: bool, recorded: bool}`. 서버는 과제안을 다시 만들지 않는다.
- 기록(6절): 공용 계정이면 기록하지 않는다(`recorded=false`). 시험 계정은 `test: true`.

### 3.3 카드 전달
`ProposalRequest.problem_card`(선택)로 `/v1/precheck/recommendations(·/stream)`·`/v1/precheck/clarify`·`/v1/runs` 에 실린다.
- `FORM_ONLY_FIELDS` — `prompt_view()`·`search_text()`·`keyword_cache_key`·②판정·차단에 들어가지 않는다.
- 서버는 `problem_card.yaml enabled=false` 면 받은 카드를 **무시**한다(소비자가 `ProblemCardConfig.uses(...)` 로 확인).

## 4. 카드를 쓰는 곳 (레인 B) — 모두 "카드가 있고 그 스위치가 켜져 있을 때만", 아니면 종전 코드 경로 그대로
| 스위치 `use.*` | 동작 |
|---|---|
| `analogy_queries` | 질의는 `card_queries` 가 만든다(4.1절). 저장 자료 질의 = 사다리 3단 + 국문·영문 기능 문장(질의마다 종전 `_candidates`, 같은 문서는 높은 유사도). 실시간 검색 키워드 = ko: 사다리 구체·일반화 단 + 국문 기능 문장, en: 영문 대상어·작용어 조합 + 영문 기능 문장 → OpenAlex 가 영문 질의를 받는다 |
| `analogy_rank` | 최종 5건 = ① 하한 0.79·철도 분야 제외·같은 제목 제외(종전) ② `rank.require_object` 면 대상어(`objects_ko`/`objects_en`, 낱말 앞부분 일치)가 겹친 자료만 — **영문 자료도** ③ 유사도 상위 `rank.rerank_top` 건을 reranker 로 재순위(질의 = 국문 기능 문장 + " / " + 영문 기능 문장), 점수는 **순서에만** 쓴다(하한 없음) ④ 순위대로 자료원당 `rank.per_source` 건까지 먼저 담고, 5건이 안 차면 넘긴 것을 순위대로 채운다. reranker 가 없으면 ③ 을 (공유 문제어 수, 유사도) 순으로 대신한다. 규칙은 `domain/rules/analogy_rank.py`(순수 함수) |
| `contradiction` | novel 프롬프트에 `[문제 정의]` 구획(기능 문장·모순·발명 원리 번호·이름·근본 원인·문제 성격). 과제명 `principles`(카드의 원리 번호 안에서만, 밖이면 뺀다) → 화면 "발명 원리 n. 이름". differentiate 경로에는 넣지 않는다 |
| `kipris_class` | `verified != unverified` 인 IPC 로 KIPRIS 분류 검색(실시간, 키워드 검색과 함께, 일일 상한 공유) → 유추 후보에 합친다. 분류 검색 파라미터는 KIPRIS 실응답으로 확정하고 fixture 를 남긴다 |
| `clarify` | 보완 질문 앞자리에 규칙 문장(AI 호출 없음) 최대 2개: 원인 질문 1(`needs_check` 또는 원인이 `추정`) + `추정` 항목 확인 1(기능 문장 → 모순 순). 기존 상한 4 안에서 |

- `why_relevant` 의 공유 문제어 = 카드 문제어 중 문서에 나온 것(장소어 없음).
- 캐시·세션·메모 키는 4.1절(0단계 모듈 `domain/rules/card_queries.py`)을 따른다.
- `few_analogies` 신호: 유추 결과가 3건 미만이면 측정 줄에 기록만(재검색 없음).
- `PatentClassCount`(계약 모듈) = KIPRIS 분류 검색 총 건수 — 레인 B 가 구현, 조립이 레인 A 의 `ClassCodeCheck` 에 넣는다.

### 4.1 캐시·세션·메모 키 — **카드 전체가 아니라 실제로 보낸 질의 기준** (2026-11-10 소유자 지시)
현재 구조(확인): 유추 검색이 거치는 재사용 지점은 넷이고, 그대로 두면 둘이 틀린다.

| 지점 | 지금 키 | 기능 문장을 고치면 |
|---|---|---|
| 자료원 응답 24시간 캐시(`live_search.cache_key`) | 자료원 + **보낸 질의** + 건수 | 질의가 달라져 새로 호출 — 이미 질의 기준 ✅ |
| 실시간 검색 세션(`session_key`, 프로세스 안) | 소유자 + 입력 글 + 정책 근거 | ❌ 입력 글이 같아 **옛 세션(옛 질의 결과)을 다시 쓴다** |
| 유추 키워드 기억(`ProblemKeywords.remember`) | 입력 글 | ❌ 같은 입력·다른 카드가 서로 덮어쓴다 |
| 유추 결과 메모(`ProblemAnalogySearch._memo`, 30분) | 입력 글 + 핵심어 | ❌ 옛 5건을 다시 준다 |
| 평소 키워드 24시간 캐시(`keyword_cache_key`) | 입력 글 + 정책 근거 | 유추 인스턴스는 `keyword_cache=False` 라 읽지도 쓰지도 않는다 ✅ (그대로 둔다) |

레인 B 가 지킬 것:
1. 질의는 `card_queries(card, use_queries=…, use_class=…)` **한 곳**에서 만든다. None 이면 종전 코드 경로(규칙 문제어·종전 소유자·종전 메모 키)를
   한 글자도 바꾸지 않고 탄다.
2. 실시간 검색 세션 소유자 = `analogy_owner(ANALOGY_OWNER, queries)` — 카드가 있으면 `analogy:card:<질의 지문>`. 질의가 바뀌면 새 세션이다.
3. 유추 키워드는 `remember` 를 거치지 않고 **요청에 실린 카드에서 그대로** 만든다(`ProblemKeywords.__call__` 이 `card_queries(req.problem_card)` 를 먼저 본다).
   카드 질의를 입력 글 키의 캐시·기억에 쓰지 않는다.
4. 유추 결과 메모 키 = `input_key(req, core, *memo_groups(pick_fingerprint(queries, card, rank)))` — 검색 지문 + 정렬에 쓰는 값(문제어·재순위 질의·정렬 설정).
5. KIPRIS 분류 검색의 캐시 키 질의 문자열은 `class_query(code)`("ipc:" 표식) — 같은 글자의 키워드 검색과 겹치지 않는다.
6. 새로움 확인(`WideNoveltyCheck`)은 1차에 카드를 쓰지 않는다 — 평소 키워드·종전 키 그대로(② 판정과 같은 기준이어야 하므로).

성질(시험으로 고정 — `tests/domain/test_card_queries.py`·`tests/application/test_card_query_cache.py`, 레인 B 는 지우거나 약하게 하지 않는다):
- 기능 문장(또는 그에 따라 다시 만든 사다리·영문)을 고치면 지문·세션 키·메모 키가 바뀌고, 자료원을 **다시 호출**한다(24시간 캐시 재사용 없음).
- 원인·모순처럼 질의에 들어가지 않는 칸만 고치면 검색 지문은 그대로다(다시 검색하지 않는다). 문제어만 바뀌면 정렬 메모 키만 바뀐다.
- 카드를 쓰는 키에는 늘 `:card:` 표식이 있어 스위치 꺼짐(카드 없음) 때의 세션·메모와 **같아질 수 없다**. 카드가 없을 때의 키는 종전 값과 같다.
- 자료원 응답 캐시는 "그 자료원에 그 질의를 보낸 응답"이라, 카드에서 나온 질의와 종전 질의가 글자까지 같을 때만 같은 항목을 쓴다(같은 요청의 같은 응답). **나누지 않고 지금처럼 공유한다**(2026-11-10 소유자 결정).
- 레인 B 는 여기에 `ProblemAnalogySearch` 수준 시험을 더한다: 카드 A → 카드 A'(기능 문장 수정) 호출이 메모·세션을 다시 쓰지 않고 새 질의로 검색하는지,
  스위치 꺼짐 호출의 결과·키가 종전 스냅샷과 같은지.

### 4.2 통합 때 바뀐 것 (2026-11-10, 실제 AI 카드 4사례 측정 뒤 — 메인)
- **정렬**: 재순위 점수 = 카드 기능 문장 질의와 **제안문 문제어 질의(종전 규칙)** 중 높은 쪽(`rank.with_request_query`), 후보에도 그 질의의 검색 결과를 합친다 —
  카드 기능 문장이 제안자의 원인에 좁게 맞춰져도 직접 관련 자료(공중화장실 복합악취)가 밀리지 않게. `rank.rerank_top` 40 → 30(질의 2개).
- **자료원당 우선**은 재순위 상위 `rank.priority_window`(15) 안에서, 점수가 1위의 `rank.priority_min_ratio`(0.25) 이상인 자료에만. 그 밖은 순위대로 채운다
  (점수가 거의 0 인 다른 자료원 자료가 자료원 몫으로 들어오던 것).
- **실시간 국문 키워드**는 짧은 "대상어 작용어" 짝 먼저, 그다음 구체 단(`card_queries.live_ko`) — 긴 구절은 ScienceON 이 0~4건만 돌려줬다.
- **대상어**: 국문·영문 기능 문장에 나온 말은 `novelty.yaml` 장소 말 목록에 있어도 대상어로 남긴다(궤도 틀림의 "궤도"·track). `facets.place` 의 말은 뺀다.
- **모순이 비면** novel 프롬프트에 `[문제 정의]` 구획·`principles` 지시를 넣지 않는다 — 카드 없는 프롬프트와 글자까지 같다. 문제 성격은 프롬프트에도 넣지 않는다.
- **문제 성격·신호**는 화면에 표시하지 않는다(카드에 기록만).
- **진단 지시문**: 기능 문장은 제안문 낱말을 그대로 옮기지 않고 대상의 실제 행동·작용으로, 일반어(침입·방지·관리)만으로 된 문장 금지.
- **수정 기록**: 표현 다듬기(유사도 ≥ `polish_similarity`)도 줄은 남기고(`recorded=true`) 본인 예시에서만 뺀다. 꺼진 상태의 `diagnose/edit` 는 409.
- **근거 있음/추정 판정은 원인·모순·분류에만**(2026-11-10 소유자 결정). 기능 문장·사다리는 화면에 '추정' 대신 **"AI가 다시 쓴 문장"** 으로 표시하고(제안자가 고치면 '직접 고침'),
  보완 질문의 확인 문장도 기능 문장은 묻지 않는다(원인 1 + 모순이 추정일 때 1). 카드의 `function_*.basis` 값은 남아 있지만 화면·질문·분포(`basis_counts`)에 쓰지 않는다.
- **겹치는 제목**: 꼬리말(`rank.dup_title_suffixes`)을 뺀 제목 낱말이 짧은 쪽 기준 `rank.dup_title_ratio`(0.6) 이상 겹치면 순위 높은 하나만(`analogy_rank.drop_similar_titles`).
- **철도 분야 판정 보강**(`novelty.yaml rail_field`, 스위치와 무관): 영문 구 `phrases_en`·약한 말 `context_terms_en`(2개 이상 함께일 때만)·붙여 쓴 한글 합성어 `contains_ko`.
  카드의 대상·장소가 철도 시설이면 그 요청에 한해 약한 영문 말은 혼자서도, 한글 철도 용어는 낱말 안 어디에든(`novelty.card_rail_terms`).
- `science_class` 는 운영 DB 에 이름만 있어 **분류 이름**으로 받고 이름으로 센다. IPC 저장 자료 확인은 메인그룹 단위.

### 4.3 '자료 없음'을 억지로 채우지 않는다 (2026-11-10 소유자 확정 — 메인)
원칙: **대상 자체가 철도 시설인 과제는 철도 자료가 나오는 것이 맞다. 자료가 없으면 채우지 않고, '없는 것'과 '못 찾은 것'을 구분해 보인다.**
- **철도 시설 과제 판정**(`novelty.rail_asset_basis`): 카드의 대상어(`terms.objects_ko`)나 대상 칸(`facets.target`)의 낱말이 철도 용어(`novelty.yaml rail_field.terms_ko` —
  궤도·선로·레일·전차선·열차…)로 **시작**하면 철도 시설 과제. **장소 칸은 보지 않는다**("철도역사의 비둘기"는 대상이 비둘기 → 철도 시설 과제 아님).
  철도 시설 과제는 유추에서 철도 분야 거르기를 하지 않고 제목을 '관련 선행 자료'로(`AnalogyReport.kind = related`), 이유 문장은 "같은 대상(…)을 다룬 선행 자료".
  그 밖의 과제(비둘기·악취·관광)는 종전대로 철도 자료를 거른다(영문·합성어 포함).
- **검색 범위 보고**(`domain/models/novel.AnalogyReport` → 응답 `analogy_report`, 문장은 `views.analogy_report_payload` 가 만든다): 실시간 자료원 N곳 중 M곳 확인,
  확인 못 한 자료원과 사유(서버 IP·한도·시간 초과). 응답하지 않은 자료원이 있으면 `partial`(일부만 확인). 0건이면 "찾지 못했습니다(검색 범위: 한국어·영어, 자료원 …)" +
  [아는 자료 직접 추가](② 관련 연구의 [차별화에 참고]로 이동). 카드를 쓰지 않은 요청에는 이 칸이 없다 — 화면은 종전 그대로.
- **대상어 일치**: 띄어쓰기 무시(4자 이상 한글 — "가속도센서" = "가속도 센서") + 동의어 묶음 `problem_card.yaml object_synonyms`. 일반화 단 대상어·영문 대상어는 원래 포함.
- **약한 자료 제외**(`analogy_rank.cut_weak`): 재순위 점수가 1위의 `rank.weak_ratio`(0.15) 미만이면 뺀다 — 절대값이 아니라 1위 대비(눈금이 사례마다 다르다).
  대상어가 **제목**에 나온 자료는 점수가 낮아도 남긴다(`weak_keep_title_object`). 5건을 억지로 채우지 않는다.
  기준값 근거(2026-11-10 4사례·실제 AI 카드): 화면에 나온 관련 자료의 최저 비율 0.196(비둘기 5위 "교량용 버드넷"), 무관 자료의 최고 비율 0.117(굴뚝칼새 논문) → 그 사이 0.15.
  네 사례 모두 자르기 전·후 표시 5건이 같았다(잘린 것은 6위 이하). `dropped_weak` 는 자른 탓에 비게 된 자리 수만 센다.
  한계: 1위 점수가 유독 높은 사례(관광 0.95)는 6위 이하의 관련 자료도 비율상 '약함'이 된다 — 5건이 차는 한 화면에는 영향이 없다.

### 4.4 같은 제안문은 같은 카드 — 재사용·고정·'카드 방식만 0건' 안내 (2026-11-10)
부를 때마다 AI 를 새로 부르면 같은 제안문에도 카드가 달라져 유추 결과가 흔들린다. 스위치는 `problem_card.yaml reuse: {enabled, cache_days}` —
맨 위 `enabled` 가 꺼져 있으면 저장소를 만들지도 읽지도 쓰지도 않는다(종전과 같다). 규칙 `domain/rules/card_reuse.py`, 유스케이스 `usecases/card_reuse.CardReuse`,
저장소 `adapters/persistence/card_store.py`(CachePort), 조립 `composition.build_card_reuse`.

- **순서**: `diagnose` = ① 이 사용자가 고정한 카드 → ② 공용 캐시 → ③ AI. 응답에 선택 칸 `reused: "pinned" | "cached" | null`(새로 만들었으면 null).
  재사용한 응답은 AI·분류 코드 확인을 부르지 않는다(`provider`·`model` null, `seconds` 0). `previous` 의 사용자 항목(origin=user)은 재사용한 카드 위에도 그대로 얹는다.
- **공용 캐시(제안문 기준)**: 키 = sha256(입력 글 해시 + 진단 지시문 지문 + 모델 이름). 입력 글 해시 = 가제·현황·원인·한계·목표를 칸 순서대로 `normalize_query`(NFKC·소문자·공백 하나) 한 것.
  값은 **검증을 통과한 AI 카드만**(입력 원문·사용자 식별값 없음, 클라이언트가 보낸 카드는 넣지 않는다). 보관 `reuse.cache_days`(기본 30, 0 이면 공용 캐시 없음).
  실패·시간 초과는 캐시하지 않는다. 지시문이나 모델이 바뀌면 키가 달라져 옛 카드는 쓰이지 않는다(보관 기간 뒤 읽히지 않음).
  **그 사람에게 맞춘 결과는 넣지 않는다** — 본인 수정 예시가 지시문에 들어갔거나(`examples > 0`) `previous` 에 사용자 항목이 있던 진단.
- **고정(사용자별)**: 키 = sha256(가명 ID + 입력 글 해시), 값 = 그 사용자가 확인한 카드. 만료 없음. 확인 = (a) `problem_card` 를 실은 요청이
  `/v1/precheck/recommendations`(·`/stream`)·`/v1/runs` 에 온 것, (b) `diagnose/edit` 로 고친 것(응답의 카드). **공용 계정(guest)·로그인 없음은 고정하지 않고 읽지도 않는다**
  (공용 캐시만). 시험 계정·관리자는 고정한다. 다른 사용자의 고정 카드는 어떤 경우에도 돌려주지 않는다(키에 가명 ID).
- **다시 진단**: 요청 선택 칸 `refresh: bool = false`. true 면 ①② 를 건너뛰고 AI 를 새로 부른다. 결과는 공용 캐시를 갈아 끼운다(위 '맞춘 결과' 는 제외).
  고정은 그대로 두고, 사용자가 새 카드로 진행하면(확인) 그때 갈아 끼운다. 웹 카드 머리의 [다시 정리] 가 `refresh: true` 로 부른다(진행 중 "문제 정리 중…",
  실패하면 지금 카드를 그대로). `reused = "pinned"` 면 머리에 "확인한 카드", "cached" 는 표시 없음.
- **저장 위치**: `data/cache/problem_cards/<sha256>.json`(공용), `data/cache/problem_cards/pinned/<sha256>.json`(고정) — 폴더 700·파일 600, 파일 이름은 해시뿐.
  데이터 위치 표 키 `problem_cards`(`problem_card.yaml paths.cards` 로 덮어씀). 가짜 모드(`RRA_FAKE_LLM`)는 메모리.
- **키는 입력 글 기준**이다 — 4.1절의 유추 세션·메모 키(실제 보낸 질의 지문)와 별개이고 서로 건드리지 않는다.
- **로그**: `card.reuse kind=pinned|cached|none`(INFO, 값 없음). 저장소 오류는 재사용 없이 진행(예외 클래스명만).
- **카드 방식만 0건**: 카드 경로(`analogy_rank`)의 최종이 0건일 때만, 이미 받아 둔 **종전 문제어 질의**(`rank.with_request_query` 로 후보에 합친 것)의 후보에 종전 고르기
  (`_pick` — 규칙 문제어 1개 이상·종전 철도 거르기)를 한 번 적용해 건수를 센다 → `AnalogyReport.legacy_count`. 저장소·자료원을 더 부르지 않는다(1건 이상이면 계산도 안 함).
  응답 `analogy_report.card_hint`(선택, 서버가 만든 문장): `legacy_count > 0` 이고 `count == 0` 일 때
  "문제 정의 카드 기준으로는 찾지 못했지만, 카드 없이 찾으면 n건이 있습니다. 핵심 문제 카드(기능 문장·대상)를 확인해 주세요." 웹은 0건 구획에 그 문장 +
  [카드 확인하러 가기](① `/new`). 종전 방식의 자료 자체는 보이지 않는다(카드 기준이 아니다). `with_request_query` 가 꺼져 있으면 세지 않는다(더 부르지 않기 위해).
### 4.5 스위치 켬 (2026-11-10)
- `config/problem_card.yaml enabled: true`. 파일이 없을 때의 기본값은 여전히 꺼짐. 끌 때는 이 값만 false.
- **제목 겹침으로 지우는 규칙은 끔**(`rank.dup_title_ratio: 0`). 악취 사례의 "악취 역류 차단 장치"(2019, E03C 1/298 — 싱크 배수 유닛의 수막)·"하수구 악취 역류 방지기"(2000,
  E03F 5/04 — 판 높이차 물막이)·"악취 역류 방지장치"(2009, E03F 5/06·F16K 15/03 — 맨홀 덮개 개폐판)는 초록으로 보면 서로 다른 발명이다. e5 초록 유사도는 0.89~0.93 으로
  높지만 이 임베딩은 무관한 글도 0.80 을 넘어 '같은 자료'의 근거가 못 된다. 비슷한 자료는 지우지 않고 **묶어서 비교 분석**하는 방식으로 다시 설계한다(다음 PR).
- 켜기 전 측정(실제 AI 카드 4사례, 실시간 포함, 운영 DB 사본): 비둘기·관광 무관 자료 0건, 궤도 틀림은 '관련 선행 자료' 5건, 악취는 역류 장치 3건(서로 다른 발명) + 공중화장실 복합악취 +
  환기구 역류 방지 댐퍼. 유추 시간 증가 최대 +3.0초. 가짜 모드 전체 e2e 56건 통과.

## 5. 웹 (레인 C)
- ① 상세 입력 아래 '핵심 문제' 카드 4줄(기능 문장·원인·모순·분류). 네 칸이 채워지면(간편 입력 `onFilled` 또는 상세 입력에서 네 칸이 모두 찬 뒤
  입력이 멈추면) **뒤에서** `diagnose` — 화면을 막지 않고, 정책 근거 팝업과 독립. 단계는 늘리지 않는다.
- 줄마다 '근거 있음'/'추정' 배지, `needs_check` 면 '확인 필요'. 맞으면 그대로 [다음], 틀리면 그 줄을 고친다 → `diagnose/edit`.
- "전문가 분석 펼치기"(접힘): 항목 나누기·사다리·영문 기능 문장·근본 원인 2단계·발명 원리·문제 성격·켜진 신호.
- [다음] 을 눌렀을 때 진단이 아직 안 끝났거나 실패·꺼짐이면 **카드 없이** 진행(요청에 `problem_card` 를 싣지 않는다). 진행 중 호출은 취소.
- 네 칸이 바뀌면 카드는 '입력이 바뀜 — 다시 진단' 표시(자동 재진단은 입력이 멈춘 뒤 1회, user 항목 보존).
- `plans_stale` 이면 ② 에 "문제 정의가 바뀌었습니다 — [과제안 다시 만들기]" 한 줄(자동 실행 없음).
- 화면 문구에 내부 코드·"run" 금지(기존 e2e 검사). `status="off"` 면 카드 영역 자체가 없다 → 스위치가 꺼진 지금 화면은 종전과 같다.
- sessionStorage `rra-idea` 에 옛 상태가 있어도 깨지지 않게 `problemCard` 는 선택 칸.

## 6. 기록·학습 (레인 A)
- **수정 짝** `data/feedback/card_edits.jsonl`(600, 폴더 700, 허용 칸 방식): `at, user(가명 ID), test, idea(해시 16자), field, before, after,
  similarity, function(당시 국문 기능 문장), methods, signals`. 글은 `rules/privacy` 로 이름·연락처를 지운 뒤. 공용 계정(guest)은 쓰지 않는다.
- **선택 기록**(`similar_choices.jsonl`)에 `event: "card_edit"` 줄: `at, event, idea, field, before(요약 ≤80자), after(≤80자), methods, signals, test`.
  기존 집계(`feedback_stats`)의 by_event 는 '기타'로 세므로 `card_edit` 칸을 더한다.
- **본인 예시**: 새 진단 때 `CardEditLogPort.by_user(본인)` 중 `similarity < learning.polish_similarity`(다듬기 제외) · `test` 아님 줄에서,
  지금 입력과 임베딩 유사도 `example_min_similarity` 이상 상위 `max_examples` 건을 지시문 `[이 제안자가 전에 고친 예]` 구획에. 다른 사용자 줄은
  어떤 경우에도 넣지 않는다. 임베딩은 `EmbeddingPort` 로 메모리에서(색인 없음).
- 학습 자료는 파일 하나(JSONL)·yaml 스위치(`learning.*`)로 끈다. 사전 후보·관리자 통계는 2차.
- 로그에는 건수·상태·예외 클래스명만(D).

## 7. 가짜 모드 (`RRA_FAKE_LLM`)
레인 A: `adapters/fake` 가 `diagnose` 프롬프트에 검증을 통과하는 카드 JSON 을 돌려준다(입력 낱말 사용). e2e 는 설정 사본(`RRA_CONFIG_DIR`)에서
`enabled: true` 로 돌린다 — 저장소의 `config/problem_card.yaml` 은 `false` 그대로.

## 8. 통과 조건
레인 PR 마다: `pytest -q -n auto`, `PYTHONPATH=src lint-imports`(8건), `ruff check src tests`, `web/`: typecheck·vitest·e2e, CI 전부.
**스위치가 꺼진 상태에서 결과가 지금과 같아야 한다**(레인 B: 카드 없는 유추·novel 프롬프트·보완 질문 회귀 시험).

완료 기준(통합 뒤, 못 미치면 병합하지 않고 보고):
1. 비둘기 유추 5건 중 문제와 무관한 자료 0건.
2. 악취 유추 5건이 현재와 같거나 더 낫다.
3. OpenAlex 1건 이상 — **유추 검색 기준**(비둘기 사례의 유추 실시간 검색이 OpenAlex 에서 1건 이상 받거나, 유추 최종 5건에 OpenAlex 자료 1건 이상. 새로움 확인 쪽 건수는 세지 않는다).
4. 새로움 확인(novel 갈래 search ∥ analogy 단계) 시간 증가 10초 이내.
5. pytest·vitest·e2e·계약 통과.

## 9. 지켜야 할 것
헥사고날 계층·보안 규칙(A: LLM 출력은 JSON 만·카드 글은 프롬프트에 넣을 때 태그 무력화, C: 허용 도메인만, D: 키·사번·개인정보를 출력·기록하지 않는다,
E: SQL 파라미터 바인딩), `.env` 수정 금지, `data/`·양식 원본 커밋 금지, `main` 직접 커밋·force push 금지, 운영(launchd·`tools/deploy.sh`)에 손대지 않는다.
골든셋·`rra eval` 은 쓰지 않는다. 실제 AI·임베딩·reranker 를 쓰는 측정은 `tools/with_heavy_lock.py` 로.
