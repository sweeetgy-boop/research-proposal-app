"""② 스위치 off 회귀 (레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §1) — 세 스위치가
false 일 때 표 순서·blocking·keywords·판정 입력·관련 연구·저장소 호출이 스위치 도입 전(main 434581b)
스냅샷과 바이트 단위로 같다. 스냅샷은 `tests/fixtures/overlap_switch_off_snapshot.json`(하네스
`overlap_switch_harness`
로 main 코드에서 생성). 골든셋 12건 + 시범 합성(비둘기) 13 사례, FakeLLM·가짜 저장소만."""

from __future__ import annotations

import json

import pytest

from rra.domain.rules.overlap_switches import OFF, OverlapSwitches
from tests.application import overlap_switch_harness as h

SNAPSHOT = json.loads(h.SNAPSHOT.read_text(encoding="utf-8"))
NAMES = [name for name, _ in h.cases()]


def test_snapshot_covers_every_case_and_exercises_blocking_series_and_research():
    assert [r["name"] for r in SNAPSHOT] == NAMES
    assert any(a["blocking"] for r in SNAPSHOT for a in r["judged"]["alerts"])
    assert any(a["series"] for r in SNAPSHOT for a in r["judged"]["alerts"])
    assert all(r["related_research"] for r in SNAPSHOT)
    assert sum(1 for r in SNAPSHOT if r["judge_prompts"]) == len(NAMES) - 1  # 03 은 후보 0


async def test_switch_off_output_is_byte_identical_to_main_snapshot():
    rows = await h.run_all()
    assert h.dumps(rows) == h.dumps(SNAPSHOT)


@pytest.mark.parametrize("name", NAMES)
async def test_each_case_matches_with_explicit_off_switches(name):
    case = dict(h.cases())[name]
    expected = next(r for r in SNAPSHOT if r["name"] == name)
    got = await h.run_case(name, case, switches=OFF)
    assert json.loads(h.dumps([got]))[0] == expected


async def test_default_switches_are_all_false():
    assert OverlapSwitches() == OFF and not OFF.any_on
    for r in SNAPSHOT:  # 스냅샷(스위치 전) 행에는 facet_overlap 칸이 없다
        assert all("facet_overlap" not in a for a in r["judged"]["alerts"])
