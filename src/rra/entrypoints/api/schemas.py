"""요청 DTO. 본문 길이·필수 슬롯은 도메인 모델(ProposalRequest·EditRequest)이 강제한다."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import ProposalRequest  # noqa: F401 — 요청 본문 모델로 그대로 쓴다
from rra.domain.models.review import EditRequest  # noqa: F401 — POST /runs/{id}/edits 본문

_SHORT = 100


class SessionIn(BaseModel):
    """POST /v1/session — 관리 토큰으로 세션 쿠키를 받는다. 토큰은 본문으로만 (URL·로그 금지)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)
    orgs: list[str] | None = Field(default=None, max_length=10)


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
    department: str = Field(default="", max_length=_SHORT)
    proposer: PersonIn = Field(default_factory=PersonIn)
    head: PersonIn = Field(default_factory=PersonIn)


class FinalizeIn(ConfirmIn):
    """POST /v1/runs/{id}/finalize — 선택형(넘긴 것만 덮어씀, 나머지 제안값) + 제안자 정보."""

    proposed_on: str = Field(default="", max_length=20)
    department: str = Field(default="", max_length=_SHORT)
    proposer: PersonIn = Field(default_factory=PersonIn)
    head: PersonIn = Field(default_factory=PersonIn)


class RevertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: int = Field(ge=1, le=10_000)


class DifferentiationTransferIn(BaseModel):
    """POST /v1/precheck/differentiate 응답의 transfer 를 되돌려 보내면 run manifest 에 남는다.
    doc_id 와 개수만 — 본문은 받지 않는다 (보안 I)."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)
    fallback_local: bool = False
    public_doc_ids: list[str] = Field(default_factory=list, max_length=50)
    internal_doc_ids: list[str] = Field(default_factory=list, max_length=50)
    excluded_doc_ids: list[str] = Field(default_factory=list, max_length=50)
    calls: int = Field(default=0, ge=0, le=100)
    items: int = Field(default=0, ge=0, le=100)
    discarded: int = Field(default=0, ge=0, le=100)
    skipped_reason: str | None = Field(default=None, max_length=40)


class RecommendationApplyIn(BaseModel):
    """POST /v1/precheck/recommendations/{id}/apply — 고른 추천 번호. 미리보기만 돌려준다."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, le=4)


class RunIn(ProposalRequest):
    """생성 요청 = ProposalRequest + (선택) 차별화 제안 전송 기록 + (선택) 과제 추천 세션 id·번호.

    recommendation_id 가 있으면 서버가 그 세션의 추천 결과 전체를 run 의 recommendations.json 에
    복사하고 manifest 에 전송 기록·chosen 을 남긴다. 모르는 id 는 404.
    """

    differentiation_transfer: DifferentiationTransferIn | None = None
    recommendation_id: str | None = Field(default=None, min_length=8, max_length=64)
    recommendation_index: int | None = Field(default=None, ge=0, le=4)

    def request(self) -> ProposalRequest:
        return ProposalRequest(
            **self.model_dump(
                exclude={"differentiation_transfer", "recommendation_id", "recommendation_index"}
            )
        )

    def transfer_record(self) -> dict | None:
        if self.differentiation_transfer is None:
            return None
        return {
            **self.differentiation_transfer.model_dump(),
            "chosen": bool(self.differentiation.strip()),
        }
