from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

SLOT_MAX = 2000


class ProposalRequest(BaseModel):
    """제안자 입력 5슬롯. G: 길이 상한은 도메인에서 강제."""

    current_state: str = Field(description="현재 상황·문제")
    root_cause: str = Field(description="발생 원인")
    limitation: str = Field(description="현행 대응의 한계")
    goal: str = Field(description="해결 목표")
    constraints: str = Field(default="", description="예산·기간·현장 제약")
    proposer: str | None = None

    @field_validator("current_state", "root_cause", "limitation", "goal", "constraints")
    @classmethod
    def _limit(cls, v: str) -> str:
        v = v.strip()
        if len(v) > SLOT_MAX:
            raise ValueError(f"슬롯 길이 {len(v)} > {SLOT_MAX}")
        return v

    def search_text(self) -> str:
        return " ".join([self.current_state, self.root_cause, self.limitation, self.goal])
