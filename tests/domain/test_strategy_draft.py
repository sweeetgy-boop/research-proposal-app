"""전략체계 초안 — 중장기 경영목표 표(fixture)에서 전략방향·전략과제를 뽑는다. 지어내지 않는다."""

from pathlib import Path

import pytest

from rra.adapters.sources.korail_web import strategy_draft_from_html
from rra.adapters.sources.korail_web._html import parse_tables
from rra.domain.models import StrategyCatalog
from rra.domain.rules.strategy_draft import build_strategy_draft, find_strategy_table

FIX = Path(__file__).parents[1] / "fixtures" / "korail_web" / "contents_1900.html"


def test_draft_from_real_table_has_five_directions_and_fifteen_tasks():
    html = FIX.read_text(encoding="utf-8")
    draft = strategy_draft_from_html(
        html, url="https://info.korail.com/info/contents.do?key=1900", snapshot="2026-10-27"
    )
    assert draft["status"] == "draft" and draft["basis"] == "text"
    assert "중장기 경영목표" in draft["source"] and "2026-10-27" in draft["source"]
    assert [d["id"] for d in draft["directions"]] == ["D1", "D2", "D3", "D4", "D5"]
    assert draft["directions"][0]["name"] == "모두가 안심하는 AX 철도안전 구축"
    tasks = [t for d in draft["directions"] for t in d["tasks"]]
    assert len(tasks) == 15
    first = draft["directions"][0]["tasks"][0]
    assert first == {
        "id": "D1-1",
        "name": "AI기반 예방적 안전관리 구축",
        "basis": "text",
        "source": {
            "document": "중장기 경영목표",
            "url": "https://info.korail.com/info/contents.do?key=1900",
            "location": "표 ‘전략목표 및 과제종합’",
            "snapshot": "2026-10-27",
        },
        "summary": [
            "실시간 위험 감시․예측하는 AI 활용 통합안전관리 플랫폼 구축",
            "기후변화 본격화에 대응한 AI 활용 선제적 재난안전관리 대응",
            "AI기반 보안시스템 구축 및 개인정보보호체계 확립",
        ],
        "kpi": [
            "안전관리율",
            "AI・안전투자확대",
            "재난관리평가",
            "정보보안수준",
            "운영시스템 사고제로",
        ],
    }
    catalog = StrategyCatalog.model_validate(draft)
    assert len(catalog.options()) == 15 and catalog.status == "draft"
    assert catalog.label == "전략체계 초안(확인 전)"


def test_every_task_name_appears_verbatim_in_the_page():
    html = FIX.read_text(encoding="utf-8")
    draft = strategy_draft_from_html(html, url="u", snapshot=None)
    flat = " ".join(html.split())
    for d in draft["directions"]:
        for t in d["tasks"]:
            assert all(part in flat for part in t["name"].split()), t["name"]


def test_find_strategy_table_and_empty_rows_rejected():
    tables = parse_tables(FIX.read_text(encoding="utf-8"))
    rows = find_strategy_table(tables)
    assert rows is not None and rows[0][:2] == ["경영목표", "전략과제"]
    assert find_strategy_table([[["연도", "값"]]]) is None
    with pytest.raises(ValueError):
        build_strategy_draft([["경영목표", "전략과제"]], document="d", url="u", snapshot=None)


def test_duplicate_tasks_within_a_direction_are_kept_once():
    rows = [["경영목표", "전략과제"], ["A", "x"], ["A", "x"], ["B", "y"]]
    draft = build_strategy_draft(rows, document="d", url="u", snapshot=None)
    assert [(d["name"], [t["id"] for t in d["tasks"]]) for d in draft["directions"]] == [
        ("A", ["D1-1"]),
        ("B", ["D2-1"]),
    ]
