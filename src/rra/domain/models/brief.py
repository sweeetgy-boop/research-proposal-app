"""U5 선행연구 브리핑 — 검색 상위 논문·보고서의 한 줄 요약·연도별 건수·키워드·연구 공백 후보."""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_ITEMS = 10
MAX_SUMMARY_CHARS = 300
MAX_GAP_CHARS = 300
GAP_LABEL = "연구 공백 후보 (근거 안에서 찾은 것이며 확정이 아님)"


class BriefItem(BaseModel):
    doc_id: str
    chunk_id: str
    title: str = ""  # 비신뢰
    source: str
    doc_type: str | None = None
    year: int | None = None
    basis: str | None = None
    summary: str = Field(default="", max_length=MAX_SUMMARY_CHARS)  # LLM 한 줄 (검증 통과분)
    summary_missing: bool = False  # 모델이 요약을 내지 않았거나 검증에서 폐기


class GapCandidate(BaseModel):
    text: str = Field(max_length=MAX_GAP_CHARS)
    evidence: list[str] = Field(default_factory=list)  # 브리핑 항목의 chunk_id/doc_id 안에서만


class PriorWorkBrief(BaseModel):
    items: list[BriefItem] = Field(default_factory=list)
    years: dict[str, int] = Field(default_factory=dict)  # "2023" → 건수, "미상" 포함
    keywords: list[str] = Field(default_factory=list)
    gaps: list[GapCandidate] = Field(default_factory=list)
    gap_label: str = GAP_LABEL
    discarded: list[dict[str, str]] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    fallback_local: bool = False
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    excluded_doc_ids: list[str] = Field(default_factory=list)
    calls: int = 0
    skipped_reason: str | None = None  # no_evidence | parse_failed

    def transfer(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "fallback_local": self.fallback_local,
            "public_doc_ids": list(self.public_doc_ids),
            "internal_doc_ids": list(self.internal_doc_ids),
            "excluded_doc_ids": list(self.excluded_doc_ids),
            "calls": self.calls,
            "items": len(self.items),
            "gaps": len(self.gaps),
            "skipped_reason": self.skipped_reason,
        }
