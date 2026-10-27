"""전략체계 초안 — 중장기 경영목표 표(경영목표·전략과제·주요내용·KPI)에서 전략방향·전략과제를
뽑는다 (순수).

문서에 없는 항목은 만들지 않는다. 항목마다 출처(문서·URL·표 위치·스냅샷)와 `basis: text` 를 붙인다
(이미지에서 읽은 항목은 다른 레인이 `basis: image_vision` 으로 보탠다).
결과는 StrategyCatalog 로 검증된다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from rra.domain.models import StrategyCatalog

HEADER_GOAL = ("경영목표", "전략목표")
HEADER_TASK = ("전략과제",)
MAX_NAME = 200
_SPLIT = re.compile(r"\s*/\s*|\s*[‣•▪·]\s*")


def _clean(cell: str) -> str:
    """셀 텍스트의 " / "(줄바꿈 자리) 를 공백으로 합친다.

    '모두가 안심하는 / AX 철도안전 구축' → 한 줄."""
    return " ".join(cell.replace(" / ", " ").split())[:MAX_NAME]


def _items(cell: str) -> list[str]:
    return [t for t in (x.strip() for x in _SPLIT.split(cell)) if t]


def find_strategy_table(tables: Sequence[Sequence[Sequence[str]]]) -> list[list[str]] | None:
    """머리행이 경영목표(또는 전략목표)·전략과제로 시작하는 첫 표."""
    for table in tables:
        if not table:
            continue
        head = [c.replace(" ", "") for c in table[0]]
        if len(head) >= 2 and head[0].startswith(HEADER_GOAL) and head[1].startswith(HEADER_TASK):
            return [list(r) for r in table]
    return None


def build_strategy_draft(
    rows: Sequence[Sequence[str]],
    *,
    document: str,
    url: str,
    snapshot: str | None,
    location: str = "표 ‘전략목표 및 과제종합’",
) -> dict[str, Any]:
    """[머리행, (경영목표, 전략과제, 주요내용, KPI)…] → 초안 dict (korail_strategy.draft.yaml 내용).

    같은 경영목표가 rowspan 으로 반복된 행은 한 전략방향 아래 전략과제로 모인다.
    id 는 D1, D1-1 … 순서대로.
    """
    source = {"document": document, "url": url, "location": location, "snapshot": snapshot}
    directions: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        goal, task = _clean(row[0]), _clean(row[1])
        if not goal or not task or goal.replace(" ", "").startswith(HEADER_GOAL):
            continue
        d = index.get(goal)
        if d is None:
            d = {
                "id": f"D{len(directions) + 1}",
                "name": goal,
                "basis": "text",
                "source": dict(source),
                "tasks": [],
            }
            index[goal] = d
            directions.append(d)
        if any(t["name"] == task for t in d["tasks"]):
            continue
        entry: dict[str, Any] = {
            "id": f"{d['id']}-{len(d['tasks']) + 1}",
            "name": task,
            "basis": "text",
            "source": dict(source),
        }
        if len(row) > 2 and row[2].strip():
            entry["summary"] = _items(row[2])
        if len(row) > 3 and row[3].strip():
            entry["kpi"] = _items(row[3])
        d["tasks"].append(entry)
    draft = {
        "source": f"{document} (공사 홈페이지 {url}, 스냅샷 {snapshot or '-'})",
        "status": "draft",
        "basis": "text",
        "directions": directions,
    }
    StrategyCatalog.model_validate(draft)  # id 중복·형식 검증 (추가 키는 무시된다)
    if not directions:
        raise ValueError("표에서 경영목표·전략과제를 찾지 못했습니다.")
    return draft
