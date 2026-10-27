"""판독 캐시 → DB 적재 (P3 ⑥). Argon 호출 없음 — ReadImages(reader=None) 로 캐시·OCR 결과만 모은다.

- 페이지 문서는 manifest 의 page_doc_id 로 저장소에서 찾는다 (본문이 이기는 규칙·source 결정용).
  없으면 페이지 없이 적재한다 (source 는 manifest 의 source — SourceType 에 없으면 건너뜀).
- dry_run 이면 upsert 하지 않고 건수만 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rra.application.ports import DocumentRepository
from rra.application.usecases.link_image_readings import LinkReport, link_readings
from rra.application.usecases.read_images import ReadImages
from rra.domain.models import Document


@dataclass
class ImageIngestReport:
    snapshot: str
    results: int = 0
    documents: int = 0
    chunks: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    removed_personal: dict[str, int] = field(default_factory=dict)
    pages_found: int = 0
    dry_run: bool = False
    doc_ids: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot,
            "dry_run": self.dry_run,
            "results": self.results,
            "documents": self.documents,
            "chunks": self.chunks,
            "skipped": dict(self.skipped),
            "removed_personal": dict(self.removed_personal),
            "pages_found": self.pages_found,
        }


class IngestImageReadings:
    def __init__(
        self, reader: ReadImages, repo: DocumentRepository, *, chunk_max_chars: int = 1500
    ):
        if reader.reader is not None:
            raise ValueError(
                "적재는 판독 캐시만 쓴다 — ReadImages 를 reader=None 으로 만들어야 한다"
            )
        self.read, self.repo, self.chunk_max_chars = reader, repo, chunk_max_chars

    async def __call__(
        self, *, dry_run: bool = False, limit: int | None = None
    ) -> ImageIngestReport:
        read_report = await self.read(limit=limit)
        pages: dict[str, Document] = {}
        for r in read_report.results:
            key = r.item.page_doc_id
            if key and key not in pages:
                doc = await self.repo.get_document(key)
                if doc is not None:
                    pages[key] = doc
        linked: LinkReport = link_readings(
            read_report.results, pages, chunk_max_chars=self.chunk_max_chars
        )
        report = ImageIngestReport(
            snapshot=read_report.snapshot,
            results=len(read_report.results),
            documents=len(linked.documents),
            chunks=len(linked.chunks),
            removed_personal=dict(linked.removed_personal),
            pages_found=len(pages),
            dry_run=dry_run,
            doc_ids=[d.doc_id for d in linked.documents],
        )
        for reason in linked.skipped.values():
            report.skipped[reason] = report.skipped.get(reason, 0) + 1
        if not dry_run and linked.documents:
            await self.repo.upsert(linked.documents, linked.chunks)
        return report
