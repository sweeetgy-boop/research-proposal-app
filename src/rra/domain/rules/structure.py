"""U2 간편 입력의 순수 규칙 — LLM 출력 해석, 근거 검사, 보완 질문, 답 합치기.

- parse_structure: JSON 객체의 4칸만 받는다(문자열, 길이 상한, 정리). 원문(자유 문장+가제)에 없는
  수치·고유명이 든 칸은 비운다 — 모델이 지어낸 내용이 칸에 들어가지 않게.
- followup_questions: 빈 칸마다 질문 1개, 너무 짧은 칸(MIN_CHARS 미만)도 질문. 최대 4개.
- merge_answers: 답이 있는 칸은 답으로 채우고(빈 칸) 또는 뒤에 덧붙인다(이미 있는 칸).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rra.domain.models.request import REQUIRED_SLOTS, SLOT_MAX
from rra.domain.models.structure import FIELD_LABELS, FollowUp, StructuredIdea
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted

MIN_CHARS = 5  # 이보다 짧은 칸("짧음" 같은 한 어절)은 다시 묻는다
MAX_QUESTIONS = 4
QUESTIONS: dict[str, str] = {
    "current_state": "지금 현장에서 어떤 문제가 어떻게 나타나고 있습니까? (대상·빈도·영향)",
    "root_cause": "그 문제가 생기는 원인은 무엇이라고 보십니까?",
    "limitation": "지금 하고 있는 대응(점검·규정·장비)의 한계는 무엇입니까?",
    "goal": "이 연구로 무엇을 어느 수준까지 해결하려 합니까?",
}
SHORT_HINT = " (조금 더 구체적으로)"


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value))[:SLOT_MAX]


def parse_structure(data: Mapping[str, Any] | None, source_texts: list[str]) -> dict[str, str]:
    """LLM JSON → 4칸. 원문에 없는 수치·고유명이 든 칸은 비운다 (칸은 비어 있어도 된다)."""
    out = {k: "" for k in REQUIRED_SLOTS}
    if not isinstance(data, Mapping):
        return out
    for key in REQUIRED_SLOTS:
        text = _text(data.get(key))
        if not text:
            continue
        if unsupported_numbers(text, source_texts) or ungrounded(text, source_texts):
            continue  # 원문 밖 내용 → 빈 칸 (보완 질문으로 받는다)
        out[key] = text
    return out


def followup_questions(fields: Mapping[str, str]) -> list[FollowUp]:
    out: list[FollowUp] = []
    for key in REQUIRED_SLOTS:
        value = (fields.get(key) or "").strip()
        if not value:
            out.append(FollowUp(field=key, question=QUESTIONS[key], reason="empty"))
        elif len(value) < MIN_CHARS:
            out.append(FollowUp(field=key, question=QUESTIONS[key] + SHORT_HINT, reason="short"))
    return out[:MAX_QUESTIONS]


def merge_answers(fields: Mapping[str, str], answers: Mapping[str, str]) -> dict[str, str]:
    """답을 4칸에 합친다 — 빈 칸은 답으로 채우고, 이미 있는 칸은 뒤에 한 칸 띄워 덧붙인다."""
    out = {k: (fields.get(k) or "").strip() for k in REQUIRED_SLOTS}
    for key in REQUIRED_SLOTS:
        answer = clean_sentence(str(answers.get(key) or ""))
        if not answer:
            continue
        out[key] = (f"{out[key]} {answer}" if out[key] else answer)[:SLOT_MAX]
    return out


def structured(fields: Mapping[str, str], **meta: Any) -> StructuredIdea:
    clean = {k: (fields.get(k) or "").strip()[:SLOT_MAX] for k in REQUIRED_SLOTS}
    return StructuredIdea(fields=clean, questions=followup_questions(clean), **meta)


def labels() -> dict[str, str]:
    return dict(FIELD_LABELS)
