"""요청 DTO (레인 D — 단계 이동·입력 변경 다시 쓰기·근거 일괄 승인). schemas.py 와 같은 규칙."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import ProposalRequest


class RequestChangeIn(BaseModel):
    """POST /v1/runs/{id}/request/preview — 바뀐 입력(①)과 ② 우선 근거. 저장하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    request: ProposalRequest
    # None 이면 우선 근거는 비교하지 않는다 (① 화면에서 저장할 때)
    priority_evidence: list[str] | None = Field(default=None, max_length=50)


class RegenerateIn(RequestChangeIn):
    """POST /v1/runs/{id}/regenerate — sections: 바뀐 내용과 관련된 섹션만, all: 초안 전체.
    둘 다 새 버전을 만들고 이전 버전은 남는다. base_version 이 현재와 다르면 409."""

    mode: Literal["sections", "all"] = "sections"
    base_version: int | None = Field(default=None, ge=1)


class BulkApproveIn(BaseModel):
    """POST /v1/runs/{id}/evidence-decisions/bulk-approve — 확인 필요 문장을 뺀 근거 일괄 승인."""

    model_config = ConfigDict(extra="forbid")

    base_version: int | None = Field(default=None, ge=1)
