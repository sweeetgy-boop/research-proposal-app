"""U2 간편 입력 — 자유 문장을 필수 4칸으로 나눈 결과 + 보완 질문. 서버는 저장하지 않는다."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .request import REQUIRED_SLOTS, SLOT_MAX

FIELD_LABELS: dict[str, str] = {
    "current_state": "현재 상황·문제",
    "root_cause": "발생 원인",
    "limitation": "현행 대응의 한계",
    "goal": "해결 목표",
}
MAX_QUESTION_CHARS = 200


class FollowUp(BaseModel):
    field: str
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    reason: str = "empty"  # empty | short


class StructuredIdea(BaseModel):
    fields: dict[str, str] = Field(default_factory=lambda: {k: "" for k in REQUIRED_SLOTS})
    questions: list[FollowUp] = Field(default_factory=list)
    skip_allowed: bool = True
    provider: str | None = None
    model: str | None = None
    parse_failed: bool = False

    @property
    def complete(self) -> bool:
        return all((self.fields.get(k) or "").strip() for k in REQUIRED_SLOTS)

    def as_request_fields(self) -> dict[str, str]:
        return {k: (self.fields.get(k) or "").strip()[:SLOT_MAX] for k in REQUIRED_SLOTS}
