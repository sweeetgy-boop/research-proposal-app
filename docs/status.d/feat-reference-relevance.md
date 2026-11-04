# feat/reference-relevance (2026-11-04) 전달 사항

## 전달한 것
- **응답** 비교표(`/v1/precheck/comparison`, `/v1/runs/{id}/comparison`) 열에 `relevance: "high"|"mid"|"low"|null` 을 더했다.
  reference 열에서만 값이 있고, `similarity` 에는 이제 ② 관련 연구 e5 점수가 들어간다(목록 밖이면 null). `rra api schema` 생성물은 바뀌지 않는다(응답이 dict) — 계약 메모 `docs/contracts/reference-papers.md` 에 적었다.
- **규칙** `domain/rules/research_relevance.ResearchRelevanceRule`(순수, 높음 ≥ high · 중간 ≥ mid · 낮음), `ComparisonColumn.relevance`,
  `comparison.reference_column(…, similarity, relevance)` 를 둔다.
- **설정** `config/overlap.yaml candidates.research.relevance {high: 0.895, mid: 0.885}` 이고, 읽는 곳은 `config_loader.research_relevance` 다.
  조립은 `build_comparer` 가 맡는다.
- **점수 출처** `CompareProjects._research_scores` 가 precheck 메모(`memo(req).related_research`)에서 가져온다. 메모가 없으면
  `PrecheckOverlap.search_research(req)`(같은 질의·자료원)로 한 번 다시 검색한다. 도메인에는 I/O 가 없다.
- **웹** `types.ts ComparisonColumn.relevance?` 를 더했다. `labels.ts REFERENCE_RELEVANCE_LABELS`·`referenceRelevanceLabel` 로
  "검색 관련도 높음·중간·낮음" 을 만든다. `ComparisonView` 는 선행연구 열의 표 머리와 카드 제목 아래에 이 말을 보인다(`data-testid="reference-relevance"`).
  숫자는 보이지 않는다.
- **측정** `docs/eval-2026-11-04-reference-relevance.md`(개발 DB, 골든셋 10건 + not_similar 2건, 수치만).

## 시험
- pytest +13: 경계 표 시험, 설정값, 메모 경로, 다시 검색 경로, 참고 논문이 없으면 검색 안 함, `search_research`, 가짜 모드 REST 에서 `scienceon:fake-1` 가 "low".
- vitest +1: 높음·중간·낮음·없음, 유사과제 열에는 없음, 카드에도 같은 말, 숫자 없음, axe 0.
- e2e `reference-papers.spec.ts`: 선행연구 열에 "검색 관련도 낮음"(가짜 저장소는 낱말 겹침 비율이라 늘 낮음)이 보이고 숫자가 없다.

## 남은 것
- 경계 폭이 0.01 이라 임베딩 모델·적재 자료가 바뀌면 다시 재야 한다. reranker 점수가 분리도는 더 높지만 쓰지 않았다(이유는 측정 문서에 있다).
- 영문(OpenAlex) 논문은 표본에 없었다.
