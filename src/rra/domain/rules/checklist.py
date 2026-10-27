"""U3 섹션 체크리스트 → 보완 질문 (순수). 체크리스트는 설정 파일(section_checklists.yaml)에서 온다.

요소마다 keywords 중 하나라도 섹션 본문에 있으면 "있음", 없으면 그 요소의 질문을 낸다.
답은 제안자 입력(proposer_notes)으로 저장되어 다음 다시 쓰기 프롬프트에 들어간다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rra.domain.models import Section

MAX_QUESTIONS = 6
MAX_ANSWER_CHARS = 1000


def _present(text: str, keywords: Sequence[str], element: str) -> bool:
    body = "".join(text.split())
    probes = [k for k in keywords if k] or [element]
    return any("".join(p.split()) in body for p in probes)


def missing_elements(section: Section | None, checklist: Sequence[Mapping[str, Any]]) -> list[dict]:
    """[{element, question}] — 본문에 없는 요소만, 체크리스트 순서."""
    text = section.text if section is not None else ""
    out: list[dict] = []
    for item in checklist:
        element = str(item.get("element", ""))
        if not element or _present(text, list(item.get("keywords") or []), element):
            continue
        out.append({"element": element, "question": str(item.get("question") or element)})
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def coverage(section: Section | None, checklist: Sequence[Mapping[str, Any]]) -> float | None:
    """있는 요소 비율 (0~1). 체크리스트가 비면 None."""
    if not checklist:
        return None
    missing = len(missing_elements(section, checklist))
    return round((len(checklist) - missing) / len(checklist), 3)


def clean_answers(raw: Mapping[str, Any] | None) -> dict[str, str]:
    """{요소: 답} — 빈 답은 버리고 길이를 자른다. 요소 이름은 체크리스트 키가 아니어도 받는다."""
    out: dict[str, str] = {}
    for k, v in (raw or {}).items():
        key = " ".join(str(k).split())[:80]
        val = " ".join(str(v or "").split())[:MAX_ANSWER_CHARS]
        if key and val:
            out[key] = val
    return out
