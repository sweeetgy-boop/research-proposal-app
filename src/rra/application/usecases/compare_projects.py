"""U4 차별성 비교표 유스케이스 — 유사과제 상위 5건의 문서를 읽어 표를 만든다.

2026-10-28 레인 A:
- similar_only=True(REST ②) 면 제안자가 [유사함] 으로 고른 행(req.similar_choices)만 넣는다. 고른 행이
  없으면 기존 과제 행 없이 "유사한 과제를 고르면 비교표가 만들어집니다".
- 기존 과제 칸은 CellExtractor(Argon → 로컬 → 규칙)가 원문에서 뽑은 1~2문장. 없으면 규칙 추출.
- 초안이 있으면(draft: 초안 섹션 목록) 제안 행을 초안으로 채운다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from rra.application.ports import DocumentRepository
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.comparison import ComparisonTable
from rra.domain.rules.comparison import (
    EMPTY_NO_SIMILAR,
    MAX_PROJECTS,
    comparison_table,
    draft_cells,
)
from rra.domain.rules.overlap import tier_of
from rra.domain.rules.similar_choice import merge_same_titles, similar_alerts

Precheck = Callable[[ProposalRequest], Awaitable[list[OverlapAlert]]]


@dataclass
class CompareProjects:
    repo: DocumentRepository
    precheck: Precheck | None = None
    extractor: Any | None = None  # CellExtractor (usecases/extract_cells)

    async def __call__(
        self,
        req: ProposalRequest,
        alerts: list[OverlapAlert] | None = None,
        *,
        similar_only: bool = False,
        draft: Iterable[Any] | None = None,
    ) -> ComparisonTable:
        if alerts is None:
            if self.precheck is None:
                raise ValueError("alerts 또는 precheck 가 필요합니다.")
            alerts = await self.precheck(req)
        empty_reason = None
        if similar_only:
            alerts = similar_alerts(merge_same_titles(alerts), req.choice_map())
            alerts = await self._add_missing(req, alerts)
            if not alerts:
                empty_reason = EMPTY_NO_SIMILAR
        ranked = sorted(alerts, key=lambda a: (-a.similarity, a.doc_id))
        docs: dict[str, Document | None] = {}
        for alert in ranked:
            if alert.doc_id in docs:
                continue
            docs[alert.doc_id] = await self.repo.get_document(alert.doc_id)
            if len(docs) >= MAX_PROJECTS:
                break
        extracted: dict[str, dict[str, str]] = {}
        by: str | None = None
        if self.extractor is not None and getattr(self.extractor, "enabled", True):
            extracted, by = await self.extractor([d for d in docs.values() if d is not None])
        table = comparison_table(
            req,
            alerts,
            docs,
            differentiation=req.differentiation,
            extracted=extracted,
            draft=draft_cells(draft) if draft is not None else None,
            empty_reason=empty_reason,
        )
        if extracted:
            table = table.model_copy(update={"extraction": "ai", "extraction_by": by})
        return table

    async def _add_missing(
        self, req: ProposalRequest, alerts: list[OverlapAlert]
    ) -> list[OverlapAlert]:
        """[유사함] 으로 골랐지만 이번 알림에 없는 문서(메모 만료 등)는 문서를 읽어 행으로 더한다."""
        have = {i for a in alerts for i in [a.doc_id, *a.merged_ids]}
        out = list(alerts)
        for doc_id, choice in req.choice_map().items():
            if choice != "similar" or doc_id in have:
                continue
            doc = await self.repo.get_document(doc_id)
            if doc is None:
                continue
            out.append(
                OverlapAlert(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    tier=tier_of(doc),
                    similarity=0.0,
                    blocking=False,
                    basis=doc.text_basis,
                    choice="similar",
                )
            )
        return out
