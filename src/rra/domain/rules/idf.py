"""핵심어 겹침의 말뭉치 IDF 가중 (레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §3) —
순수.

`generic_terms` 를 손으로 늘리는 대신 말뭉치 문서빈도로 흔한 낱말의 무게를 낮춘다. `keyword_overlap`
(domain/rules/keywords) 은 그대로 두고, 여기 `weighted_overlap` 이 겹친 핵심어마다 가중
`idf(h)/max_idf`(0~1)를 붙인다. 차단의 핵심어 조건은 스위치가 켜졌을 때 `enough_weighted` 로 —
"가중 합 ≥ core_min_hits ×
평균 가중 × ratio". 토큰은 `keywords.tokens`(어절 + 조사 제거)와 같은 것이다.

IDF 표는 적재·재색인 뒤 `usecases/build_idf` 가 계산해 캐시(`data/cache/idf.json`)한다. 표에 없는
토큰은
가장 드문 것(max_idf, 가중 1.0)으로 본다 — 모르는 낱말을 흔하다고 보지 않는다.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

ROUND = 2


class IdfWeights(BaseModel):
    """토큰 → idf (소수 2자리). documents 는 계산에 쓴 문서 수, max_idf 는 표의 최댓값."""

    model_config = ConfigDict(frozen=True)

    values: dict[str, float] = Field(default_factory=dict)
    documents: int = 0
    max_idf: float = 0.0

    def weight(self, token: str) -> float:
        """0~1. 표가 비었거나 토큰이 없으면 1.0(가장 드문 것으로)."""
        if self.max_idf <= 0:
            return 1.0
        v = self.values.get(token)
        if v is None:
            return 1.0
        return max(0.0, min(1.0, v / self.max_idf))


class IdfWeightingRule(BaseModel):
    """config/overlap.yaml `idf_weighting` 절의 값(enabled 는 스위치가 따로 읽는다)."""

    model_config = ConfigDict(frozen=True)

    # 가중 합 ≥ core_min_hits × 평균 가중 × min_weight_ratio. 1.0 = 계약 그대로; 골든셋 측정으로
    # 조정
    min_weight_ratio: float = Field(default=1.0, gt=0.0, le=2.0)
    min_doc_freq: int = Field(default=1, ge=1)  # 표에 넣을 토큰의 최소 문서빈도
    max_terms: int = Field(default=200_000, ge=1000)  # 표 크기 상한 (가장 드문 것부터 자른다)


def compute_idf(
    doc_tokens: Iterable[Iterable[str]], *, min_doc_freq: int = 1, max_terms: int = 200_000
) -> IdfWeights:
    """문서마다 토큰 집합 → idf = ln(N / df) (소수 2자리). df < min_doc_freq 는 뺀다. 표가 max_terms
    를 넘으면 df 가 큰(흔한) 것부터 남긴다 — 드문 토큰은 어차피 "표에 없음 = max" 로 같다."""
    df: Counter[str] = Counter()
    n = 0
    for toks in doc_tokens:
        n += 1
        df.update(set(toks))
    if n == 0:
        return IdfWeights()
    rows = [(t, c) for t, c in df.items() if c >= min_doc_freq]
    rows.sort(key=lambda tc: (-tc[1], tc[0]))
    rows = rows[:max_terms]
    values = {t: round(math.log(n / c), ROUND) for t, c in rows}
    return IdfWeights(values=values, documents=n, max_idf=max(values.values(), default=0.0))


def weighted_overlap(
    query_terms: Sequence[str], doc_tokens: Sequence[str], idf: IdfWeights
) -> list[tuple[str, float]]:
    """핵심어 중 문서에 있는 것(접두 일치 — keywords.core_keyword_overlap 과 같은 규칙)과 그
    가중."""
    out: list[tuple[str, float]] = []
    for kw in query_terms:
        if any(d.startswith(kw) for d in doc_tokens):
            out.append((kw, idf.weight(kw)))
    return out


def mean_weight(terms: Sequence[str], idf: IdfWeights) -> float:
    if not terms:
        return 0.0
    return sum(idf.weight(t) for t in terms) / len(terms)


def enough_weighted(
    hits: Sequence[tuple[str, float]],
    terms: Sequence[str],
    idf: IdfWeights,
    *,
    min_hits: int,
    ratio: float = 1.0,
) -> bool:
    """가중 합 ≥ min_hits × 평균 가중(질의 핵심어 전체) × ratio. 핵심어가 없으면 False."""
    if not terms or not hits:
        return False
    need = min_hits * mean_weight(terms, idf) * ratio
    return sum(w for _, w in hits) >= need - 1e-9
