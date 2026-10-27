"""자료 종류별 검색 범위 (레인 A, 2026-10-27).

- policy(공사 경영목표·전략·ESG·정책 자료): 정책적 중요도·경영전략 정합성 근거.
  정책 근거 추천(policy_suggest).
- korail_news(보도자료): 특이사항·현황 보조만.
- rnd_notice(정부 R&D 사업공고·RFP, P2-7): 정책 근거 추천 후보·공고문 대조(#13, notice_match)만.
- 셋 다 기술적 중요도 근거·유사과제 판정(precheck/find_similar)에는 쓰지 않는다.
섹션별 혼합 비율은 통합 세션의 retrieval_mix.yaml 이 맡는다 — 여기서는 제외 규칙만 둔다.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.domain.models import Document

# 유사과제 판정(find_similar)에서 빼는 자료 종류
OVERLAP_EXCLUDED_DOC_TYPES: frozenset[str] = frozenset({"policy", "korail_news", "rnd_notice"})
# 정책 근거 추천에 쓰는 자료 종류 (공고문은 정책 방향·사업 개요를 담아 후보에 넣는다)
POLICY_DOC_TYPES: frozenset[str] = frozenset({"policy", "rnd_notice"})
# 공고문 대조(notice_match, #13)에 쓰는 자료 종류
NOTICE_DOC_TYPES: frozenset[str] = frozenset({"rnd_notice"})


def overlap_candidates(hits: Iterable[tuple[Document, float]]) -> list[tuple[Document, float]]:
    """유사과제 판정 대상만 남긴다 (정책·보도자료 제외). 순서 유지."""
    return [(d, s) for d, s in hits if d.doc_type not in OVERLAP_EXCLUDED_DOC_TYPES]
