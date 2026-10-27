"""정책 문구 고르기·policy_basis 반영 (순수). 자동 삽입 없음 — apply 는 제안자가 고른 뒤에만."""

from rra.domain.models import PolicySuggestion, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.policy_phrases import (
    apply_policy_suggestion,
    pick_quote,
    policy_basis_text,
    rank,
)

TEXT = (
    "경영목표는 다섯 가지다. "
    "데이터기반 유지보수 첨단화로 차량·철도시설 상태기반의 유지보수체계를 확립한다. "
    "국민공감 소통·홍보를 강화한다."
)


def test_pick_quote_prefers_sentence_with_most_query_keywords():
    quote, hits = pick_quote(TEXT, "궤도 상태기반 유지보수 체계 자동 감지", KeywordRule(min_hits=1))
    assert quote.startswith("데이터기반 유지보수 첨단화")
    assert "유지보수" in hits
    quote2, hits2 = pick_quote(TEXT, "전혀 다른 질의", KeywordRule())
    assert quote2 == "경영목표는 다섯 가지다." and hits2 == []


def test_pick_quote_caps_length():
    long = "가" * 400 + "."
    quote, _ = pick_quote(long, "질의")
    assert len(quote) == 300 and quote.endswith("…")


def _s(doc_id, hits, sim=None, **kw):
    return PolicySuggestion(
        doc_id=doc_id,
        title=kw.get("title", "중장기 경영목표"),
        quote="q",
        keywords=hits,
        similarity=sim,
        **{k: v for k, v in kw.items() if k != "title"},
    )


def test_rank_by_keywords_then_similarity_one_per_document_max_five():
    items = [
        _s("a", ["x"], 0.9),
        _s("a", ["x", "y"], 0.5),
        _s("b", [], 0.95),
        _s("c", ["x"], 0.8),
        _s("d", ["x"], 0.7),
        _s("e", ["x"], 0.6),
        _s("f", ["x"], 0.5),
        _s("g", ["x"], 0.4),
    ]
    ranked = rank(items)
    assert [s.doc_id for s in ranked] == ["a", "c", "d", "e", "f"]
    assert ranked[0].keywords == ["x", "y"]


def test_policy_basis_text_and_apply_keeps_existing_input():
    s = PolicySuggestion(
        doc_id="korail_web:1",
        title="중장기 경영목표",
        year=2026,
        page="표 ‘전략목표 및 과제종합’",
        quote="데이터기반 유지보수 첨단화",
        url="https://info.korail.com/info/contents.do?key=1900",
    )
    line = policy_basis_text(s)
    assert line == (
        "“데이터기반 유지보수 첨단화” (중장기 경영목표, 2026, 표 ‘전략목표 및 과제종합’, "
        "https://info.korail.com/info/contents.do?key=1900)"
    )
    req = ProposalRequest(
        current_state="a", root_cause="b", limitation="c", goal="d", policy_basis="기존 근거"
    )
    out = apply_policy_suggestion(req, s)
    assert out.policy_basis == "기존 근거\n" + line and req.policy_basis == "기존 근거"
    assert (
        apply_policy_suggestion(req.model_copy(update={"policy_basis": ""}), s).policy_basis == line
    )
