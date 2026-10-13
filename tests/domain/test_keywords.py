"""유사과제 차단의 키워드 조건 — 조사 차이를 넘어 일치하고, 일반어만 겹치면 세지 않는다."""

import pytest

from rra.domain.rules.keywords import (
    DEFAULT_GENERIC_TERMS,
    KeywordRule,
    enough,
    keyword_overlap,
    query_keywords,
    stem,
    tokens,
)

RULE = KeywordRule()


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("자산개발을", "자산개발"),
        ("자산개발의", "자산개발"),
        ("자산개발", "자산개발"),
        ("유휴부지에서는", "유휴부지"),
        ("타당성으로", "타당성"),
        ("매각이며", "매각"),
        ("평가", "평가"),  # 떼면 1자 — 떼지 않는다
        ("비교", "비교"),
        ("참고", "참고"),
    ],
)
def test_particles_are_stripped_but_short_nouns_survive(word, expected):
    assert stem(word) == expected


@pytest.mark.parametrize("variant", ["자산개발을", "자산개발의", "자산개발", "자산개발에서는"])
def test_query_particle_variants_match_document(variant):
    doc = "철도공사 자산개발 현황 분석 및 유휴부지 활용"
    assert "자산개발" in keyword_overlap(f"{variant} 다각화 모델", doc, RULE)


@pytest.mark.parametrize("doc_form", ["자산개발을", "자산개발의", "자산개발", "자산개발사업"])
def test_document_particle_variants_match_query(doc_form):
    assert keyword_overlap("자산개발 다각화", f"공사의 {doc_form} 탈피", RULE) == ["자산개발"]


def test_tokens_follow_unicode61_boundaries_and_lowercase():
    got = tokens("Track-Geometry(궤도) 틀림, 2026년")
    assert got == ["track", "geometry", "궤도", "틀림", "2026년"]


def test_generic_terms_numbers_and_short_tokens_are_not_keywords():
    q = "철도 시스템 개선 연구 2030 및 궤도 틀림 열화"
    assert query_keywords(q, RULE) == ["궤도", "틀림", "열화"]
    assert "철도" in DEFAULT_GENERIC_TERMS


def test_only_generic_overlap_is_not_enough():
    doc = "철도 안전 개선을 위한 시스템 연구 방안 분석"
    rule = RULE.with_extra_generic(["안전"])
    hits = keyword_overlap("철도 시스템 안전 개선 방안 궤도 틀림", doc, rule)
    assert hits == [] and not enough(hits, rule)


def test_extra_generic_terms_are_stemmed_and_lowercased():
    rule = RULE.with_extra_generic([" Data를 ", "노선의"])
    assert {"data", "노선"} <= rule.generic_terms
    assert "노선" not in query_keywords("노선 궤도", rule)


def test_min_hits_gate():
    assert enough(["자산개발"], KeywordRule(min_hits=1))
    assert not enough(["자산개발"], KeywordRule(min_hits=2))
    assert enough(["자산개발", "유휴부지"], KeywordRule(min_hits=2))
