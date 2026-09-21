"""Document/Chunk ↔ SQLite row 변환. 순수 함수 — DB 커넥션을 모른다."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from rra.domain.models import Chunk, Document

DOCUMENT_COLUMNS = (
    "doc_id",
    "source",
    "doc_type",
    "title",
    "abstract",
    "body",
    "pub_date",
    "lang",
    "url",
    "doi",
    "application_no",
    "department",
    "period_start",
    "period_end",
    "authors_json",
    "codes_json",
    "orgs_json",
    "toc_json",
    "text_basis",
    "raw_json",
)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def document_to_row(doc: Document) -> tuple[Any, ...]:
    start, end = doc.project_period if doc.project_period else (None, None)
    values: dict[str, Any] = {
        "doc_id": doc.doc_id,
        "source": doc.source,
        "doc_type": doc.doc_type,
        "title": doc.title,
        "abstract": doc.abstract,
        "body": doc.body,
        "pub_date": _iso(doc.pub_date),
        "lang": doc.lang,
        "url": doc.url,
        "doi": doc.doi,
        "application_no": doc.application_no,
        "department": doc.department,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "authors_json": _dumps(doc.authors),
        "codes_json": _dumps(doc.codes),
        "orgs_json": _dumps(doc.orgs),
        "toc_json": _dumps(doc.toc) if doc.toc is not None else None,
        "text_basis": doc.text_basis,
        "raw_json": _dumps(doc.raw),
    }
    return tuple(values[c] for c in DOCUMENT_COLUMNS)


def row_to_document(row: Any) -> Document:
    start = _parse_date(row["period_start"])
    end = _parse_date(row["period_end"])
    toc = json.loads(row["toc_json"]) if row["toc_json"] is not None else None
    return Document(
        doc_id=row["doc_id"],
        source=row["source"],
        doc_type=row["doc_type"],
        title=row["title"],
        abstract=row["abstract"],
        body=row["body"],
        pub_date=_parse_date(row["pub_date"]),
        orgs=json.loads(row["orgs_json"]),
        authors=json.loads(row["authors_json"]),
        codes=json.loads(row["codes_json"]),
        lang=row["lang"],
        url=row["url"],
        doi=row["doi"],
        application_no=row["application_no"],
        department=row["department"],
        project_period=(start, end) if start and end else None,
        toc=toc,
        text_basis=row["text_basis"],
        raw=json.loads(row["raw_json"]),
    )


def chunk_to_row(chunk: Chunk) -> tuple[Any, ...]:
    return (chunk.chunk_id, chunk.doc_id, chunk.ordinal, chunk.heading, chunk.text)


def row_to_chunk(row: Any) -> Chunk:
    """basis 는 documents.text_basis 를 JOIN 해 온 컬럼."""
    return Chunk(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"],
        ordinal=row["ordinal"],
        heading=row["heading"],
        text=row["text"],
        basis=row["basis"],
    )
