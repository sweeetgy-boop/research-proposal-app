"""계획 문서의 판(edition) 추적 (순수) — "제4차 국가철도망 구축계획(2021~2030)" 처럼 차수가 있는
제목.

같은 계획 이름(차수·연도 범위·괄호를 뺀 이름)에서 차수가 가장 큰 것이 현행, 나머지는 구판
(valid_until = 다음 판의 등록일; 등록일을 모르면 None 으로 두고 둘 다 현행으로 본다 —
모호하면 유지).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import Any

_EDITION = re.compile(r"제\s*(\d{1,2})\s*차\s*")
_RANGE = re.compile(r"\(\s*\d{4}\s*[~∼-]\s*\d{4}\s*\)|\s*\d{4}\s*[~∼-]\s*\d{4}")
_PAREN = re.compile(r"\([^)]*\)")


def plan_family(title: str) -> tuple[str, int] | None:
    """('국가철도망 구축계획', 4) 또는 None(차수 없음)."""
    m = _EDITION.search(title)
    if not m:
        return None
    name = _EDITION.sub("", title, count=1)
    name = _RANGE.sub("", name)
    name = _PAREN.sub("", name)
    name = " ".join(name.replace("(", " ").replace(")", " ").split())
    return (name, int(m.group(1))) if name else None


def mark_editions(
    items: Sequence[dict[str, Any]], *, title_key: str = "title", date_key: str = "posted"
) -> list[dict[str, Any]]:
    """각 항목에 edition={family, no, status: 현행|구판, superseded_by, valid_until} 를 붙인
    사본."""
    families: dict[str, list[tuple[int, int]]] = {}
    for i, it in enumerate(items):
        fam = plan_family(str(it.get(title_key) or ""))
        if fam:
            families.setdefault(fam[0], []).append((fam[1], i))
    out = [dict(it) for it in items]
    for name, members in families.items():
        members.sort()
        latest_no = members[-1][0]
        latest = [i for no, i in members if no == latest_no]
        newest_date = max((str(out[i].get(date_key) or "") for i in latest), default="")
        for no, i in members:
            status = "현행" if no == latest_no else "구판"
            edition: dict[str, Any] = {"family": name, "no": no, "status": status}
            if status == "구판":
                edition["superseded_by"] = latest_no
                if newest_date:
                    edition["valid_until"] = newest_date
            out[i]["edition"] = edition
    return out


def valid_until_of(item: dict[str, Any]) -> date | None:
    value = (item.get("edition") or {}).get("valid_until")
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
