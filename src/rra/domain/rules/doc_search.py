"""통합 검색·자료 검색의 문서 단위 결과 규칙 (2026-10-29 [UI] 레인 3). 순수 함수.

검색은 청크 단위로 돌아오지만 화면은 문서 하나를 한 줄로 보인다: 같은 문서의 청크는 처음(가장 관련
높은) 것만 남기고, 연도 거르기는 문서 발행 연도로 한다(연도를 모르는 문서는 거르기를 켜면 빠진다).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

#: 문서 번호 모양 (자료원:번호) — 근거 패널 [원본 보기] 가 번호로 자료 검색을 연다
_DOC_ID = re.compile(r"^[a-z_]+:[A-Za-z0-9_\-.:/#]+$")
EXCERPT_CHARS = 300


def first_per_doc[T](hits: Iterable[T], doc_id_of: Callable[[T], str]) -> list[T]:
    """같은 문서의 청크는 처음 것만 (순서 유지)."""
    seen: set[str] = set()
    out: list[T] = []
    for h in hits:
        d = doc_id_of(h)
        if d in seen:
            continue
        seen.add(d)
        out.append(h)
    return out


def year_in_range(year: int | None, year_from: int | None, year_to: int | None) -> bool:
    """거르기가 없으면 통과. 있으면 연도를 아는 문서만 범위 안에서 통과."""
    if year_from is None and year_to is None:
        return True
    if year is None:
        return False
    if year_from is not None and year < year_from:
        return False
    return not (year_to is not None and year > year_to)


def excerpt(text: str | None, limit: int = EXCERPT_CHARS) -> str:
    """요약 칸에 넣을 발췌 — 공백을 한 칸으로, 상한을 넘으면 말줄임."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def looks_like_doc_id(query: str) -> bool:
    """질의가 문서 번호 하나인가 (공백 없는 자료원:번호)."""
    return bool(_DOC_ID.match(query.strip()))
