# feat/card-b-analogy (2026-11-10, ADR 0065 레인 B) 전달 사항

## 전달한 것 — 모두 `config/problem_card.yaml` 스위치 뒤(저장소 값 `enabled: false` 그대로, 꺼져 있으면 종전과 같다)
- **유추 질의** `usecases/novelty.py`: 요청에 카드가 있고 `use.analogy_queries` 면 질의는 `domain/rules/card_queries.card_queries` 한 곳.
  저장 자료는 질의마다 종전 `_candidates`(자료원별 최소 보장) → 같은 문서는 높은 유사도. 실시간 키워드는 `ProblemKeywords.__call__` 이
  요청의 카드에서 그대로(remember 없음) — OpenAlex 가 영문 질의를 받는다. 세션 소유자 `analogy_owner`, 메모 키 `pick_fingerprint`.
- **최종 5건** `domain/rules/analogy_rank.py`(순수 함수) + `_pick_card`: 종전 규칙(하한·철도 제외·같은 제목) → 대상어 겹침(영문 포함) →
  유사도 상위 `rerank_top` 재순위(점수는 순서에만) → 자료원당 `per_source` 먼저, 모자라면 넘긴 것을 순위대로. reranker 없음·실패면
  (공유 문제어 수, 유사도) 순. 3건 미만이면 로그에 `few_analogies=True`(재검색 없음).
- **KIPRIS 분류 검색** `adapters/sources/kipris/client.py`: 2026-11-10 실호출 2회로 확정 — 항목별 검색
  `/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch`, `ipcNumber`("A01M 29/00"·서브클래스 "A01M" 모두 됨), 키 `ServiceKey`,
  레코드 `item`, 총 건수 `count/totalCount`. `search_class`·`count_class`·`KiprisClassCount`(= `PatentClassCount`, 일일 카운터 공유).
  실시간: `LiveSearch` 가 `class_queries`("ipc:" 표식)를 `class_search` 자료원(KIPRIS)에만 덧붙이고 `LiveKipris` 가 분류 검색으로 보낸다.
- **모순 → novel** `recommend_novel.py`·`recommend_projects.py`·`novel_recommendation.py`·`views.py`: `[문제 정의]` 구획 + 과제명
  `principles`(카드 원리 번호 안에서만) → 응답 `titles[].principles: [{number, name}]`. 차별화 갈래에는 넣지 않는다.
- **보완 질문** `clarify_input.py`: 카드 규칙 문장 최대 2개(원인 1 + 추정 항목 1)를 맨 앞에, 기존 상한 4 안에서.
- **조립** `composition.build_novelty`(설정·reranker 전달), `build_patent_class_count`(새), `build_clarifier`·`build_recommender`(설정 전달).

## 남은 일
- `entrypoints/api/app.py` 가 `recommendations_payload(..., card=req.problem_card)` 로 카드를 넘겨야 발명 원리 이름이 응답에 나온다(PR 본문 조각).
- `build_patent_class_count` 를 레인 A 의 분류 코드 확인에 잇는 것(조립).
- 측정 줄(recommend_metrics)의 `few_analogies` 칸은 넣지 않았다(로그만) — 허용 칸 표가 공용이라.
