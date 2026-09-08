from __future__ import annotations

from rra.application.ports import DocumentRepository
from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.rules.overlap import judge


class PrecheckOverlap:
    def __init__(self, repo: DocumentRepository, k: int = 10):
        self.repo, self.k = repo, k

    def __call__(self, req: ProposalRequest) -> list[OverlapAlert]:
        hits = self.repo.find_similar(req.search_text(), k=self.k)
        return judge(hits)
