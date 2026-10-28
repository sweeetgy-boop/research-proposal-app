"""작성·편집 AI 경로의 요청 DTO (2026-10-28 레인 B). 길이 상한은 도메인 모델이 강제한다."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import PolicyChoice, ProposalRequest

_EXTRA = {"exclude_doc_ids", "choice", "text"}


class PolicyCardsIn(ProposalRequest):
    """POST /v1/ideas/policy-cards — 입력 + [다른 안 보기] 때 이미 본 문서 id."""

    exclude_doc_ids: list[str] = Field(default_factory=list, max_length=40)

    def request(self) -> ProposalRequest:
        return ProposalRequest(**self.model_dump(exclude=_EXTRA))


class PolicyPolishIn(ProposalRequest):
    """POST /v1/ideas/policy-cards/polish — 입력 + 고른 안 + 제안자가 고친 글."""

    choice: PolicyChoice
    text: str = Field(min_length=1, max_length=2000)

    def request(self) -> ProposalRequest:
        return ProposalRequest(**self.model_dump(exclude=_EXTRA))


class RunPolicyCardsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exclude_doc_ids: list[str] = Field(default_factory=list, max_length=40)


class RunPolicyPolishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: PolicyChoice
    text: str = Field(min_length=1, max_length=2000)


class PolicyChoiceIn(BaseModel):
    """POST /v1/runs/{id}/policy-choice — 고른 안 또는 {mode: none}."""

    model_config = ConfigDict(extra="forbid")

    choice: PolicyChoice
    base_version: int | None = Field(default=None, ge=1, le=10_000)
