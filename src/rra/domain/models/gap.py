from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .document import TextBasis

Tier = Literal["own", "national_rnd", "domestic_rail", "external", "procurement"]
# 사내(철도연구원·공사 과제 기록) / 국가R&D 과제(NTIS 과제검색, 수행기관 무관) / 공단 등 / KRRI·외부 /
# 발주 용역 공고(P2-6, doc_type procurement)
# own 티어의 세부 구분 — institute: 철도연구원 부서, company: 그 외 공사 부서(사내 과제 기록 출처)
OwnDetail = Literal["institute", "company"]


class OverlapAlert(BaseModel):
    doc_id: str
    title: str
    tier: Tier
    similarity: float
    blocking: bool  # 임계치 초과(+ 키워드 조건) → 제안 진행 전 확인 필요
    basis: TextBasis | None = None  # summary 면 공개 요약만으로 판정한 것
    keywords: list[str] = Field(default_factory=list)  # 질의와 문서가 공유한 키워드 (일반어 제외)
    # 사내 과제 기록의 상태 (completed·ongoing·stopped·rejected·proposed), 발주 용역 공고는
    # procuring
    # ("용역으로 진행 중/예정"). 수집 문서 raw.status 에서
    status: str | None = None
    own_detail: OwnDetail | None = (
        None  # tier=own 일 때: 철도연구원 부서(institute) / 그 외 공사 부서(company)
    )


MAX_DIRECTIONS = 3
MAX_ITEM_CHARS = 600


class DifferentiationItem(BaseModel):
    """겹친 과제 하나에 대한 활용·차별화 제안 (LLM 출력을 검증한 뒤의 값)."""

    doc_id: str
    title: str  # 비신뢰 텍스트 (수집 문서 제목)
    tier: Tier
    status: str | None = None  # 사내 기록의 상태. rejected 면 "보완 재제안" 관점
    overlap_summary: str = Field(max_length=MAX_ITEM_CHARS)  # 무엇이 겹치는지
    build_on: str = Field(max_length=MAX_ITEM_CHARS)  # 그 과제 결과를 이어받을 점
    differentiation: list[str] = Field(min_length=1, max_length=MAX_DIRECTIONS)  # 차별화 방향
    evidence: list[str] = Field(default_factory=list)  # 겹친 과제 doc_id


class DifferentiationProposal(BaseModel):
    """유사과제 활용·차별화 제안 결과 + 외부 전송 범위 (manifest 용. 본문은 run 에 안 남긴다)."""

    items: list[DifferentiationItem] = Field(default_factory=list)
    discarded: list[dict[str, str]] = Field(default_factory=list)  # {doc_id, reason}
    provider: str | None = None
    model: str | None = None
    fallback_local: bool = False  # differentiate 단계 키가 없어 로컬(compose) 모델로 돌림
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    excluded_doc_ids: list[str] = Field(default_factory=list)  # include_internal=false 로 뺀 것
    calls: int = 0
    skipped_reason: str | None = None  # no_candidates | no_documents | parse_failed

    def transfer(self) -> dict[str, object]:
        """manifest 에 남기는 전송 기록 (검토 단계의 ReviewTransfer 와 같은 범위)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "fallback_local": self.fallback_local,
            "public_doc_ids": list(self.public_doc_ids),
            "internal_doc_ids": list(self.internal_doc_ids),
            "excluded_doc_ids": list(self.excluded_doc_ids),
            "calls": self.calls,
            "items": len(self.items),
            "discarded": len(self.discarded),
            "skipped_reason": self.skipped_reason,
        }


class GapRow(BaseModel):
    approach: str
    doc_ids: list[str]
    limitation: str
    our_difference: str


class GapTable(BaseModel):
    rows: list[GapRow] = Field(default_factory=list)
    alerts: list[OverlapAlert] = Field(default_factory=list)
