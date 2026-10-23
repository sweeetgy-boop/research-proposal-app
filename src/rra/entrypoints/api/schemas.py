"""요청 DTO. 본문 길이·필수 슬롯은 도메인 모델(ProposalRequest)이 강제하므로 재정의하지 않는다."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import ProposalRequest  # noqa: F401 — 요청 본문 모델로 그대로 쓴다

_SHORT = 100


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str | None = Field(default=None, max_length=32)
    utilization: list[str] | None = Field(default=None, max_length=20)
    strategy: list[str] | None = Field(default=None, max_length=5)

    def choices(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if self.task_type:
            out["task_type"] = [self.task_type]
        if self.utilization:
            out["utilization"] = list(self.utilization)
        if self.strategy:
            out["strategy_alignment"] = list(self.strategy)
        return out


class PersonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: str = Field(default="", max_length=_SHORT)
    name: str = Field(default="", max_length=_SHORT)
    phone: str = Field(default="", max_length=_SHORT)


class ProposerIn(BaseModel):
    """양식 하단 정보 — 응답 파일에만 들어가고 서버 어디에도 저장되지 않는다 (요청 본문으로만)."""

    model_config = ConfigDict(extra="forbid")

    proposed_on: str = Field(default="", max_length=20)
    proposer: PersonIn = Field(default_factory=PersonIn)
    head: PersonIn = Field(default_factory=PersonIn)
