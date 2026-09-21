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
    blocking: bool  # 임계치 초과 → 제안 진행 전 확인 필요
    basis: TextBasis | None = None  # summary 면 공개 요약만으로 판정한 것


class GapRow(BaseModel):
    approach: str
    doc_ids: list[str]
    limitation: str
    our_difference: str


class GapTable(BaseModel):
    rows: list[GapRow] = Field(default_factory=list)
    alerts: list[OverlapAlert] = Field(default_factory=list)
