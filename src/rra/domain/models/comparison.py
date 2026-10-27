"""U4 차별성 비교표 — precheck 상위 유사과제 × 비교 항목. 화면·API 표만 (양식 밖)."""

from __future__ import annotations

from pydantic import BaseModel, Field

ASPECTS: tuple[tuple[str, str], ...] = (
    ("objective", "연구목표"),
    ("method", "연구방법"),
    ("scope", "적용범위"),
    ("outcome", "기대성과"),
    ("differentiation", "차별화 방향"),
)
NO_INFO_TITLE_ONLY = "정보 없음(제목 기준)"
NO_INFO = "정보 없음"
MAX_CELL_CHARS = 400


class ComparisonColumn(BaseModel):
    """표의 열 하나 — 제안(proposal) 또는 유사과제."""

    doc_id: str | None = None  # None 이면 제안 자체
    title: str = ""  # 비신뢰 (수집 문서 제목) / 제안은 가제
    tier: str | None = None
    similarity: float | None = None
    blocking: bool = False
    basis: str | None = None
    title_only: bool = False  # 요약·초록이 없어 제목만으로 채움
    cells: dict[str, str] = Field(default_factory=dict)  # aspect → 글 (MAX_CELL_CHARS)


class ComparisonTable(BaseModel):
    aspects: list[dict[str, str]] = Field(
        default_factory=lambda: [{"key": k, "label": v} for k, v in ASPECTS]
    )
    proposal: ComparisonColumn
    projects: list[ComparisonColumn] = Field(default_factory=list)
