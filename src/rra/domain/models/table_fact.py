"""표 사실(P2-8). 수집 문서의 표 한 칸 = 사실 한 건. 전부 비신뢰 데이터 — 파싱·판독 결과에서 온다.

TableFact   (항목, 연도, 단위, 값) + 출처(doc_id·쪽·시트·행/열 머리글·근거 종류).
ParsedTable 어댑터가 넘기는 표 한 장(문자열 격자). 규칙(`domain/rules/table_facts.py`)이 사실로
바꾼다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# text=문서 본문·시트에서 파싱, image_vision=이미지 판독(P3) structure 에서
FactBasis = Literal["text", "image_vision"]
MAX_LABEL_CHARS = 120
MAX_ITEM_CHARS = 200
MAX_UNIT_CHARS = 20


class TableFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: str = Field(min_length=1, max_length=MAX_ITEM_CHARS)
    value: Decimal
    value_text: str = Field(min_length=1, max_length=40)  # 표에 적힌 그대로 ("1,512")
    doc_id: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)
    unit: str | None = Field(default=None, max_length=MAX_UNIT_CHARS)
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, max_length=MAX_LABEL_CHARS)
    row_label: str | None = Field(default=None, max_length=MAX_LABEL_CHARS)
    col_label: str | None = Field(default=None, max_length=MAX_LABEL_CHARS)
    basis: FactBasis = "text"
    trust: Literal["untrusted"] = "untrusted"

    def as_text(self) -> str:
        """수치 lint(`numbers.unsupported_numbers`)가 허용 텍스트로 읽는 꼴 — "2023년 1,512대"."""
        year = f"{self.year}년 " if self.year else ""
        return f"{year}{self.value_text}{self.unit or ''}"


class ParsedTable(BaseModel):
    """어댑터 → 규칙. rows 는 문자열 격자(빈 칸 None). title·notes 는 단위 탐지에만 쓴다."""

    doc_id: str = Field(min_length=1, max_length=200)
    rows: list[list[str | None]] = Field(default_factory=list)
    # 격자가 아니라 본문 줄(PDF 텍스트·문서 body)이면 lines 에 — 규칙은 정렬된 숫자 줄만 사실로 본다
    lines: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, max_length=MAX_LABEL_CHARS)
    title: str | None = Field(default=None, max_length=300)
    notes: list[str] = Field(default_factory=list)
    unit: str | None = Field(default=None, max_length=MAX_UNIT_CHARS)  # 어댑터가 아는 기본 단위
    basis: FactBasis = "text"
