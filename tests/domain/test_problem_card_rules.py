"""문제 정의 카드 규칙 (ADR 0065, 계약 problem-card.md 2·3절) — 파싱·검증·근거 판정·장소어 제거·
사용자 항목 보존·수정 반영·의존표·TRIZ 고정 목록."""

from __future__ import annotations

import copy

from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import (
    BASIS_GUESSED,
    BASIS_STATED,
    CARD_DEPENDENTS,
    ProblemCard,
)
from rra.domain.rules import problem_card as rules
from rra.domain.rules import triz
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.novelty import ProblemAxisRule

REQ = ProposalRequest(
    title_hint="철도역사 비둘기 침입 방지",
    current_state="역사 승강장 지붕에 비둘기가 드나들어 배설물 민원이 반복됨",
    root_cause="출입구가 열려 있어 비둘기 침입 경로가 막히지 않음",
    limitation="그물 설치는 미관을 해치고 유지관리가 어려움",
    goal="역사 구조에 맞는 비둘기 침입 방지 방법을 마련함",
)
AXIS = ProblemAxisRule()
RULE = KeywordRule()
RAW = {
    "facets": {
        "phenomenon": "비둘기 배설물 민원 반복",
        "target": "비둘기",
        "place": "철도역사 승강장 지붕",
        "cause": "열린 출입구로 비둘기 침입",
        "harm": "배설물 민원",
        "desired": "비둘기 침입 방지",
    },
    "function_ko": "비둘기의 침입을 막는다",
    "function_en": "prevent pigeons from entering and roosting",
    "ladder": {
        "concrete": "비둘기 침입 방지",
        "general": "조류 침입 차단",
        "abstract": "유해동물 접근 억제",
    },
    "terms": {
        "objects_ko": ["비둘기", "조류", "유해동물", "승강장", "철도역사"],
        "actions_ko": ["침입", "착좌", "방법"],
        "objects_en": ["pigeon", "bird", "station"],
        "actions_en": ["intrusion", "roosting"],
    },
    "contradiction": {
        "improve": "비둘기 침입 방지",
        "worsen": "미관과 유지관리",
        "principles": [{"number": 3, "name": "아무 이름"}, 15, 99, "24", 3],
    },
    "causes": ["출입구가 열려 침입 경로가 남음", "구조 개방 부위를 막을 기준이 없음"],
    "ipc": ["A01M-029/00", "e04h 1/12", "잘못된 코드", "A01M 29/00"],
    "science_class": ["철도교통기술", "건설·교통", "셋째"],
    "nature": {"kind": "난해", "mode": "실증형"},
    "signals": ["unclear_cause", "made_up", "few_analogies"],
}


def parse(raw=None, **kw):
    return rules.parse_card(RAW if raw is None else raw, REQ, axis=AXIS, rule=RULE, **kw)


def card() -> ProblemCard:
    found = parse().card
    assert found is not None
    return found


def variant(**changes) -> dict:
    raw = copy.deepcopy(RAW)
    raw.update(changes)
    return raw


# ── TRIZ ──────────────────────────────────────────────────
def test_triz_table_has_forty_fixed_names():
    assert len(triz.PRINCIPLES) == 40
    assert triz.principle_name(1) == "분할" and triz.principle_name(40) == "복합 재료"
    assert triz.principle_name(35) == "속성 변환"
    assert triz.principle_name(0) is None and triz.principle_name(41) is None


def test_triz_keeps_numbers_in_range_and_rewrites_names():
    got = triz.principles([{"number": 3, "name": "지어낸 이름"}, 15, 99, "24", 3, True, 2.5, 0])
    assert [(p.number, p.name) for p in got] == [(3, "국소적 성질"), (15, "역동성"), (24, "매개체")]


# ── 파싱·검증 ──────────────────────────────────────────────
def test_parse_builds_card_from_json_object():
    c = card()
    assert c.function_ko.value == "비둘기의 침입을 막는다"
    assert c.function_en.value == "prevent pigeons from entering and roosting"
    assert [s.level for s in c.ladder] == ["구체", "일반화", "추상화"]
    assert c.nature.kind == "난해" and c.nature.mode == "실증형"
    assert c.methods == ["core"]
    assert [p.name for p in c.contradiction.principles] == ["국소적 성질", "역동성", "매개체"]


def test_parse_rejects_non_object_and_empty_function_sentence():
    assert rules.parse_card(["x"], REQ).card is None
    assert rules.parse_card("글", REQ).card is None
    assert parse(variant(function_ko="")).card is None


def test_field_with_number_not_in_input_is_cleared():
    out = parse(variant(function_ko="비둘기 침입을 80% 줄인다"))
    assert out.card is None  # 기능 문장이 비워져 진단 실패
    out = parse(variant(causes=["민원이 연 300건 발생", "출입구가 열려 침입 경로가 남음"]))
    assert [c.value for c in out.card.causes] == ["출입구가 열려 침입 경로가 남음"]
    assert ("causes.0", rules.CLEARED_NUMBER) in out.cleared


def test_field_with_agency_or_law_name_not_in_input_is_cleared():
    raw = variant(
        facets={**RAW["facets"], "harm": "국토교통부 지적 사항", "cause": "철도안전법 위반"}
    )
    out = parse(raw)
    assert out.card.facets.harm.value == "" and out.card.facets.cause.value == ""
    assert ("facets.harm", rules.CLEARED_NAME) in out.cleared
    assert ("facets.cause", rules.CLEARED_NAME) in out.cleared


def test_foreign_script_field_is_cleared_and_hangul_in_english_is_cleared():
    out = parse(variant(function_en="비둘기 prevent pigeons"))
    assert out.card.function_en.value == ""
    assert ("function_en", rules.CLEARED_HANGUL) in out.cleared
    out = parse(variant(ladder={**RAW["ladder"], "general": "鳥類 침입 차단"}))
    assert [s.level for s in out.card.ladder] == ["구체", "추상화"]
    assert ("ladder.일반화", rules.CLEARED_FOREIGN) in out.cleared


def test_signals_only_enumerated_values_and_nature_enum():
    c = card()
    assert c.signals == ["unclear_cause", "few_analogies"]
    out = parse(variant(nature={"kind": "아주 어려움", "mode": "연구형"}))
    assert out.card.nature.kind is None and out.card.nature.mode == "연구형"


def test_ipc_codes_are_normalized_deduped_and_capped():
    c = card()
    assert [x.code for x in c.ipc] == ["A01M 29/00", "E04H 1/12"]
    assert all(x.verified == "unverified" and x.label == "" for x in c.ipc)
    assert [x.code for x in c.science_class] == ["철도교통기술", "건설·교통"]
    assert rules.normalize_ipc("a01m29/00") == "A01M 29/00"
    assert rules.normalize_ipc("A01M") == "A01M"
    assert rules.normalize_ipc("A01M 29") == "A01M 29/00"
    assert rules.normalize_ipc("ZZ9") is None
    assert rules.ipc_group_prefix("A01M-029/00") == "A01M 29/"
    assert rules.ipc_group_prefix("A01M") == "A01M"


# ── basis ─────────────────────────────────────────────────
def test_basis_is_decided_by_rule_not_by_model():
    raw = variant(function_ko={"value": "비둘기의 침입을 막는다", "basis": "추정"})
    c = parse(raw).card
    assert c.function_ko.basis == BASIS_STATED  # 낱말이 입력에 있다 — AI 의 신고는 보지 않는다
    assert c.function_en.basis == BASIS_STATED  # 번역은 국문 기능 문장을 따른다
    raw = variant(function_ko={"value": "조류의 착좌를 억제한다", "basis": "근거 있음"})
    assert parse(raw).card.function_ko.basis == BASIS_GUESSED


def test_basis_of_uses_stems_and_prefix_match():
    texts = rules.request_texts(REQ)
    assert rules.basis_of("비둘기가 침입해 배설물을 남김", texts, RULE) == BASIS_STATED
    assert rules.basis_of("초음파 퇴치기 성능 저하", texts, RULE) == BASIS_GUESSED
    assert rules.basis_of("", texts, RULE) == BASIS_GUESSED


# ── 문제어 ─────────────────────────────────────────────────
def test_terms_drop_place_words_generic_words_and_abstract_step_words():
    out = parse()
    t = out.card.terms
    assert t.objects_ko == ["비둘기", "조류"]  # 유해동물(추상화 단)·승강장·철도역사(장소) 빠짐
    assert t.actions_ko == ["침입", "착좌"]  # '방법' 은 일반어
    assert t.objects_en == ["pigeon", "bird"]  # station 은 장소 말
    assert t.actions_en == ["intrusion", "roosting"]
    assert "terms" in out.changed


def test_terms_drop_words_of_place_facet_even_if_not_in_axis_list():
    raw = variant(
        facets={**RAW["facets"], "place": "환승통로 캐노피"},
        terms={"objects_ko": ["비둘기", "캐노피", "환승통로"], "actions_ko": ["침입"]},
    )
    assert parse(raw).card.terms.objects_ko == ["비둘기"]


def test_terms_split_phrases_into_words_and_keep_language_apart():
    terms, dropped = rules.clean_terms(
        {
            "objects_ko": ["비둘기 배설물", "bird"],
            "objects_en": ["Bird Droppings", "비둘기"],
            "actions_en": ["the cleaning"],
        },
        axis=AXIS,
        rule=RULE,
    )
    assert terms.objects_ko == ["비둘기", "배설물"]
    assert terms.objects_en == ["bird", "droppings"]
    assert terms.actions_en == ["cleaning"]
    assert dropped == 3


# ── 원인 불일치 ────────────────────────────────────────────
def test_cause_mismatch_sets_needs_check():
    c = card()
    assert c.causes[0].needs_check is False and c.checks == []
    out = parse(variant(causes=["먹이를 주는 이용객이 많음"]))
    assert out.card.causes[0].needs_check is True
    assert out.card.checks == [rules.CHECK_CAUSE_MISMATCH]


def test_user_cause_never_needs_check():
    c = parse(variant(causes=["먹이를 주는 이용객이 많음"])).card
    after = c.model_copy(
        update={"causes": [c.causes[0].model_copy(update={"value": "천장 틈새가 넓음"})]}
    )
    edited, _ = rules.apply_edits(c, after, ["cause"])
    edited = rules.recheck_cause(edited, REQ, RULE)
    assert edited.causes[0].origin == "user" and edited.causes[0].needs_check is False
    assert edited.checks == []


# ── 사용자 항목 보존 ───────────────────────────────────────
def test_keep_user_items_preserves_user_fields_on_rediagnosis():
    old = card()
    after = old.model_copy(
        update={
            "function_ko": old.function_ko.model_copy(update={"value": "조류의 착좌를 막는다"}),
            "ipc": [old.ipc[0].model_copy(update={"code": "E04B 1/72"})],
        }
    )
    edited, _ = rules.apply_edits(old, after, ["function_ko", "ipc"])
    fresh = parse(variant(function_ko="비둘기 침입 경로를 막는다")).card
    merged = rules.keep_user_items(fresh, edited)
    assert merged.function_ko.value == "조류의 착좌를 막는다"
    assert merged.function_ko.origin == "user"
    assert merged.function_ko.ai_value == "비둘기의 침입을 막는다"
    assert merged.ipc[0].code == "E04B 1/72" and merged.ipc[0].origin == "user"
    assert [c.code for c in merged.ipc[1:]] == ["A01M 29/00", "E04H 1/12"]
    assert merged.function_en.origin == "ai"  # 사용자 항목이 아닌 것은 새 값
    assert rules.keep_user_items(fresh, None) is fresh


def test_user_items_view_lists_only_user_fields():
    old = card()
    assert rules.user_items_view(old) == {} and rules.user_items_view(None) == {}
    after = old.model_copy(
        update={"function_ko": old.function_ko.model_copy(update={"value": "조류 착좌 방지"})}
    )
    edited, _ = rules.apply_edits(old, after, ["function_ko"])
    assert rules.user_items_view(edited) == {"기능 문장": "조류 착좌 방지"}


# ── 수정 반영·의존표 ───────────────────────────────────────
def test_apply_edits_takes_only_named_fields_from_after():
    old = card()
    after = old.model_copy(
        update={
            "function_ko": old.function_ko.model_copy(update={"value": "조류의 착좌를 막는다"}),
            "function_en": old.function_en.model_copy(update={"value": "tampered"}),
        }
    )
    edited, reruns = rules.apply_edits(old, after, ["function_ko"])
    assert edited.function_ko.value == "조류의 착좌를 막는다"
    assert edited.function_ko.origin == "user" and edited.function_ko.basis == BASIS_STATED
    assert edited.function_ko.ai_value == old.function_ko.value
    assert edited.function_en == old.function_en  # 이름이 없는 항목은 before 그대로
    assert reruns == list(CARD_DEPENDENTS["function_ko"]) == ["derive", "analogy", "plans_stale"]


def test_apply_edits_keeps_first_ai_value_across_repeated_edits():
    old = card()
    step1, _ = rules.apply_edits(
        old,
        old.model_copy(
            update={"function_ko": old.function_ko.model_copy(update={"value": "첫 수정"})}
        ),
        ["function_ko"],
    )
    step2, _ = rules.apply_edits(
        step1,
        step1.model_copy(
            update={"function_ko": step1.function_ko.model_copy(update={"value": "둘째 수정"})}
        ),
        ["function_ko"],
    )
    assert step2.function_ko.value == "둘째 수정"
    assert step2.function_ko.ai_value == old.function_ko.value


def test_apply_edits_contradiction_revalidates_principles_and_keeps_ai_values():
    old = card()
    new_con = {
        **old.contradiction.model_dump(),
        "improve": "차단 효과",
        "principles": [{"number": 7, "name": "틀린 이름"}, {"number": 1, "name": ""}],
    }
    after = ProblemCard.model_validate({**old.model_dump(), "contradiction": new_con})
    edited, reruns = rules.apply_edits(old, after, ["contradiction"])
    con = edited.contradiction
    assert con.origin == "user" and con.improve == "차단 효과"
    assert con.ai_improve == old.contradiction.improve
    assert [(p.number, p.name) for p in con.principles] == [(7, "포개기"), (1, "분할")]
    assert reruns == ["principles", "plans_stale"]


def test_apply_edits_reruns_are_union_in_order_and_empty_for_facets():
    old = card()
    _, reruns = rules.apply_edits(old, old, ["cause", "ipc", "science_class"])
    assert reruns == ["checks", "clarify", "codes", "analogy", "plans_stale"]
    _, reruns = rules.apply_edits(old, old, ["facets", "nature"])
    assert reruns == []


def test_apply_edits_codes_mark_new_code_as_user_and_drop_bad_format():
    old = card()
    after = ProblemCard.model_validate(
        {
            **old.model_dump(),
            "ipc": [
                old.ipc[0].model_dump(),
                {"code": "b08b 1/00"},
                {"code": "코드 아님"},
            ],
        }
    )
    edited, _ = rules.apply_edits(old, after, ["ipc"])
    assert [(c.code, c.origin) for c in edited.ipc] == [("A01M 29/00", "ai"), ("B08B 1/00", "user")]


def test_apply_edits_strips_personal_data_from_user_text():
    old = card()
    after = old.model_copy(
        update={
            "function_ko": old.function_ko.model_copy(
                update={"value": "비둘기 침입을 막는다 문의 010-1234-5678"}
            )
        }
    )
    edited, _ = rules.apply_edits(old, after, ["function_ko"])
    assert "010-1234-5678" not in edited.function_ko.value


def test_apply_derived_replaces_only_non_user_items():
    old = card()
    user_ladder, _ = rules.apply_edits(old, old, ["ladder"])
    derived = parse(
        variant(
            function_en="deter birds from perching",
            ladder={"concrete": "조류 착좌 방지", "general": "조류 접근 차단", "abstract": ""},
        ),
        function_ko="조류의 착좌를 막는다",
    ).card
    out = rules.apply_derived(user_ladder, derived)
    assert out.function_en.value == "deter birds from perching"
    assert out.ladder == user_ladder.ladder  # 사용자 항목은 그대로
    empty = derived.model_copy(
        update={"function_en": derived.function_en.model_copy(update={"value": ""})}
    )
    assert rules.apply_derived(old, empty).function_en == old.function_en  # 빈 값이면 그대로


# ── 코드 확인 결과·화면 ────────────────────────────────────
def test_with_code_checks_fills_verified_count_label():
    c = rules.with_code_checks(
        card(),
        {
            ("ipc", "A01M 29/00"): ("corpus", 4, ""),
            ("science_class", "철도교통기술"): ("corpus", 648, ""),
        },
    )
    assert (c.ipc[0].verified, c.ipc[0].count) == ("corpus", 4)
    assert c.ipc[1].verified == "unverified"
    assert (c.science_class[0].verified, c.science_class[0].count) == ("corpus", 648)


def test_card_lines_and_signal_labels_are_korean():
    c = card()
    assert rules.card_lines(c) == {
        "function": "비둘기의 침입을 막는다",
        "cause": "출입구가 열려 침입 경로가 남음",
        "contradiction": "비둘기 침입 방지 ↔ 미관과 유지관리",
        "codes": "A01M 29/00 · E04H 1/12 · 철도교통기술 · 건설·교통",
    }
    labels = rules.signal_labels(c)
    assert labels[0] == {"signal": "unclear_cause", "label": "원인이 뚜렷하지 않거나 여러 가지"}
    assert all(not x["label"].isascii() for x in labels)
    counts = rules.basis_counts(c)
    assert counts[BASIS_STATED] + counts[BASIS_GUESSED] >= 8
