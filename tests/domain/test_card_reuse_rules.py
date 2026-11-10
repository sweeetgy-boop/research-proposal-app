"""문제 정의 카드 재사용·고정 키 규칙 (계약 problem-card.md 4.4절)."""

from __future__ import annotations

from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import CardRank
from rra.domain.rules import card_reuse as rules
from rra.domain.rules.card_queries import card_queries, memo_groups, pick_fingerprint
from tests.domain.test_card_queries import IDEA, card

REQ = ProposalRequest(**IDEA)
STAFF = Principal(kind="staff", id="staff:aaaaaaaaaaaa")


def test_text_hash_ignores_spacing_case_and_width_but_not_content():
    same = ProposalRequest(
        **{**IDEA, "goal": "  역사  구조에 맞는 비둘기 침입 방지 방법을 마련함 "}
    )
    other = ProposalRequest(**{**IDEA, "goal": IDEA["goal"] + " 또한 비용을 줄임"})
    assert rules.text_hash(same) == rules.text_hash(REQ)
    assert rules.text_hash(other) != rules.text_hash(REQ)
    # 칸이 바뀌면(같은 글자가 다른 칸에) 다른 입력이다
    swapped = ProposalRequest(
        **{**IDEA, "root_cause": IDEA["limitation"], "limitation": IDEA["root_cause"]}
    )
    assert rules.text_hash(swapped) != rules.text_hash(REQ)


def test_text_hash_does_not_depend_on_card_or_other_form_fields():
    with_card = ProposalRequest(**IDEA, problem_card=card(), policy_basis="철도안전법")
    assert rules.text_hash(with_card) == rules.text_hash(REQ)


def test_cache_key_changes_with_prompt_or_model_and_holds_no_text():
    v1 = rules.prompt_version("지시문 1", "model-a")
    assert rules.cache_key(REQ, v1) == rules.cache_key(
        REQ, rules.prompt_version("지시문 1", "model-a")
    )
    assert rules.cache_key(REQ, v1) != rules.cache_key(
        REQ, rules.prompt_version("지시문 2", "model-a")
    )
    assert rules.cache_key(REQ, v1) != rules.cache_key(
        REQ, rules.prompt_version("지시문 1", "model-b")
    )
    key = rules.cache_key(REQ, v1)
    assert len(key) == 64 and "비둘기" not in key and "지시문" not in v1


def test_pin_key_is_per_user_and_differs_from_cache_key():
    a, b = rules.pin_key("staff:aaaaaaaaaaaa", REQ), rules.pin_key("staff:bbbbbbbbbbbb", REQ)
    assert a != b and len(a) == 64 and "staff" not in a
    assert a != rules.cache_key(REQ, rules.prompt_version("", ""))


def test_guest_and_anonymous_cannot_pin():
    assert rules.can_pin(STAFF) and rules.can_pin(Principal(kind="admin", id="admin"))
    assert rules.can_pin(Principal(kind="staff", id="staff:cccccccccccc", test=True))
    assert not rules.can_pin(Principal(kind="guest", id="guest:demo"))
    assert not rules.can_pin(None)


def test_load_card_rejects_broken_values():
    c = card()
    assert rules.load_card(c.model_dump(mode="json")) == c
    for bad in (None, "x", [], {"function_ko": {"value": "x", "origin": "nobody"}}):
        assert rules.load_card(bad) is None


def test_reuse_keys_are_separate_from_analogy_fingerprints():
    """입력 글 기준 키는 유추 세션·메모 키(보낸 질의 지문, 계약 4.1절)와 재료가 다르다 — 카드를
    고쳐도 입력 글 키는 그대로이고, 질의 지문은 재사용 키와 무관하게 종전 값이다."""
    c = card()
    before = memo_groups(pick_fingerprint(card_queries(c), c, CardRank()))
    key = rules.cache_key(ProposalRequest(**IDEA, problem_card=c), "v")
    assert key == rules.cache_key(REQ, "v")
    assert memo_groups(pick_fingerprint(card_queries(c), c, CardRank())) == before
