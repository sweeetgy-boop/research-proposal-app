"""샌드박스 자식이 돌려준 결과를 본체에서 다시 검증하는 스키마 (자식 출력도 비신뢰)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_TEXT_CHARS = 5_000_000


class ExtractResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(max_length=MAX_TEXT_CHARS)
    toc: list[str] = Field(default_factory=list, max_length=500)
    pages: int | None = Field(default=None, ge=0)
    meta_title: str | None = Field(default=None, max_length=200)
    truncated: bool = False


class CatalogRows(BaseModel):
    model_config = ConfigDict(extra="ignore")

    header: list[str] = Field(max_length=200)
    rows: list[dict[str, str]]
