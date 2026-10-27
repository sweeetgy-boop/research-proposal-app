"""U4 차별성 비교표 유스케이스 — precheck 알림 상위 5건의 문서를 읽어 표를 만든다 (LLM 없음)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from rra.application.ports import DocumentRepository
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.comparison import ComparisonTable
from rra.domain.rules.comparison import MAX_PROJECTS, comparison_table

Precheck = Callable[[ProposalRequest], Awaitable[list[OverlapAlert]]]


@dataclass
class CompareProjects:
    repo: DocumentRepository
    precheck: Precheck | None = None

    async def __call__(
        self, req: ProposalRequest, alerts: list[OverlapAlert] | None = None
    ) -> ComparisonTable:
        if alerts is None:
            if self.precheck is None:
                raise ValueError("alerts 또는 precheck 가 필요합니다.")
            alerts = await self.precheck(req)
        ranked = sorted(alerts, key=lambda a: (-a.similarity, a.doc_id))
        docs: dict[str, Document | None] = {}
        for alert in ranked:
            if alert.doc_id in docs:
                continue
            docs[alert.doc_id] = await self.repo.get_document(alert.doc_id)
            if len(docs) >= MAX_PROJECTS:
                break
        return comparison_table(req, alerts, docs, differentiation=req.differentiation)
