"""② 관련 연구(참고 논문)의 검색 관련도 — 높음·중간·낮음 (순수 규칙).

비교표의 참고 논문 열(`kind="reference"`, ADR 0053)에 제안자가 ② 관련 연구에서 본 검색 점수를
말로 붙인다. 점수는 관련 연구 검색의 e5 코사인(`overlap_candidates.related_research`)이다. 한국어
문서끼리는 무관해도 0.86~0.88 이라 숫자는 화면에 보이지 않는다(ADR 0039). 임계치는 설정
(`config/overlap.yaml candidates.research.relevance`)에 두고, 값은 측정
(docs/eval-2026-11-04-reference-relevance.md)으로 정했다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RelevanceLevel = Literal["high", "mid", "low"]
HIGH: RelevanceLevel = "high"
MID: RelevanceLevel = "mid"
LOW: RelevanceLevel = "low"
# 2026-11-04 측정(아이디어 12건, 상위 5건 60행): 높음 17건 무관 0, 낮음에 무관 10건 중 9건
DEFAULT_HIGH = 0.895
DEFAULT_MID = 0.885


class ResearchRelevanceRule(BaseModel):
    """관련 연구 점수 → 높음(≥ high)·중간(≥ mid)·낮음. 점수가 없으면 None."""

    model_config = ConfigDict(frozen=True)

    high: float = Field(default=DEFAULT_HIGH, ge=0.0, le=1.0)
    mid: float = Field(default=DEFAULT_MID, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> ResearchRelevanceRule:
        if self.mid > self.high:
            raise ValueError("관련도 임계치는 mid ≤ high 여야 합니다.")
        return self

    def level(self, score: float | None) -> RelevanceLevel | None:
        if score is None:
            return None
        if score >= self.high:
            return HIGH
        if score >= self.mid:
            return MID
        return LOW
