"""정책 문구 고르기·policy_basis 반영 (순수). 자동 삽입 없음 — apply 는 제안자가 고른 뒤에만."""

from rra.domain.models import PolicySuggestion, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.policy_phrases import (
    apply_policy_suggestion,
    clean_quote,
    match_text,
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


def test_pick_quote_never_cuts_a_sentence():
    """300자를 넘는 문장은 자르지 않고 빼고, 맞는 문장이 없으면 빈 인용 (2026-10-28 레인 B)."""
    long = "가" * 400 + "."
    assert pick_quote(long, "질의") == ("", [])
    quote, _ = pick_quote(long + " 짧은 정책 문장으로 유지보수를 강화함.", "유지보수")
    assert quote == "짧은 정책 문장으로 유지보수를 강화함."


def test_pick_quote_strips_urls_and_leading_bullets():
    text = (
        "O 이에 상태기반 유지보수 체계를 확대함 "
        "(https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=1) "
        "○ 둘째 과제는 데이터 기반 유지보수 첨단화 추진임. ? 셋째 과제는 홍보 강화"
    )
    quote, hits = pick_quote(text, "상태기반 유지보수")
    assert quote == "상태기반 유지보수 체계를 확대함" and "http" not in quote
    for raw, want in [
        ("□ (1) 국가철도망 구축계획 반영함", "국가철도망 구축계획 반영함"),
        ("- 2. 철도안전 종합계획 이행", "철도안전 종합계획 이행"),
        ("? 노후 시설 개량을 추진함", "노후 시설 개량을 추진함"),
    ]:
        assert clean_quote(raw) == want
    # 청크 끝에서 잘린 조각은 고르지 않는다
    q2, _ = pick_quote(
        "첫 문장은 유지보수 확대 계획임. 둘째 문장은 유지보수 데이터 체계를 구", "유지보수 데이터"
    )
    assert q2 == "첫 문장은 유지보수 확대 계획임."


def test_match_text_ignores_urls_for_source_check():
    assert match_text("상태 (https://a.b/c?x=1) 확인") == match_text("상태 확인")


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
