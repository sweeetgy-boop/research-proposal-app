from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

SLOT_MAX = 2000
SHORT_MAX = 200

# 필수 입력. 비면 생성하지 않는다 (진입점이 검사).
REQUIRED_SLOTS = ("current_state", "root_cause", "limitation", "goal")
# LLM 에 보내지 않는 입력 — 양식 칸에 그대로 옮기는 값.
FORM_ONLY_FIELDS = frozenset({"budget", "department"})


class Budget(BaseModel):
    """1-나 소요예산(추정액). 사용자 입력 전용 — LLM 이 만들지 않고 프롬프트에도 넣지 않는다."""

    account: str = Field(default="", max_length=SHORT_MAX, description="예산과목")
    amount_thousand_krw: int | None = Field(default=None, ge=0, description="금액(천원)")

    @field_validator("account")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ProposalRequest(BaseModel):
    """제안자 입력. G: 길이 상한은 도메인에서 강제.

    개인정보(제안자·부서장 성명·직급·연락처)는 여기 두지 않는다 — run 폴더(request.json)에
    저장되기 때문이다. 그 값은 렌더 시점에만 ProposerInfo 로 받는다 (models/proposer.py).
    """

    current_state: str = Field(description="현재 상황·문제")
    root_cause: str = Field(description="발생 원인")
    limitation: str = Field(description="현행 대응의 한계")
    goal: str = Field(description="해결 목표")
    constraints: str = Field(default="", description="예산·기간·현장 제약")
    title_hint: str = Field(default="", description="가제 (있으면 과제명을 이것으로 다듬는다)")
    policy_basis: str = Field(
        default="", description="정책적 중요도의 유일한 근거 — 제안자가 아는 정책·계획명과 요지"
    )
    beneficiaries: str = Field(default="", description="활용 주체 부서 (차량처·시설처 등)")
    remarks: str = Field(default="", description="특이사항에 덧붙일 내용")
    department: str = Field(default="", description="제안부서 (양식 칸에만 쓴다)")
    budget: Budget | None = None

    @field_validator(
        "current_state",
        "root_cause",
        "limitation",
        "goal",
        "constraints",
        "policy_basis",
        "beneficiaries",
        "remarks",
    )
    @classmethod
    def _limit(cls, v: str) -> str:
        v = v.strip()
        if len(v) > SLOT_MAX:
            raise ValueError(f"슬롯 길이 {len(v)} > {SLOT_MAX}")
        return v

    @field_validator("title_hint", "department")
    @classmethod
    def _limit_short(cls, v: str) -> str:
        v = v.strip()
        if len(v) > SHORT_MAX:
            raise ValueError(f"길이 {len(v)} > {SHORT_MAX}")
        return v

    def search_text(self) -> str:
        parts = [self.title_hint, self.current_state, self.root_cause, self.limitation, self.goal]
        return " ".join(p for p in parts if p)

    def prompt_view(self) -> dict[str, Any]:
        """LLM 에 보내는 입력. 양식 전용 값(예산·부서)과 빈 칸은 뺀다."""
        return {
            k: v
            for k, v in self.model_dump(exclude=set(FORM_ONLY_FIELDS)).items()
            if v not in ("", None)
        }
