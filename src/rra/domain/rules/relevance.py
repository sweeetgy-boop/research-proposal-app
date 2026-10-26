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
    # 출처 다양성(2026-10-26, OpenAlex 2,468건 적재 뒤): 한국어 질의는 FTS·벡터 모두 사내 기록(짧은
    # 제목, 0.85)을 앞세워 상위 20 에 영어 논문이 하나도 남지 않았다. 검색은 k×search_multiplier 로
    # 넓게 받고, 하한 통과 청크를 출처(doc_id 접두어)마다 최소 min_per_source 건 보장한 뒤 나머지는
    # 융합 순위대로 채운다. 0 이면 끔.
    min_per_source: int = Field(default=4, ge=0)
    search_multiplier: int = Field(default=4, ge=1)


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


def balance_sources(chunks: list[Chunk], k: int, min_per_source: int) -> list[Chunk]:
    """순위 목록에서 k 개를 고르되 출처(doc_id 의 ':' 앞)마다 최소 min_per_source 건을 먼저 보장.

    보장분은 출처별 순위 순, 나머지는 전체 순위 순. 출처가 많아 보장분만으로 k 를 넘으면 출처를
    돌아가며(각 출처의 첫 순위부터) k 개를 고른다 — 전체 순위로 자르면 뒤에 붙은 출처가 통째로
    빠지기 때문 (2026-10-26, 3 출처 × 8 > 20 에서 논문이 다시 4 건으로 준 데서).
    """
    if k <= 0:
        return []
    if min_per_source <= 0 or len(chunks) <= k:
        return chunks[:k]
    queues: dict[str, list[Chunk]] = {}
    for c in chunks:
        src = c.doc_id.split(":", 1)[0]
        if len(queues.setdefault(src, [])) < min_per_source:
            queues[src].append(c)
    picked: list[Chunk] = []
    if sum(len(q) for q in queues.values()) > k:
        for i in range(min_per_source):  # 라운드 로빈 — 출처 순서는 각 출처의 첫 등장 순
            for q in queues.values():
                if i < len(q) and len(picked) < k:
                    picked.append(q[i])
    else:
        picked = [c for q in queues.values() for c in q]
    chosen = {c.chunk_id for c in picked}
    for c in chunks:
        if len(picked) >= k:
            break
        if c.chunk_id not in chosen:
            chosen.add(c.chunk_id)
            picked.append(c)
    order = {c.chunk_id: i for i, c in enumerate(chunks)}
    return sorted(picked, key=lambda c: order[c.chunk_id])[:k]
