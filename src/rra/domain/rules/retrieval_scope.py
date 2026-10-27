"""자료 종류별 검색 범위 (레인 A, 2026-10-27).

- policy(공사 경영목표·전략·ESG·정책 자료): 정책적 중요도·경영전략 정합성 근거.
  정책 근거 추천(policy_suggest).
- korail_news(보도자료): 특이사항·현황 보조만.
- 둘 다 기술적 중요도 근거·유사과제 판정(precheck/find_similar)에는 쓰지 않는다.
섹션별 혼합 비율은 통합 세션의 retrieval_mix.yaml 이 맡는다 — 여기서는 제외 규칙만 둔다.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.domain.models import Document

# 유사과제 판정(find_similar)에서 빼는 자료 종류. [P2] 감사·통계도 과제가 아니다. 발주
# 용역(procurement)은
# 남긴다.
OVERLAP_EXCLUDED_DOC_TYPES: frozenset[str] = frozenset(
    {"policy", "korail_news", "audit", "statistics"}
)
# 정책 근거 추천에 쓰는 자료 종류
POLICY_DOC_TYPES: frozenset[str] = frozenset({"policy"})


def overlap_candidates(hits: Iterable[tuple[Document, float]]) -> list[tuple[Document, float]]:
    """유사과제 판정 대상만 남긴다 (정책·보도자료 제외). 순서 유지."""
    return [(d, s) for d, s in hits if d.doc_type not in OVERLAP_EXCLUDED_DOC_TYPES]
