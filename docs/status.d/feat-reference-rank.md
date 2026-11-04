# feat/reference-rank (2026-11-04) 전달 사항

소유자 결정 1·2(2026-11-04) 반영. 비교표 참고 논문 열의 고정 경계값 표시("검색 관련도 높음·중간·낮음", #118)를
② 관련 연구 목록 안의 자리 "관련 순위 n/총수" 로 바꿨다. 경계값 재측정은 시범 사례가 쌓인 뒤.

## 전달한 것
- **응답** 비교표(`/v1/precheck/comparison`, `/v1/runs/{id}/comparison`) 열에 `relevance_rank: int|null`·`relevance_total: int|null`.
  reference 열에서만 값이 있고, 제안자가 본 ② 관련 연구 목록(`related_research`, 점수 내림차순 = 화면 순서)의 1부터 센 자리와
  목록 길이다. 목록 밖·similar 열·제안 열은 null. `relevance`(high/mid/low) 필드는 없앴다. `similarity`(점수)는 그대로(화면에 안 씀).
  `rra api schema` 생성물(`docs/openapi.json`)은 바뀌지 않는다(응답이 dict) — 계약 메모 `docs/contracts/reference-papers.md` 를 고쳤다.
- **규칙** `domain/rules/reference_rank.research_ranks`(순수 — 점수 내림차순 안정 정렬, 같은 점수는 목록 순서, 중복 doc_id 는 처음 것만).
  `ComparisonColumn.relevance_rank`·`relevance_total`, `comparison.reference_column(…, similarity, rank)`.
  `comparison_table(reference_scores=…)` 가 관련 연구 목록 전체(목록 순서)를 받아 순위를 낸다.
- **목록 출처**는 그대로: precheck 메모(`memo(req).related_research`) → 없으면 `PrecheckOverlap.search_research(req)` 한 번.
- **없앤 것** `domain/rules/research_relevance.py`, `config/overlap.yaml candidates.research.relevance`, `config_loader.research_relevance`,
  `build_comparer` 의 `relevance=` 인자, `CompareProjects.relevance`, 웹 `REFERENCE_RELEVANCE_LABELS`·`referenceRelevanceLabel`.
- **웹** `types.ts ComparisonColumn.relevance_rank?`·`relevance_total?`, `labels.ts referenceRankLabel(rank, total)` → "관련 순위 2/5"
  (없거나 말이 안 되는 값이면 null). `ComparisonView` 표 머리·카드 제목 아래(`data-testid="reference-relevance"` 유지).
- **문서** 측정 문서 `docs/eval-2026-11-04-reference-relevance.md` 맨 위에 "경계값 표시는 순위 표시로 바뀜(2026-11-04 소유자 결정),
  재측정은 시범 사례가 쌓인 뒤". ADR 0054 결정에 CLI·MCP·Streamlit 활용 제안의 종전 후보 대체 유지 한 줄(소유자 확인).
  CLAUDE.md 2026-11-04 줄의 참고 논문 열 설명.

## 시험
- pytest: 순위 규칙(점수 순서·동점은 목록 순서·목록 밖 None·중복), 메모 경로(열 순서는 reference_ids 그대로), 다시 검색 경로,
  목록이 비면 순위 없음, 설정에 경계값 없음, REST 가짜 모드(② 응답 `related_research` 순서와 같은 n/총수, `relevance` 키 없음).
- vitest: 표·카드 "관련 순위 2/5"·"1/5", 유사과제·목록 밖·옛 서버 열은 표시 없음, "검색 관련도"·점수 숫자 없음, axe 0, `referenceRankLabel` 경계값.
- e2e `reference-papers.spec.ts`: 가짜 모드 관련 연구는 `scienceon:fake-1` 1건 → "관련 순위 1/1".

## 남은 것
- 경계값(또는 다른 표시) 재측정은 시범 사례가 쌓인 뒤.
