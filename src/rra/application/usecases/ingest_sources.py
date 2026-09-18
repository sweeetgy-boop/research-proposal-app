"""배치 수집: 소스별 search → normalize → (전체) dedup → chunking → repo.upsert.

- 레코드 하나가 깨져도 그 레코드만 건너뛴다.
- 소스 하나가 실패해도 다른 소스는 계속한다.
  실패는 예외 클래스명만 남긴다 (D: 메시지에 URL·키가 섞일 수 있음).
- upsert 는 마지막에 한 번만 호출한다 (저장소 쪽 단일 트랜잭션).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rra.application.ports import DocumentRepository, SourcePort
from rra.domain.models import Chunk, Document
from rra.domain.rules.dedup import dedup
from rra.domain.services.chunking import chunk_document


@dataclass(frozen=True)
class IngestReport:
    fetched: dict[str, int] = field(default_factory=dict)
    normalized: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    deduped: int = 0  # dedup 으로 빠진 문서 수 (전 소스 합계)
    stored: int = 0
    chunks: int = 0


class IngestSources:
    def __init__(
        self,
        sources: list[SourcePort],
        repo: DocumentRepository,
        *,
        limit: int = 200,
        chunk_max_chars: int = 1500,
    ):
        self.sources, self.repo = sources, repo
        self.limit, self.chunk_max_chars = limit, chunk_max_chars

    async def __call__(self, query: str | None = None) -> IngestReport:
        fetched: dict[str, int] = {}
        normalized: dict[str, int] = {}
        skipped: dict[str, int] = {}
        failed: dict[str, str] = {}
        docs: list[Document] = []

        for source in self.sources:
            name = source.source
            try:
                raws = await source.search(query, self.limit)
            except Exception as exc:  # 소스 격리
                failed[name] = type(exc).__name__
                continue
            fetched[name] = len(raws)
            ok = 0
            for raw in raws:
                try:
                    docs.append(source.normalize(raw))
                    ok += 1
                except ValueError:  # pydantic ValidationError 포함
                    continue
            normalized[name] = ok
            skipped[name] = len(raws) - ok

        unique = dedup(docs)
        chunks: list[Chunk] = [
            c for d in unique for c in chunk_document(d, max_chars=self.chunk_max_chars)
        ]
        if unique:
            self.repo.upsert(unique, chunks)

        return IngestReport(
            fetched=fetched,
            normalized=normalized,
            skipped=skipped,
            failed=failed,
            deduped=len(docs) - len(unique),
            stored=len(unique),
            chunks=len(chunks),
        )
