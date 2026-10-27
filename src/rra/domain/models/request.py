from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

SLOT_MAX = 2000
SHORT_MAX = 200

# 필수 입력. 비면 ProposalRequest 가 거부한다 — 진입점(CLI·UI·MCP·API)은 ValidationError 를
# 사용자 메시지로 바꾸기만 한다 (validation_message). 규칙은 여기 한 곳에만 둔다.
REQUIRED_SLOTS = ("current_state", "root_cause", "limitation", "goal")
MISSING_SLOTS_ERROR = "missing_slots"
MISSING_SLOTS_MESSAGE = "필수 슬롯이 비었습니다"


def missing_required_slots(values: Mapping[str, object]) -> list[str]:
    """비어 있거나 공백뿐인 필수 슬롯 이름 (REQUIRED_SLOTS 순서)."""
    return [k for k in REQUIRED_SLOTS if not str(values.get(k) or "").strip()]


def validation_message(
    exc: ValidationError | Iterable[Mapping[str, Any]], labels: Mapping[str, str] | None = None
) -> str:
    """ValidationError(또는 .errors() 형태의 dict 목록) → 한 줄 사용자 메시지.

    labels 로 슬롯 이름을 표시명으로 바꿀 수 있다. 필수 슬롯 누락은 어느 진입점에서든 같은
    문구("필수 슬롯이 비었습니다: a, b")로 나온다. loc 앞의 "body"(웹 프레임워크 접두)는 뗀다.
    """
    labels = labels or {}
    parts: list[str] = []
    errors = exc.errors() if hasattr(exc, "errors") else list(exc)
    for err in errors:
        if err["type"] == MISSING_SLOTS_ERROR:
            fields = [labels.get(f, f) for f in err.get("ctx", {}).get("fields", [])]
            parts.append(f"{MISSING_SLOTS_MESSAGE}: {', '.join(fields)}")
            continue
        loc_parts = [str(p) for p in err.get("loc", ())]
        if loc_parts and loc_parts[0] == "body":
            loc_parts = loc_parts[1:]
        loc = ".".join(labels.get(p, p) for p in loc_parts)
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


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
    differentiation: str = Field(
        default="",
        description="제안자가 정한 차별화 방향 (기능 2 제안에서 고르거나 직접 적은 것)",
    )
    # Q1 입력 보강 질문의 답 ("질문: 답" 줄). 제안자 입력 근거로 취급 — 설계도·작성 프롬프트에
    supplement: str = Field(default="", description="보충 정보 (보강 질문의 답)")
    department: str = Field(default="", description="제안부서 (양식 칸에만 쓴다)")
    budget: Budget | None = None

    @model_validator(mode="before")
    @classmethod
    def _require_slots(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            missing = missing_required_slots(data)
            if missing:
                raise PydanticCustomError(
                    MISSING_SLOTS_ERROR,
                    MISSING_SLOTS_MESSAGE + ": {slots}",
                    {"slots": ", ".join(missing), "fields": missing},
                )
        return data

    @field_validator(
        "current_state",
        "root_cause",
        "limitation",
        "goal",
        "constraints",
        "policy_basis",
        "beneficiaries",
        "remarks",
        "differentiation",
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
