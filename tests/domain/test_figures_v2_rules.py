"""[G] 그림 v2 규칙 — As-Is/To-Be 명세 검사, 분석 기법 목록·고르기·종류별 분석 규칙(정성·비교·
경제성), 출처, 비율 고르기, 인포그래픽 프롬프트, 추천 결정의 버전 비교."""

import pytest
from pydantic import ValidationError

from rra.domain.models.figure import (
    MAX_BOX,
    NEED_CALC,
    PRELIM_NOTE,
    Figure,
    FigureRecommendation,
    TechniqueSpec,
    parse_spec,
)
from rra.domain.rules import figures as rules
from rra.domain.rules import techniques as tr
from tests.figure_v2_helpers import (
    AS_IS,
    CATALOG,
    COST_BENEFIT,
    PUGH,
    REQ,
    SECTIONS,
    SNAP,
    SWOT,
    picks,
)

PUBLIC = [c for c in SNAP.chunks if c.visibility != "internal"]


def pool_for(tech=None):
    pool = rules.text_pool(SECTIONS, REQ, [c.text for c in PUBLIC])
    return rules.with_texts(pool, tech.fixed_texts()) if tech else pool


def sources():
    return tr.source_index(SECTIONS, REQ, [(c.chunk_id, c.text) for c in PUBLIC])


def analyse(key, data):
    tech = CATALOG.get(key)
    spec = TechniqueSpec.model_validate(tr.normalize_technique_data(data, tech))
    spec = tr.repair_technique(spec, tech, pool_for(tech), sources())
    problems = tr.validate_technique(spec, tech, sources()) or rules.validate_spec(
        spec, pool_for(tech)
    )
    return spec, problems


# ── 목록 ────────────────────────────────────────────────
def test_catalog_has_the_twenty_techniques_with_content_and_situation():
    keys = set(CATALOG.keys())
    assert len(CATALOG) == 20
    assert {
        "swot",
        "tows",
        "pmi",
        "force_field",
        "six_hats",
        "pestel",
        "cost_benefit",
        "cost_effectiveness",
        "lcc",
        "sensitivity",
        "weighted_matrix",
        "pugh",
        "ahp",
        "topsis",
        "dea",
        "fmea",
        "decision_tree",
        "scenario",
        "delphi",
        "systematic_review",
    } == keys
    for t in CATALOG.items:
        assert t.summary and t.fits and t.label and t.section
    fam = {t.key: t.family for t in CATALOG.items}
    assert {fam[k] for k in ("swot", "tows", "pmi", "force_field", "pestel", "six_hats")} == {
        "qualitative"
    }
    assert {fam[k] for k in ("pugh", "weighted_matrix", "ahp", "topsis", "fmea")} == {"evaluation"}
    assert {
        fam[k]
        for k in (
            "cost_benefit",
            "cost_effectiveness",
            "lcc",
            "sensitivity",
            "decision_tree",
            "scenario",
            "dea",
        )
    } == {"economic"}
    with pytest.raises(ValueError):
        tr.catalog_from({"techniques": [{"key": "x", "family": "magic"}]})


# ── 고르기 0~2 ─────────────────────────────────────────────
def test_parse_picks_keeps_zero_to_two_known_unique_and_records_none_reason():
    got = tr.parse_picks(picks("swot", "pugh", "lcc"), CATALOG)
    assert [p.technique for p in got.picks] == ["swot", "pugh"] and got.dropped == ("lcc",)
    got = tr.parse_picks(picks("swot", "swot", "magic"), CATALOG, limit=1)
    assert [p.technique for p in got.picks] == ["swot"] and set(got.dropped) == {"swot", "magic"}
    got = tr.parse_picks(picks("swot"), CATALOG, exclude=["swot"])
    assert got.picks == () and got.dropped == ("swot",)
    none = tr.parse_picks({"picks": [], "none_reason": "비교할 대안이 본문에 없음"}, CATALOG)
    assert none.picks == () and none.none_reason == "비교할 대안이 본문에 없음"
    assert tr.parse_picks({"picks": "swot"}, CATALOG) is None
    assert tr.parse_picks([], CATALOG) is None


# ── 정성 ────────────────────────────────────────────────
def test_qualitative_swot_needs_fixed_quadrants_ratings_and_sources():
    spec, problems = analyse("swot", SWOT)
    assert problems == [] and spec.note == PRELIM_NOTE
    assert [g.name for g in spec.groups] == ["강점", "약점", "기회", "위협"]
    assert all(
        it.rating in ("상", "중", "하") and it.amount is None for g in spec.groups for it in g.items
    )
    # 강도가 없으면 거절, 고정 묶음 이름이 아니면 거절
    no_rating = {
        "groups": [{**g, "items": [{**g["items"][0], "rating": None}]} for g in SWOT["groups"]]
    }
    assert tr.TECH_RATING in analyse("swot", no_rating)[1]
    renamed = {"groups": [{**SWOT["groups"][0], "name": "장점"}, *SWOT["groups"][1:]]}
    assert tr.TECH_GROUPS in analyse("swot", renamed)[1]
    # 출처 id 가 틀려도 글자로 찾아 잇는다 / 본문에 없는 항목은 빠진다
    fixed = {
        "groups": [
            {
                "name": "강점",
                "items": [
                    {"text": "검측 이력 자료를 축적해 왔음", "rating": "상", "source": "s:nope:9"},
                    {"text": "인공지능 로봇 도입", "rating": "상", "source": "s:method:0"},
                ],
            },
            *SWOT["groups"][1:],
        ]
    }
    spec, problems = analyse("swot", fixed)
    assert problems == []
    assert [it.text for it in spec.groups[0].items] == ["검측 이력 자료를 축적해 왔음"]
    assert spec.groups[0].items[0].source == "s:tech_importance:1"


def test_six_hats_and_pestel_accept_subset_of_four_groups():
    data = {
        "groups": [
            {
                "name": n,
                "items": [{"text": "검측 이력 분석", "rating": "중", "source": "s:method:0"}],
            }
            for n in ("정치", "경제", "사회", "기술")
        ]
    }
    assert analyse("pestel", data)[1] == []
    data["groups"] = data["groups"][:3]
    assert tr.TECH_GROUPS in analyse("pestel", data)[1]


# ── 비교·평가 ──────────────────────────────────────────────
def test_evaluation_pugh_uses_scale_symbols_and_preliminary_note():
    spec, problems = analyse("pugh", PUGH)
    assert problems == [] and spec.rows[1].cells == ["0", "−"]  # "-" → "−"
    assert spec.note == "제안 내용 기반 예비 평가"
    bad = {**PUGH, "rows": [{**PUGH["rows"][0], "cells": ["0", "상"]}, PUGH["rows"][1]]}
    assert tr.TECH_RATING in analyse("pugh", bad)[1]
    short = {**PUGH, "rows": [{**PUGH["rows"][0], "cells": ["0"]}, PUGH["rows"][1]]}
    assert tr.TECH_CELLS in analyse("pugh", short)[1]
    one_column = {**PUGH, "columns": ["제안 방식"]}
    assert tr.TECH_GROUPS in analyse("pugh", one_column)[1]  # 대안 2개 이상이어야 비교
    # 근거 밖 대안 이름은 출처 검사로 거절
    invented = {**PUGH, "columns": ["현행 방식", "드론 자율 점검"]}
    assert rules.TEXT_NOT_IN_SOURCES in analyse("pugh", invented)[1]


def test_fmea_has_fixed_columns_and_level_scale():
    data = {
        "columns": ["심각도", "발생도", "검출 난이도"],
        "rows": [
            {"name": "궤도 틀림이 반복 발생함", "cells": ["높음", "중", "low"], "source": ""},
            {"name": "다짐 효과가 오래 가지 않음", "cells": ["중", "중", "하"], "source": ""},
        ],
    }
    spec, problems = analyse("fmea", data)
    assert problems == [] and spec.rows[0].cells == ["상", "중", "하"]
    assert spec.rows[0].source == "input:current_state"  # 글자로 출처를 찾았다


# ── 경제성 ───────────────────────────────────────────────
def test_economic_amounts_only_from_sources_else_need_calc():
    spec, problems = analyse("cost_benefit", COST_BENEFIT)
    assert problems == []
    amounts = {it.text: it.amount for g in spec.groups for it in g.items}
    assert amounts["연간 궤도 보수비"] == "1,200억 원"  # 근거 수치 그대로
    assert amounts["검측 이력 분석"] == NEED_CALC  # 지어낸 금액 → 산출 필요
    assert amounts["유지보수 비용을 절감함"] == NEED_CALC  # 본문에 없는 30%
    assert all(it.rating is None for g in spec.groups for it in g.items)
    no_amount = {
        "groups": [
            {"name": "비용", "items": [{"text": "검측 이력 분석", "source": "s:method:0"}]},
            {"name": "편익", "items": [{"text": "유지보수 비용을 절감함", "amount": "상당함"}]},
        ]
    }
    spec, problems = analyse("cost_benefit", no_amount)
    assert problems == [] and {it.amount for g in spec.groups for it in g.items} == {NEED_CALC}


def test_provenance_rows_use_readable_labels_not_internal_ids():
    spec, _ = analyse("cost_benefit", COST_BENEFIT)
    rows = tr.provenance(spec, titles={"method": "2-다 연구 방법 및 주요내용"})
    by = {r["text"]: r for r in rows}
    assert by["검측 이력 분석"]["source_label"] == "2-다 연구 방법 및 주요내용 문장 1"
    assert by["연간 궤도 보수비"]["source_label"] == "근거 자료"
    swot, _ = analyse("swot", SWOT)
    labels = {r["source_label"] for r in tr.provenance(swot)}
    assert "제안 입력: 발생 원인" in labels and not any(":" in x.split(" ")[0] for x in labels)


# ── As-Is / To-Be ──────────────────────────────────────────
def test_as_is_to_be_spec_texts_counts_tags_and_box_length():
    spec = parse_spec("as_is_to_be", rules.normalize_spec_data(AS_IS))
    pool = pool_for()
    assert rules.validate_spec(spec, pool) == []
    texts = rules.texts_of(spec)
    assert texts[0] == rules.AS_IS_HEAD and rules.TO_BE_HEAD in texts and spec.solution in texts
    # 칸 이름이 정해진 이름이 아니면 다듬기가 자리대로 바꾼다
    odd = {**AS_IS, "as_is": [{**AS_IS["as_is"][0], "tag": "문제"}, *AS_IS["as_is"][1:]]}
    fixed = rules.repair_spec(parse_spec("as_is_to_be", odd), pool)
    assert fixed.as_is[0].tag == "현황" and rules.validate_spec(fixed, pool) == []
    raw = parse_spec("as_is_to_be", odd)
    assert rules.SIDE_TAG in rules.validate_spec(raw, pool)
    # 근거 밖 글자는 거절
    bad = {**AS_IS, "solution": "드론 자율 비행 점검"}
    assert rules.TEXT_NOT_IN_SOURCES in rules.validate_spec(parse_spec("as_is_to_be", bad), pool)
    # 쪽마다 3~4칸
    with pytest.raises(ValidationError):
        parse_spec("as_is_to_be", {**AS_IS, "as_is": AS_IS["as_is"][:2]})
    with pytest.raises(ValidationError):
        parse_spec("as_is_to_be", {**AS_IS, "to_be": AS_IS["to_be"] * 2})
    # 칸 글자는 30자(1~2줄)로 줄인다 — 앞부분 원문이라 출처 검사 통과
    long_text = "검측 이력을 분석해 구간별 진행 속도를 추정함 그리고 보수 우선순위를 산정함"
    longer = {**AS_IS, "to_be": [{"tag": "해결 방안", "text": long_text}, *AS_IS["to_be"][1:]]}
    clipped = parse_spec("as_is_to_be", rules.normalize_spec_data(longer))
    assert len(clipped.to_be[0].text) <= MAX_BOX and long_text.startswith(clipped.to_be[0].text)
    with pytest.raises(ValidationError):
        parse_spec("as_is_to_be", longer)  # 줄이지 않으면 형식 오류


def test_concept_lines_are_clipped_to_box_length_on_new_specs():
    data = {
        "boxes": [
            {
                "label": "현황",
                "lines": [
                    "궤도 틀림 점검을 주기 순회로 수작업 측정하고 야간 차단 시간에만 점검 가능"
                ],
            },
            {"label": "문제", "lines": ["다짐"]},
            {"label": "해결 방안", "lines": ["검측"]},
            {"label": "기대효과", "lines": ["절감"]},
        ]
    }
    spec = parse_spec("concept", rules.normalize_spec_data(data))
    assert len(spec.boxes[0].lines[0]) <= MAX_BOX


# ── 비율·프롬프트 ───────────────────────────────────────────
def test_choose_aspect_follows_content_amount():
    as_is = parse_spec("as_is_to_be", AS_IS)
    longest = max(len(i.text) for i in [*as_is.as_is, *as_is.to_be])
    assert rules.choose_aspect(as_is) == ("21:9" if longest <= 20 else "16:9")
    four = parse_spec("as_is_to_be", {**AS_IS, "as_is": [*AS_IS["as_is"], AS_IS["as_is"][0]]})
    assert rules.choose_aspect(four) == "16:9"  # [23] 모두 가로 비율
    swot, _ = analyse("swot", SWOT)
    most = max(len(g.items) for g in swot.groups)
    assert rules.choose_aspect(swot) == ("21:9" if most <= 2 else "16:9")  # 네 칸 가로 한 줄
    pugh, _ = analyse("pugh", PUGH)
    assert rules.choose_aspect(pugh) == ("21:9" if len(pugh.rows) <= 3 else "16:9")
    cb, _ = analyse("cost_benefit", COST_BENEFIT)
    assert rules.choose_aspect(cb) == "21:9"  # 묶음 2개·항목 2개 이하 → 낮고 넓게
    for a in (rules.choose_aspect(x) for x in (as_is, four, swot, pugh, cb)):
        assert a in rules.ASPECTS


def test_infographic_prompt_for_new_kinds_keeps_exact_texts_and_colours():
    as_is = parse_spec("as_is_to_be", AS_IS)
    prompt = rules.image_prompt(as_is, caption="현재와 연구 후")
    for t in rules.texts_of(as_is):
        assert f"- {t}" in prompt
    assert "회색·주황" in prompt and "파랑·초록" in prompt and "가운데 큰 화살표" in prompt
    assert "새로 디자인" in prompt and "가로세로 비율 16:9" in prompt and "흑백 인쇄" in prompt
    # 제목 글자가 목록에 없는 종류는 그림 위에 제목을 지어 쓰지 않는다 (실측: "…인포그래픽" 제목)
    assert "제목 글자를 새로 쓰지 않는다" in prompt
    swot, _ = analyse("swot", SWOT)
    p2 = rules.image_prompt(swot)
    # 예비 평가 표시는 그림 밖 캡션 줄로 (2026-10-29) — 그림 프롬프트에 넣지 않는다
    assert "SWOT 분석" in p2 and "가로 한 줄에 나란히" in p2 and PRELIM_NOTE not in p2
    assert f"가로세로 비율 {rules.choose_aspect(swot)}" in p2 and "좌우 여백 최소" in p2
    for t in rules.texts_of(swot):
        assert f"- {t}" in p2
    pugh, _ = analyse("pugh", PUGH)
    assert "평가 표" in rules.image_prompt(pugh)
    # 데이터 그림은 값·기간 비율만 지킨다 (예전 "배치 그대로"는 없음)
    sched = parse_spec(
        "schedule",
        {"total_months": 12, "stages": [{"name": "a", "start_month": 1, "end_month": 6}] * 2},
    )
    assert "막대 길이·기간 비율" in rules.image_prompt(sched)


# ── 추천 결정 = 버전 변경 ─────────────────────────────────────
def _fig(status="pending", technique="swot", spec=None, included=True):
    s = spec or analyse("swot", SWOT)[0]
    return Figure(
        id="f:tech_importance:t1",
        kind="technique",
        section="tech_importance",
        spec=s,
        included=included,
        recommendation=FigureRecommendation(technique=technique, reason="이유", status=status),
    )


def test_figure_diff_counts_each_recommendation_decision_once():
    pending, accepted = _fig(), _fig("accepted")
    dismissed = _fig("dismissed", included=False)
    assert [r["change"] for r in rules.figure_diff([pending], [accepted])] == ["accepted"]
    assert [r["change"] for r in rules.figure_diff([pending], [dismissed])] == ["dismissed"]
    assert [r["change"] for r in rules.figure_diff([dismissed], [accepted])] == ["restored"]
    pugh, _ = analyse("pugh", PUGH)
    swapped = _fig(technique="pugh", spec=pugh)
    assert [r["change"] for r in rules.figure_diff([pending], [swapped])] == ["swapped"]
    assert rules.undecided([pending, accepted, dismissed]) == [pending]
