"""그림 칸 글자 — 잘라 줄이지 않고 뜻이 완결된 짧은 구절로 (2026-10-29, ADR 0044)."""

import pytest

from rra.domain.models import Section, Sentence
from rra.domain.rules import figure_phrases as fp
from rra.domain.rules.figures import text_pool

POOL = text_pool(
    [
        Section(
            key="method",
            sentences=[
                Sentence(text="신설역 수요를 별도 가정으로 보정해 오차가 발생함."),
                Sentence(text="시계열 모형으로 다음 해 수요를 예측해 수송계획에 쓴다."),
                Sentence(text="효과 분석과 회의 결과를 반영하고 선로 점검 피해를 줄일 수 있음."),
                Sentence(text="이용자 수와 정확도를 높인다."),
            ],
        )
    ],
    None,
)


@pytest.mark.parametrize(
    "text",
    [
        "신설역 수요를 별도 가정으로",  # 소유자가 든 예 — 조사로 끝남
        "궤도검측차가 분기별로 측정하고",  # 시범 그림에서 잘린 구절 (shorten_spec 22→16자)
        "준비 단계: 전력 이력 및",
        "기관사 판단 지연으로 방호 신호가 늦어질 수",
        "검측 이력을 분석해",
        "보수 우선순위를 위한",
        "수요 예측…",
        "수요 예측...",
        "역사 상층부 활용(제안",
        "보수 우선순위,",
        "및 보수 우선순위 산정",
        "예측해 수송계획에 쓴다",  # 앞이 잘림
    ],
)
def test_incomplete_phrases_are_flagged(text):
    assert fp.incomplete_reason(text, POOL) is not None
    assert fp.phrase_problem(text, 40, POOL) == fp.PHRASE_INCOMPLETE


@pytest.mark.parametrize(
    "text",
    [
        "신설역 수요 별도 가정",
        "신설역 수요 별도 산정",
        "효과 분석",
        "회의 결과",
        "선로 점검",
        "피해 저감",
        "정확도 향상",
        "보고서 작성",
        "이용자 수",
        "유지보수 비용 절감",
        "검측 이력 기반 보수 우선순위 산정",
        "정보 없음",
        "목표치 확인 필요",
    ],
)
def test_complete_phrases_pass(text):
    assert fp.incomplete_reason(text, POOL) is None
    assert fp.phrase_problem(text, 40, POOL) is None


def test_mid_word_cut_is_flagged_with_the_source_words():
    # "가정으로" 가 근거에 있다 — "가" 로 끝나면 낱말 중간에서 끊긴 것
    assert fp.incomplete_reason("신설역 수요를 별도 가", POOL) == "낱말 중간에서 끊김"
    # 근거 낱말 + 조사·어미 꼴이면 끊김이 아니다 ("가정" ← "가정으로")
    assert fp.incomplete_reason("수요 별도 가정", POOL) is None


def test_limit_is_counted_with_spaces_and_tightened_for_redraws():
    assert fp.phrase_problem("가" * 21, 20) == fp.PHRASE_TOO_LONG
    assert fp.phrase_problem("가" * 20, 20) is None
    base = fp.limits_for("as_is_to_be")
    tight = fp.limits_for("as_is_to_be", fp.TIGHTEN)
    assert base == {"as_is[].text": 20, "to_be[].text": 20, "solution": 14}
    assert tight == {"as_is[].text": 15, "to_be[].text": 15, "solution": 10}
    assert fp.limits_for("stat_chart") == {}  # 수치 그래프 이름·값은 표기 그대로


def test_slots_use_model_dump_paths_and_skip_fixed_texts():
    data = {
        "projects": [
            {"title": "기존 과제 A", "cells": {"연구목표": "정보 없음", "방법": "검측 이력 분석"}}
        ],
        "proposal": {"title": "제안", "cells": {"연구목표": "보수 우선순위 산정"}},
        "aspects": ["연구목표", "방법"],
    }
    paths = {s.path: s.limit for s in fp.slots("comparison", data)}
    assert paths == {"projects.0.cells.방법": 18, "proposal.cells.연구목표": 18}
    tech = {"groups": [{"name": "강점", "items": [{"text": "검측 이력 축적", "source": "s:x:0"}]}]}
    assert [s.path for s in fp.slots("technique", tech)] == ["groups.0.items.0.text"]


def test_limits_prompt_lists_every_slot_with_the_rule_and_example():
    text = fp.limits_prompt("technique")
    assert "[칸 글자 수 상한]" in text and "16자 안" in text
    assert "뜻이 완결된 짧은" in text and "신설역 수요 별도 가정" in text
    assert fp.limits_prompt("stat_chart") == ""
    tight = fp.limits_prompt("as_is_to_be", fp.TIGHTEN)
    assert "15자 안" in tight and "10자 안" in tight


def test_complete_window_keeps_whole_words_and_the_head_noun():
    # 끝 낱말의 조사만 던다 — 낱말은 자르지 않는다
    assert fp.complete_window("신설역 수요를 별도 가정으로", 20, POOL) == "신설역 수요를 별도 가정"
    got = fp.complete_window("시계열 모형으로 다음 해 수요를 예측해 수송계획에 쓴다", 15, POOL)
    assert got is not None and len(got) <= 15 and fp.is_complete(got, POOL)
    words = "시계열 모형으로 다음 해 수요를 예측해 수송계획에 쓴다".split()
    assert all(w in words for w in got.split())
    assert fp.complete_window("보수 우선순위를 위한", 4, POOL) is None  # 완결 묶음 없음


def test_salvage_replaces_drops_or_refuses():
    data = {
        "as_is": [
            {"tag": "현황", "text": "신설역 수요를 별도 가정으로"},
            {"tag": "원인", "text": "오차가 발생함"},
            {"tag": "한계", "text": "효과 분석"},
        ],
        "to_be": [
            {"tag": "목표", "text": "수요 예측"},
            {"tag": "해결 방안", "text": "선로 점검"},
            {"tag": "기대효과", "text": "피해 저감"},
        ],
        "solution": "수요 예측",
    }
    fixed = fp.salvage("as_is_to_be", data, POOL)
    assert fixed is not None and fixed["as_is"][0]["text"] == "신설역 수요를 별도 가정"
    assert data["as_is"][0]["text"] == "신설역 수요를 별도 가정으로"  # 원본은 그대로
    # 설명 줄은 완결 묶음이 없으면 뺀다 (상자에 한 줄 이상은 남긴다)
    concept = {
        "boxes": [
            {"label": "현황", "lines": ["선로 점검", "및 위한"]},
            {"label": "문제", "lines": ["오차"]},
            {"label": "해결 방안", "lines": ["수요 예측"]},
            {"label": "기대효과", "lines": ["피해 저감"]},
        ]
    }
    out = fp.salvage("concept", concept, POOL)
    assert out is not None and out["boxes"][0]["lines"] == ["선로 점검"]
    # 빼면 안 되는 칸(해결 방안 한 줄)에 완결 묶음이 없으면 받지 않는다
    bad = {**data, "solution": "및 위한"}
    assert fp.salvage("as_is_to_be", bad, POOL) is None


def test_exempt_texts_are_not_checked():
    data = {"stages": [{"name": "신설역 수요를 별도 가정으로", "start_month": 1, "end_month": 2}]}
    assert fp.problems("schedule", data, POOL)
    assert (
        fp.problems("schedule", data, POOL, exempt=["'신설역 수요를 별도 가정으로' 로 바꿔"]) == []
    )


def test_correction_hint_names_the_text_and_why():
    bad = fp.problems("as_is_to_be", {"as_is": [{"tag": "현황", "text": "가" * 25}]}, POOL)
    hint = fp.correction_hint(bad)
    assert "20자 넘음(25자)" in hint and "잘라 쓰지 않는다" in hint
    bad2 = fp.problems("as_is_to_be", {"solution": "수요를 별도 가정으로"}, POOL)
    assert "끝맺지 않은 구절(조사·연결어미로 끝남)" in fp.correction_hint(bad2)


def test_schema_overlong_reports_texts_instead_of_cutting():
    assert fp.schema_overlong({"boxes": [{"label": "현황", "lines": ["가" * 31]}]}) == ["가" * 31]
    assert fp.schema_overlong({"stages": [{"name": "가" * 41}]}) == ["가" * 41]
    assert fp.schema_overlong({"groups": [{"items": [{"source": "s:" + "x" * 80}]}]}) == []


def test_nominal_form_of_a_source_verb_counts_as_source_but_new_words_do_not():
    pool = text_pool(
        [
            Section(
                key="method",
                sentences=[Sentence(text="성장 속도를 추적하지 못하고 사진만 남는다.")],
            )
        ],
        None,
    )
    assert pool.has_text("성장 속도 추적 못함")  # 못하… → 못함
    assert pool.has_text("사진만 남음")  # 남는… → 남음
    assert not pool.has_text("성장 속도 미추적")  # 바꿔 쓴 낱말
    assert not pool.has_text("사진만 잔존")


def test_salvage_also_replaces_texts_outside_sources_with_in_source_words():
    pool = text_pool(
        [Section(key="method", sentences=[Sentence(text="동일 균열의 성장 속도 추적이 어렵다.")])],
        None,
    )
    data = {"boxes": [{"label": "현황", "lines": ["동일 균열의 성장 속도 미확인"]}]}
    out = fp.salvage("concept", data, pool, also=["동일 균열의 성장 속도 미확인"])
    assert out is not None and out["boxes"][0]["lines"] == ["동일 균열의 성장 속도"]
