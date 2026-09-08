"""RRF (Reciprocal Rank Fusion). 순수 랭킹 규칙 — 저장소 구현과 무관.

여러 검색 랭킹(FTS BM25, 벡터 코사인, 질의별 랭킹)을 점수 스케일 보정 없이 합친다.
score(id) = sum over rankings of 1 / (k + rank), rank 는 1부터.
"""

from __future__ import annotations

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, k: int = DEFAULT_K
) -> list[tuple[str, float]]:
    """각 랭킹은 좋은 순서로 정렬된 id 목록. 융합 점수 내림차순으로 반환.

    동점은 '처음 등장한 랭킹의 순위'가 앞선 쪽을 우선해 안정 정렬한다.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    scores: dict[str, float] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for list_no, ranking in enumerate(rankings):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            if item_id not in first_seen:
                first_seen[item_id] = (list_no, rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]], kv[0]))
