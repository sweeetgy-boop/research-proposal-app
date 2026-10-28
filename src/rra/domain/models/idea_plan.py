"""② 차별화 과제안 — 원래 아이디어 / 고른 카드 / 직접 고친 안을 버전으로 남긴다 (2026-10-28 레인 A).

run 에는 idea_versions.json 으로 복사된다. 칸은 과제안 다섯 칸만(가제·연구목표·연구방법·적용범위·
차별화 방향) — 사람 이름·연락처는 받지 않고, 저장 전 개인정보 표식으로 바꾼다
(domain/rules/idea_plan.normalize_versions).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 과제안 칸 → ProposalRequest 필드. 화면 이름은 IDEA_FIELD_LABELS.
IDEA_FIELDS: tuple[str, ...] = ("title_hint", "goal", "method", "scope", "differentiation")
IDEA_FIELD_LABELS: dict[str, str] = {
    "title_hint": "과제명(가제)",
    "goal": "연구목표",
    "method": "연구방법",
    "scope": "적용범위",
    "differentiation": "기존 과제 대비 차이",
}
IdeaVersionKind = Literal["original", "card", "edited"]
IDEA_KIND_LABELS: dict[str, str] = {
    "original": "원래 아이디어",
    "card": "고른 과제안",
    "edited": "직접 고친 안",
}
MAX_IDEA_VERSIONS = 10
IDEA_FIELD_MAX = 2000


class IdeaVersion(BaseModel):
    kind: IdeaVersionKind
    fields: dict[str, str] = Field(default_factory=dict)  # IDEA_FIELDS 만 (규칙이 거른다)
    card_index: int | None = Field(default=None, ge=0, le=9)  # kind=card 일 때 고른 카드 번호
    note: str = Field(default="", max_length=100)
    at: str = Field(default="", max_length=40)  # ISO 시각 (화면이 보낸 값, 표시용)
