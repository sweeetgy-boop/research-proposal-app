from __future__ import annotations

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import OwnUnit, judge


class PrecheckOverlap:
    def __init__(
        self,
        repo: DocumentRepository,
        k: int = 10,
        own: OwnUnit | None = None,
        keywords: KeywordRule | None = None,
    ):
        self.repo, self.k, self.own, self.keywords = repo, k, own, keywords

    async def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        query = req.search_text()
        hits = await self.repo.find_similar(query, k=self.k)
        return judge(hits, own=self.own, query=query, keywords=self.keywords)
