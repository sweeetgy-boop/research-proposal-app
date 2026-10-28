"""요청 DTO. 본문 길이·필수 슬롯은 도메인 모델(ProposalRequest·EditRequest)이 강제한다."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import ProposalRequest  # noqa: F401 — 요청 본문 모델로 그대로 쓴다
from rra.domain.models.review import EditRequest  # noqa: F401 — POST /runs/{id}/edits 본문

_SHORT = 100


class SessionIn(BaseModel):
    """POST /v1/session — 세션 쿠키를 받는다. kind: token(관리 토큰) | staff(사번) | guest(아이디·
    비밀번호). 값은 본문으로만 (URL·로그 금지). 옛 본문 `{token}` 은 kind=token 으로 본다."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["token", "staff", "guest"] = "token"
    token: str | None = Field(default=None, min_length=1, max_length=512)
    staff_no: str | None = Field(default=None, min_length=1, max_length=64)
    id: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=1, max_length=256)


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
    version: int | None = Field(default=None, ge=1, le=10_000)  # 마무리할 버전 (기본 최신)


class FinalizeIn(ConfirmIn):
    """POST /v1/runs/{id}/finalize — 선택형(넘긴 것만 덮어씀, 나머지 제안값) + 제안자 정보."""

    proposed_on: str = Field(default="", max_length=20)
    department: str = Field(default="", max_length=_SHORT)
    proposer: PersonIn = Field(default_factory=PersonIn)
    head: PersonIn = Field(default_factory=PersonIn)
    version: int | None = Field(default=None, ge=1, le=10_000)  # 마무리할 버전 (기본 최신)


class WorkingIn(BaseModel):
    """PUT /v1/runs/{id}/draft/working — 서버 작업 사본(섹션별 문장 목록 또는 통문). 버전 아님."""

    model_config = ConfigDict(extra="forbid")

    sections: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    note: str = Field(default="", max_length=200)
    base_version: int | None = Field(default=None, ge=1)


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


class RewriteApplyIn(BaseModel):
    """POST /v1/runs/{id}/sections/{key}/rewrite/apply — 고른 후보 문장 번호(없으면 전부)."""

    model_config = ConfigDict(extra="forbid")

    chosen: list[int] | None = Field(default=None, max_length=100)
    base_version: int | None = Field(default=None, ge=1, le=10_000)
    note: str = Field(default="", max_length=200)


class SectionAnswersIn(BaseModel):
    """POST /v1/runs/{id}/sections/{key}/answers — 보완 질문의 답 {요소: 답} (제안자 입력)."""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(default_factory=dict, max_length=20)


class FeedbackIn(BaseModel):
    """POST /v1/runs/{id}/feedback — 만족도 1~5 + 한 줄(200자, 이메일·전화 금지). 마무리 뒤에만."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=200)


class StructureIn(BaseModel):
    """POST /v1/ideas/structure — 자유 문장(1~2문장) + 가제(선택). 서버는 저장하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=200)


class StructureMergeIn(BaseModel):
    """POST /v1/ideas/structure/merge — 구조화 결과(fields) + 보완 답(answers) → 합친 4칸 미리보기.
    LLM 호출 없음."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str] = Field(default_factory=dict, max_length=8)
    answers: dict[str, str] = Field(default_factory=dict, max_length=8)


class RunIn(ProposalRequest):
    """생성 요청 = ProposalRequest + (선택) 차별화 제안 전송 기록 + (선택) 과제 추천 세션 id·번호
    + (선택) U5 우선 근거 id.

    recommendation_id 가 있으면 서버가 그 세션의 추천 결과 전체를 run 의 recommendations.json 에
    복사하고 manifest 에 전송 기록·chosen 을 남긴다. 모르는 id 는 404.
    priority_evidence 는 브리핑에서 고른 doc_id·chunk_id — 검색 집합 안의 것만
    snapshot.priority_ids 로.
    """

    differentiation_transfer: DifferentiationTransferIn | None = None
    recommendation_id: str | None = Field(default=None, min_length=8, max_length=64)
    recommendation_index: int | None = Field(default=None, ge=0, le=4)
    # 차단 경보 확인 — 서버가 precheck 를 다시 돌려 차단 알림이 있는데 False 면 409
    acknowledged: bool = False
    priority_evidence: list[str] | None = Field(default=None, max_length=50)

    def request(self) -> ProposalRequest:
        return ProposalRequest(
            **self.model_dump(
                exclude={
                    "differentiation_transfer",
                    "recommendation_id",
                    "recommendation_index",
                    "acknowledged",
                    "priority_evidence",
                }
            )
        )

    def transfer_record(self) -> dict | None:
        if self.differentiation_transfer is None:
            return None
        return {
            **self.differentiation_transfer.model_dump(),
            "chosen": bool(self.differentiation.strip()),
        }


FigureAction = Literal["words", "texts", "baseline", "regenerate", "include", "exclude", "confirm"]


class FigureActionIn(BaseModel):
    """POST /v1/runs/{id}/figures/{fid} — 그림 카드 동작 ([G]). words→request, texts→texts 필수."""

    model_config = ConfigDict(extra="forbid")
    action: FigureAction
    request: str = Field(default="", max_length=500)  # [말로 고치기] 요청 (개인정보 정리 뒤 저장)
    texts: dict[str, str] = Field(default_factory=dict)  # [글자 고치기] path → 글자
    base_version: int | None = Field(default=None, ge=1)


class FigureAddIn(BaseModel):
    """POST /v1/runs/{id}/figures — [다른 그림 추가]."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["concept", "process", "schedule", "stat_chart", "comparison", "roadmap"]
    section: str = Field(min_length=1, max_length=40)
    base_version: int | None = Field(default=None, ge=1)
