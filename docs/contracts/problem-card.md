# 계약 메모 — 문제 정의 카드 1차 (ADR 0065, 2026-11-10)

제안문을 AI 1회로 진단해 '문제 정의 카드'를 만들고, 유추 검색·새로움 확인·장벽 점검·과제명 추천이 장소어가 아니라
문제 기준으로 돌게 한다. 레인 A(진단·검증·수정·기록)·B(유추·과제안·KIPRIS·보완 질문)·C(웹)가 서로 기다리지 않도록 정한 계약.
**이 파일과 아래 "0단계 파일"은 0단계(통합 담당, 메인 세션)만 고친다.** 레인이 계약을 바꿔야 하면 멈추고 보고한다.

0단계 파일: 이 파일, `docs/history/decisions/0065-problem-card.md`, `src/rra/domain/models/problem_card.py`,
`src/rra/domain/models/request.py`(`problem_card` 칸), `src/rra/domain/models/novel.py`(`NovelTitle.principles`),
`src/rra/application/usecases/problem_card_contract.py`, `config/problem_card.yaml`(키 이름 — 값은 통합 담당이 바꾼다),
`config/llm.yaml` 의 `stages.diagnose`, `src/rra/config_loader.py`(`problem_card_config`·`card_edits` 경로),
`web/src/api/types-problem-card.ts`, `web/src/api/types-novel.ts`(`principles`).

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
| `analogy_queries` | 저장 자료 질의 = 사다리 3단 + 영문 기능 문장(질의마다 종전 `_candidates`, 같은 문서는 높은 유사도). 실시간 검색 키워드 = ko: 사다리 구체·일반화 단, en: 영문 기능 문장(+ `objects_en`·`actions_en` 조합) → OpenAlex 가 영문 질의를 받는다 |
| `analogy_rank` | 최종 5건 = ① 하한 0.79·철도 분야 제외·같은 제목 제외(종전) ② `rank.require_object` 면 대상어(`objects_ko`/`objects_en`, 낱말 앞부분 일치)가 겹친 자료만 — **영문 자료도** ③ 유사도 상위 `rank.rerank_top` 건을 reranker 로 재순위(질의 = 국문 기능 문장 + " / " + 영문 기능 문장), 점수는 **순서에만** 쓴다(하한 없음) ④ 순위대로 자료원당 `rank.per_source` 건까지 먼저 담고, 5건이 안 차면 넘긴 것을 순위대로 채운다. reranker 가 없으면 ③ 을 (공유 문제어 수, 유사도) 순으로 대신한다. 규칙은 `domain/rules/analogy_rank.py`(순수 함수) |
| `contradiction` | novel 프롬프트에 `[문제 정의]` 구획(기능 문장·모순·발명 원리 번호·이름·근본 원인·문제 성격). 과제명 `principles`(카드의 원리 번호 안에서만, 밖이면 뺀다) → 화면 "발명 원리 n. 이름". differentiate 경로에는 넣지 않는다 |
| `kipris_class` | `verified != unverified` 인 IPC 로 KIPRIS 분류 검색(실시간, 키워드 검색과 함께, 일일 상한 공유) → 유추 후보에 합친다. 분류 검색 파라미터는 KIPRIS 실응답으로 확정하고 fixture 를 남긴다 |
| `clarify` | 보완 질문 앞자리에 규칙 문장(AI 호출 없음) 최대 2개: 원인 질문 1(`needs_check` 또는 원인이 `추정`) + `추정` 항목 확인 1(기능 문장 → 모순 순). 기존 상한 4 안에서 |

- `why_relevant` 의 공유 문제어 = 카드 문제어 중 문서에 나온 것(장소어 없음).
- 메모 키: 카드를 쓰는 호출만 `input_key(req, core, [카드 서명])`. 카드가 없으면 키가 종전과 같다. 카드 서명 = 쓰는 칸만의 sha256(레인 B `analogy_rank` 또는 `novelty`).
- `few_analogies` 신호: 유추 결과가 3건 미만이면 측정 줄에 기록만(재검색 없음).
- `PatentClassCount`(계약 모듈) = KIPRIS 분류 검색 총 건수 — 레인 B 가 구현, 조립이 레인 A 의 `ClassCodeCheck` 에 넣는다.

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
3. OpenAlex 1건 이상(비둘기·실시간 또는 저장 자료 유추).
4. 새로움 확인(novel 갈래 search ∥ analogy 단계) 시간 증가 10초 이내.
5. pytest·vitest·e2e·계약 통과.

## 9. 지켜야 할 것
헥사고날 계층·보안 규칙(A: LLM 출력은 JSON 만·카드 글은 프롬프트에 넣을 때 태그 무력화, C: 허용 도메인만, D: 키·사번·개인정보를 출력·기록하지 않는다,
E: SQL 파라미터 바인딩), `.env` 수정 금지, `data/`·양식 원본 커밋 금지, `main` 직접 커밋·force push 금지, 운영(launchd·`tools/deploy.sh`)에 손대지 않는다.
골든셋·`rra eval` 은 쓰지 않는다. 실제 AI·임베딩·reranker 를 쓰는 측정은 `tools/with_heavy_lock.py` 로.
