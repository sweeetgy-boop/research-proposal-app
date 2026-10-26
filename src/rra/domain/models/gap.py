from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .document import TextBasis

Tier = Literal["own", "domestic_rail", "external"]  # 철도연구원 / 코레일타부서·공단 / KRRI·외부


class OverlapAlert(BaseModel):
    doc_id: str
    title: str
    tier: Tier
    similarity: float
    blocking: bool  # 임계치 초과(+ 키워드 조건) → 제안 진행 전 확인 필요
    basis: TextBasis | None = None  # summary 면 공개 요약만으로 판정한 것
    keywords: list[str] = Field(default_factory=list)  # 질의와 문서가 공유한 키워드 (일반어 제외)
    # 사내 과제 기록의 상태 (completed·ongoing·stopped·rejected·proposed). 수집 문서 raw.status 에서
    status: str | None = None


class GapRow(BaseModel):
    approach: str
    doc_ids: list[str]
    limitation: str
    our_difference: str


class GapTable(BaseModel):
    rows: list[GapRow] = Field(default_factory=list)
    alerts: list[OverlapAlert] = Field(default_factory=list)
