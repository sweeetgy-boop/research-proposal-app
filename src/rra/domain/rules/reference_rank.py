"""② 관련 연구(참고 논문)의 관련 순위 — "관련 순위 n/총수" (순수 규칙).

비교표의 참고 논문 열(`kind="reference"`, ADR 0053)에 제안자가 ② 관련 연구에서 본 목록 안의
위치를 붙인다. 순위는 그 목록의 화면 순서(점수 내림차순, `overlap_candidates.related_research` 와
같은 순서)의 1부터 센 자리이고, 총수는 목록 길이다. 같은 점수는 목록 순서를 그대로 둔다. 목록 밖
문서는 순위가 없다.

2026-11-04 소유자 결정: 고정 경계값으로 나눈 "검색 관련도 높음·중간·낮음"(옛 research_relevance)
을 이 순위 표시로 바꿨다. 경계값 재측정은 시범 사례가 쌓인 뒤. 점수 숫자는 화면에 보이지 않는다
(ADR 0039).
"""

from __future__ import annotations

from collections.abc import Iterable


def research_ranks(items: Iterable[tuple[str, float]]) -> dict[str, tuple[int, int]]:
    """관련 연구 목록 [(doc_id, 점수)] → {doc_id: (순위, 총수)}.

    점수 내림차순(같은 점수는 목록 순서 유지 — 안정 정렬)으로 1부터 센다. 같은 doc_id 가 두 번
    나오면 처음 것만 센다. 빈 목록이면 빈 dict."""
    seen: set[str] = set()
    rows: list[tuple[str, float]] = []
    for doc_id, score in items:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        rows.append((doc_id, float(score)))
    ordered = sorted(rows, key=lambda r: -r[1])
    total = len(ordered)
    return {doc_id: (i, total) for i, (doc_id, _) in enumerate(ordered, start=1)}
