"""생성 근거 검색의 관련도 하한 (이슈 #2) — 순수 규칙.

hybrid_search 는 질의와 무관해도 k 개를 채운다. multilingual-e5 코사인은 분포가 압축돼
무관한 한국어 문서도 0.78~0.80, 무관한 영어 논문도 0.74~0.78 이 나오므로(2026-10-26 골든셋 측정,
tests/fixtures/relevance_golden.json), 그대로 넘기면 모델이 억지로 인용한다.

규칙 — 청크가 근거로 남으려면:
1. 질의와의 코사인(`Chunk.similarity`)이 `min_similarity` 이상. 벡터 색인이 없어 similarity 가
   None 이면 이 조건은 보지 않는다.
2. 청크에 한글이 있으면 질의 키워드(일반어 제외, `keywords.query_keywords`)가 `min_keyword_hits`
   개 이상 등장. 영어 논문 청크는 한국어 질의와 토큰이 겹칠 수 없으므로 키워드 조건을 적용하지
   않는다 (유사도만 본다).

임계치는 골든셋 01(궤도, 관련 영어 논문 최저 0.793)·03(도서관, 최고 0.783)으로 정했고
테스트가 그 측정값으로 고정한다. 표본이 쌓이면 config/overlap.yaml `evidence_floor` 에서 조정한다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import Chunk
from rra.domain.rules.keywords import KeywordRule, keyword_overlap

_HANGUL = re.compile(r"[가-힣]")

DropReason = Literal["similarity", "keywords"]


class RelevanceFloor(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_similarity: float = Field(default=0.79, ge=0.0, le=1.0)
    min_keyword_hits: int = Field(default=1, ge=0)


def has_hangul(text: str) -> bool:
    return bool(_HANGUL.search(text or ""))


def drop_reason(
    chunk: Chunk, query: str, floor: RelevanceFloor, keywords: KeywordRule
) -> DropReason | None:
    """근거에서 빼야 하면 그 이유, 남기면 None."""
    if chunk.similarity is not None and chunk.similarity < floor.min_similarity:
        return "similarity"
    if floor.min_keyword_hits and has_hangul(chunk.text):
        if len(keyword_overlap(query, chunk.text, keywords)) < floor.min_keyword_hits:
            return "keywords"
    return None


def filter_chunks(
    chunks: list[Chunk], query: str, floor: RelevanceFloor, keywords: KeywordRule
) -> tuple[list[Chunk], list[tuple[Chunk, DropReason]]]:
    """(남긴 청크, (뺀 청크, 이유)) — 순서 유지."""
    kept: list[Chunk] = []
    dropped: list[tuple[Chunk, DropReason]] = []
    for c in chunks:
        reason = drop_reason(c, query, floor, keywords)
        if reason is None:
            kept.append(c)
        else:
            dropped.append((c, reason))
    return kept, dropped
