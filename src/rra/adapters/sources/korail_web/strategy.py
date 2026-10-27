"""중장기 경영목표 페이지(contents.do?key=1900) → 전략체계 초안 dict.

표 해석은 _html, 구조는 domain 규칙(strategy_draft)."""

from __future__ import annotations

from typing import Any

from rra.adapters.sources.korail_web._html import head_title, parse_html, parse_tables
from rra.domain.rules.strategy_draft import build_strategy_draft, find_strategy_table


def strategy_draft_from_html(html: str, *, url: str, snapshot: str | None) -> dict[str, Any]:
    rows = find_strategy_table(parse_tables(html))
    if rows is None:
        raise ValueError("경영목표·전략과제 표를 찾지 못했습니다.")
    _path, title = head_title(parse_html(html))
    return build_strategy_draft(
        rows, document=title or "중장기 경영목표", url=url, snapshot=snapshot
    )
