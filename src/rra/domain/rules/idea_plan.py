"""② 차별화 과제안 — 칸 다듬기 검증·버전 정리 (순수 함수, 2026-10-28 레인 A).

- validate_polish: [AI로 다듬기] 결과 한 칸 검증. 입력(제안 입력 전체 + 고치기 전 글)에 없는 수치·
  정책명, 한자·가나, 빈 글·너무 긴 글은 쓰지 않는다 → (다듬은 글, None) 또는 (None, 사유 문구).
- normalize_versions: run 에 남길 과제안 버전 — 과제안 다섯 칸만, 길이 상한, 개인정보 표식, 최대 10개.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rra.domain.models.idea_plan import (
    IDEA_FIELD_MAX,
    IDEA_FIELDS,
    MAX_IDEA_VERSIONS,
    IdeaVersion,
)
from rra.domain.models.request import SHORT_MAX
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.privacy import strip_personal
from rra.domain.rules.trust import escape_untrusted

POLISH_EMPTY = "다듬은 글이 비어 있음"
POLISH_NUMBER = "입력에 없는 수치가 들어가 원래 글을 유지함"
POLISH_NAME = "입력에 없는 정책·계획명이 들어가 원래 글을 유지함"
POLISH_FOREIGN = "한자·가나가 섞여 원래 글을 유지함"
POLISH_TOO_LONG = "글이 너무 길어 원래 글을 유지함"


def field_limit(field: str) -> int:
    return SHORT_MAX if field == "title_hint" else IDEA_FIELD_MAX


def validate_polish(
    field: str, polished: Any, allowed_texts: Iterable[str]
) -> tuple[str | None, str | None]:
    if not isinstance(polished, str):
        return None, POLISH_EMPTY
    text = clean_sentence(escape_untrusted(polished)).strip()
    if field == "title_hint":
        text = text.rstrip(".")
    if not text:
        return None, POLISH_EMPTY
    if len(text) > field_limit(field):
        return None, POLISH_TOO_LONG
    allowed = list(allowed_texts)
    if has_foreign_script(text):
        return None, POLISH_FOREIGN
    if unsupported_numbers(text, allowed):
        return None, POLISH_NUMBER
    if ungrounded(text, allowed):
        return None, POLISH_NAME
    return text, None


def normalize_versions(versions: Iterable[IdeaVersion]) -> list[dict[str, Any]]:
    """run 의 idea_versions.json 내용 — 칸 거르기·상한·개인정보 표식."""
    out: list[dict[str, Any]] = []
    for v in list(versions)[:MAX_IDEA_VERSIONS]:
        fields: dict[str, str] = {}
        for key in IDEA_FIELDS:
            value = v.fields.get(key)
            if isinstance(value, str) and value.strip():
                fields[key] = strip_personal(value.strip()[: field_limit(key)]).text
        out.append(
            {
                "kind": v.kind,
                "fields": fields,
                "card_index": v.card_index,
                "note": strip_personal(v.note).text if v.note else "",
                "at": v.at,
            }
        )
    return out
