"""목차 기반 청킹. 목차 없으면 문자 수 기준."""

from __future__ import annotations

from rra.domain.models import Chunk, Document


def chunk_document(doc: Document, max_chars: int = 1500) -> list[Chunk]:
    text = doc.body or doc.abstract or ""
    if not text:
        return []
    pieces: list[tuple[str | None, str]] = []
    if doc.toc:
        cursor = 0
        for i, heading in enumerate(doc.toc):
            idx = text.find(heading, cursor)
            if idx < 0:
                continue
            nxt = text.find(doc.toc[i + 1], idx + 1) if i + 1 < len(doc.toc) else len(text)
            nxt = nxt if nxt > 0 else len(text)
            pieces.append((heading, text[idx:nxt]))
            cursor = nxt
    if not pieces:
        pieces = [(None, text)]
    out: list[Chunk] = []
    n = 0
    for heading, seg in pieces:
        for i in range(0, len(seg), max_chars):
            out.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{n}",
                    doc_id=doc.doc_id,
                    ordinal=n,
                    heading=heading,
                    text=seg[i : i + max_chars],
                )
            )
            n += 1
    return out
