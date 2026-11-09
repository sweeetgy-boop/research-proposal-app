"""말뭉치 IDF 표 만들기 (`rra db idf`, 레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §3).

저장소의 청크를 훑어 문서(doc_id)마다 토큰 집합(`keywords.tokens` — 어절 + 조사 제거, 핵심어 판정과
같은
토큰)을 모으고 idf = ln(N/df) 를 계산해 캐시 포트에 저장한다. 적재(`rra ingest`)·재색인(`rra
reindex`)
끝에 한 줄로 부르는 훅은 레인 소유 밖이라 PR 본문 제안으로 둔다 — 지금은 이 유스케이스를 CLI 가 직접
부른다. 읽기만 한다(DB 수정 없음). 출력은 건수만."""

from __future__ import annotations

from dataclasses import dataclass

from rra.application.ports.idf_cache import IdfCachePort
from rra.application.ports.table_facts import CorpusAccessPort
from rra.domain.rules.idf import IdfWeightingRule, IdfWeights, compute_idf
from rra.domain.rules.keywords import tokens

SCAN_LIMIT = 5_000_000  # 전체 청크를 다 읽기 위한 상한 (운영 DB 3만여 청크)


@dataclass(frozen=True)
class IdfReport:
    documents: int
    chunks: int
    terms: int
    max_idf: float


class BuildIdf:
    def __init__(
        self,
        repo: CorpusAccessPort,
        cache: IdfCachePort,
        *,
        rule: IdfWeightingRule | None = None,
        scan_limit: int = SCAN_LIMIT,
    ):
        self.repo, self.cache = repo, cache
        self.rule = rule or IdfWeightingRule()
        self.scan_limit = scan_limit

    async def __call__(self) -> IdfReport:
        chunks = await self.repo.sample_chunks(self.scan_limit)
        per_doc: dict[str, set[str]] = {}
        for c in chunks:
            per_doc.setdefault(c.doc_id, set()).update(tokens(c.text))
        weights = compute_idf(
            per_doc.values(), min_doc_freq=self.rule.min_doc_freq, max_terms=self.rule.max_terms
        )
        self.cache.save(weights)
        return IdfReport(
            documents=weights.documents,
            chunks=len(chunks),
            terms=len(weights.values),
            max_idf=weights.max_idf,
        )


def load_idf(cache: IdfCachePort | None) -> IdfWeights | None:
    """조립용 — 캐시가 없거나 비었으면 None (가중 없음 = 종전)."""
    if cache is None:
        return None
    try:
        return cache.load()
    except Exception:  # 캐시 손상은 가중 없음으로
        return None
