"""Q2 섹션 설계도 검증 — LLM 출력(비신뢰)을 Outline 으로. 근거 id 는 검색 결과 안, 키는 양식 안."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rra.domain.models.outline import MAX_MESSAGE_CHARS, Outline, SectionPlan
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

DISCARD_UNKNOWN_SECTION = "unknown_section"
DISCARD_EVIDENCE = "evidence_out_of_range"
DISCARD_EMPTY = "empty_message"
DISCARD_FOREIGN = "foreign_script"


def _text(value: Any, limit: int = MAX_MESSAGE_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value))[:limit]


def validate_outline(
    data: Mapping[str, Any],
    *,
    section_keys: Iterable[str],
    allowed_ids: Iterable[str],
) -> tuple[Outline, list[str]]:
    """{"sections": {key: {message, evidence, links}} 또는 [{key, …}]} → (Outline, 치명 오류 목록).

    근거 id 가 검색 결과 밖이면 그 섹션 계획을 폐기(사유 기록)하되 설계도 전체는 남긴다. 양식 섹션이
    하나도 남지 않으면 오류(교정 재요청 대상).
    """
    keys = list(section_keys)
    allowed = set(allowed_ids)
    raw = data.get("sections")
    items: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(raw, Mapping):
        items = [(str(k), v) for k, v in raw.items() if isinstance(v, Mapping)]
    elif isinstance(raw, list):
        items = [(str(v.get("key", "")), v) for v in raw if isinstance(v, Mapping)]
    plans: list[SectionPlan] = []
    discarded: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, item in items:
        if key not in keys:
            discarded.append({"key": key[:40], "reason": DISCARD_UNKNOWN_SECTION})
            continue
        if key in seen:
            continue
        message = _text(item.get("message"))
        if not message:
            discarded.append({"key": key, "reason": DISCARD_EMPTY})
            continue
        if has_foreign_script(message):
            discarded.append({"key": key, "reason": DISCARD_FOREIGN})
            continue
        ev_raw = item.get("evidence")
        if isinstance(ev_raw, str):
            ev_raw = [ev_raw]
        evidence = [normalize_evidence_id(str(e)) for e in (ev_raw or []) if isinstance(e, str)]
        evidence = list(dict.fromkeys(e for e in evidence if e))
        if any(e not in allowed and e.split("#", 1)[0] not in allowed for e in evidence):
            discarded.append({"key": key, "reason": DISCARD_EVIDENCE})
            continue
        links_raw = item.get("links")
        if isinstance(links_raw, str):
            links_raw = [links_raw]
        links = [str(x) for x in (links_raw or []) if isinstance(x, str) and str(x) in keys]
        seen.add(key)
        plans.append(SectionPlan(key=key, message=message, evidence=evidence, links=links))
    ordered = sorted(plans, key=lambda p: keys.index(p.key))
    errors: list[str] = []
    if not ordered:
        errors.append("섹션 계획이 하나도 남지 않았습니다")
    return Outline(sections=ordered, discarded=discarded), errors
