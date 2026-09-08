from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal["openalex", "scienceon", "kipris_kr", "kipris_intl", "ntis", "alio"]
DocType = Literal["paper", "patent", "internal_report", "rnd_project"]


class Document(BaseModel):
    """수집 문서. A: body/abstract 는 항상 비신뢰 데이터."""

    doc_id: str  # f"{source}:{native_id}"
    source: SourceType
    doc_type: DocType
    title: str
    abstract: str | None = None
    body: str | None = None
    pub_date: date | None = None
    orgs: list[str] = Field(default_factory=list)  # korail / krri / kr / 외부
    authors: list[str] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list)  # IPC/CPC 등
    lang: str = "ko"
    url: str | None = None
    doi: str | None = None
    application_no: str | None = None  # 특허 출원번호
    department: str | None = None  # 철도연구원 등
    project_period: tuple[date, date] | None = None
    toc: list[str] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    trust: Literal["untrusted"] = "untrusted"


class Chunk(BaseModel):
    chunk_id: str  # f"{doc_id}#{n}"
    doc_id: str
    ordinal: int
    heading: str | None = None
    text: str
    trust: Literal["untrusted"] = "untrusted"
