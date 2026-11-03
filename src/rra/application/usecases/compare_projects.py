"""U4 차별성 비교표 유스케이스 — 유사과제 상위 5건의 문서를 읽어 표를 만든다.

2026-10-28 레인 A:
- similar_only=True(REST ②) 면 제안자가 [유사함] 으로 고른 행(req.similar_choices)만 넣는다. 고른
행이
  없으면 기존 과제 행 없이 "유사한 과제를 고르면 비교표가 만들어집니다".
- 기존 과제 칸은 CellExtractor(Argon → 로컬 → 규칙)가 원문에서 뽑은 1~2문장. 없으면 규칙 추출.
- 초안이 있으면(draft: 초안 섹션 목록) 제안 행을 초안으로 채운다.

2026-11-03 참고 논문(ADR 0053): req.reference_ids(② 관련 연구에서 고른 doc_id)를 저장소에서 읽어
유사과제 열 뒤에 kind="reference" 열로 붙인다(요청 순서). 칸은 유사과제와 같은 방식(AI 추출 →
규칙 추출 → 제목 기준). [유사함] 0건이어도 참고 논문이 있으면 안내 문구(empty_reason)는 없다. 없는
id·볼 수 없는 문서(공용 계정의 internal)는 조용히 뺀다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from rra.application.ports import DocumentRepository
from rra.application.usecases.references import load_references
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
        refs, _ = await load_references(self.repo, req.reference_ids, exclude=list(docs))
        if refs:
            empty_reason = None
        extracted: dict[str, dict[str, str]] = {}
        by: str | None = None
        if self.extractor is not None and getattr(self.extractor, "enabled", True):
            targets = [d for d in docs.values() if d is not None] + refs
            extracted, by = await self.extractor(targets)
        table = comparison_table(
            req,
            alerts,
            docs,
            differentiation=req.differentiation,
            extracted=extracted,
            draft=draft_cells(draft) if draft is not None else None,
            empty_reason=empty_reason,
            references=refs,
        )
        if extracted:
            table = table.model_copy(update={"extraction": "ai", "extraction_by": by})
        return table

    async def _add_missing(
        self, req: ProposalRequest, alerts: list[OverlapAlert]
    ) -> list[OverlapAlert]:
        """[유사함] 으로 골랐지만 이번 알림에 없는 문서(메모 만료 등)는 문서를 읽어 행으로
        더한다."""
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
