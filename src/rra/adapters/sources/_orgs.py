"""기관명 → 기관 태그(korail·krri·kr). 순수 함수. 목록은 config/sources.yaml 의 institutions.

overlap.tier_of 가 orgs 의 korail·kr 로 domestic_rail 티어를 정하므로, 수집 소스는 수행·주관기관명을
여기로 통과시켜 태그를 붙인다.
기관 개칭(한국철도시설공단 → 국가철도공단, 2020)은 aliases 로 흡수한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def _squash(name: str) -> str:
    return "".join(str(name).split())


def org_tags(names: Iterable[str], institutions: Sequence[Mapping[str, Any]]) -> list[str]:
    """이름 목록에서 대상 기관 태그를 찾는다. 기관명이 이름 안에 들어 있으면 매칭
    ("한국철도공사 철도연구원" → korail). 한국철도공사 ≠ 한국철도기술연구원처럼 서로 포함하지 않는
    이름만 목록에 둔다. 순서 유지·중복 제거."""
    tags: list[str] = []
    for raw in names:
        name = _squash(raw)
        if not name:
            continue
        for inst in institutions:
            labels = [inst.get("name", ""), *(inst.get("aliases") or [])]
            if any(_squash(label) and _squash(label) in name for label in labels):
                tag = inst["tag"]
                if tag not in tags:
                    tags.append(tag)
    return tags
