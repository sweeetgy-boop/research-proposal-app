"""레인 E 순수 규칙 — 4축 분해(규칙·파서)·IDF 가중·동의어 선별·facet_overlap 파싱 (ADR 0059)."""

from __future__ import annotations

from rra.domain.models import OverlapAlert
from rra.domain.models.facets import FacetOverlap, Facets
from rra.domain.rules.facets import facet_of, facet_queries, parse_facets, split_by_rule
from rra.domain.rules.idf import (
    IdfWeights,
    compute_idf,
    enough_weighted,
    mean_weight,
    weighted_overlap,
)
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.same_judgment import apply_verdicts, parse_facet_overlaps
from rra.domain.rules.synonyms import (
    SynonymConfig,
    TermStatRow,
    expand_terms,
    high_confidence,
    select_synonyms,
)

RULE = KeywordRule()


# ── 4축 규칙 분해 ────────────────────────────────────────
def test_facet_of_prefers_problem_then_place_method_target():
    assert facet_of("궤도틀림") == "problem"
    assert facet_of("궤도") == "target"
    assert facet_of("수도권") == "place" and facet_of("경부선") == "place"
    assert facet_of("지상역") == "place" and facet_of("영역") == "problem"
    assert facet_of("센서") == "method" and facet_of("딥러닝") == "method"
    assert facet_of("차축베어링") == "target" and facet_of("비둘기") == "target"
    assert facet_of("민원") == "problem" and facet_of("낯선말") == "problem"


def test_split_by_rule_assigns_core_keywords_and_falls_back_to_query():
    f = split_by_rule(
        "경부선 궤도 틀림 상시 감지", ["운행 차량 탑재 센서", "궤도 틀림", "경부선 구간"], RULE
    )
    assert f.source == "rule"
    assert "차량" in f.target and "궤도" in f.target
    assert "틀림" in f.problem and "탑재" in f.problem  # 사전에 없는 말은 problem
    assert f.method == "센서" and "경부선" in f.place and "구간" in f.place
    g = split_by_rule("승강장 캐노피 비둘기 퇴치", None, RULE)
    assert g.source == "rule" and "캐노피" in g.target and "퇴치" in g.method
    assert split_by_rule("", None, RULE).source == "none"


def test_parse_facets_accepts_only_four_string_axes_within_80_chars():
    ok = parse_facets({"facets": {"target": " a  b ", "problem": "", "method": "m", "place": ""}})
    assert ok is not None and ok.source == "local" and ok.target == "a b"
    assert parse_facets({"target": "t", "problem": "p", "method": "m", "place": ""}) is not None
    assert parse_facets({"facets": {"target": "t"}}) is None  # 축 4개 아님
    assert parse_facets({"facets": {"target": 1, "problem": "", "method": "", "place": ""}}) is None
    long = "가" * 81
    assert (
        parse_facets({"facets": {"target": long, "problem": "", "method": "", "place": ""}}) is None
    )
    assert (
        parse_facets({"facets": {"target": "", "problem": "", "method": "", "place": ""}}) is None
    )
    assert parse_facets(None) is None and parse_facets(["x"]) is None  # type: ignore[arg-type]


def test_facet_queries_needs_at_least_two_axes():
    assert facet_queries(None) == []
    assert facet_queries(Facets(target="a")) == []
    assert facet_queries(Facets(target="a", method="m")) == ["a", "m"]
    assert facet_queries(Facets(target="a", problem="p", method="m", place="pl")) == [
        "a",
        "p",
        "m",
        "pl",
    ]


# ── IDF ──────────────────────────────────────────────────
def test_compute_idf_and_weights():
    idf = compute_idf([["철도", "궤도"], ["철도", "비둘기"], ["철도"]])
    assert idf.documents == 3 and idf.values["철도"] == 0.0
    assert idf.values["궤도"] == idf.values["비둘기"] == round(__import__("math").log(3), 2)
    assert idf.max_idf == idf.values["궤도"]
    assert idf.weight("철도") == 0.0 and idf.weight("궤도") == 1.0 and idf.weight("없는말") == 1.0
    assert IdfWeights().weight("x") == 1.0  # 빈 표 — 가중 없음
    cut = compute_idf([["a", "b"], ["a"]], min_doc_freq=2)
    assert set(cut.values) == {"a"}


def test_weighted_overlap_and_enough_weighted():
    idf = IdfWeights(values={"철도": 0.1, "비둘기": 4.0, "승강장": 2.0}, documents=10, max_idf=4.0)
    hits = weighted_overlap(["철도", "비둘기", "승강장"], ["철도역", "승강장에서"], idf)
    assert [h for h, _ in hits] == ["철도", "승강장"] and hits[1][1] == 0.5
    terms = ["철도", "비둘기", "승강장"]
    assert round(mean_weight(terms, idf), 4) == round((0.025 + 1.0 + 0.5) / 3, 4)
    # 철도만 겹침(0.025) → 평균 0.508 미만 → 부족, 비둘기 겹침(1.0) → 충분
    assert not enough_weighted([("철도", 0.025)], terms, idf, min_hits=1)
    assert enough_weighted([("비둘기", 1.0)], terms, idf, min_hits=1)
    assert not enough_weighted([], terms, idf, min_hits=1)
    assert enough_weighted([("비둘기", 1.0)], terms, idf, min_hits=1, ratio=1.9)


# ── 동의어 ────────────────────────────────────────────────
def _row(term, df, examples=(), kind="rail"):
    return TermStatRow(term=term, doc_freq=df, examples=tuple(examples), kind=kind)


def test_select_synonyms_seed_groups_and_containment():
    rows = [
        _row("유지보수", 155, ["d1", "d2"]),
        _row("유지관리", 52, ["d2", "d3"]),
        _row("전차선", 28, ["e1"]),  # 씨앗 1개만 → review
        _row("교량", 54, ["b1", "b2"]),
        _row("철도교량", 24, ["b2"]),  # 포함 관계 + 공출현 1 → review
        _row("차량", 149),  # 일반어 → 제외
        _row("과제명", 500),  # 서식어 → 제외
        _row("응용연구", 356, kind="generic"),  # generic 종류 → 제외
    ]
    out = select_synonyms(rows, RULE, SynonymConfig(min_doc_freq=5))
    by = {r.canonical: r for r in out}
    assert by["유지보수"].confidence == "high" and by["유지보수"].variants == (
        "유지보수",
        "유지관리",
    )
    assert by["유지보수"].cooccur == 1 and "보수" in by["유지보수"].missing
    assert by["전차선"].confidence == "review" and by["전차선"].basis == "seed"
    assert by["교량"].confidence == "review" and by["교량"].basis == "contains"
    assert "차량" not in by and "과제명" not in by and "응용연구" not in by
    assert [r.canonical for r in high_confidence(out)] == ["유지보수"]
    assert out[0].confidence == "high"  # high 먼저


def test_expand_terms_is_or_expansion_preserving_order():
    groups = [["유지보수", "유지관리"], ["전차선", "가선"]]
    assert expand_terms(["가선", "궤도"], groups) == ["가선", "전차선", "궤도"]
    assert expand_terms(["궤도"], groups) == ["궤도"]


# ── facet_overlap 파싱·적용 ──────────────────────────────
def test_parse_facet_overlaps_is_optional_and_clamps():
    data = {
        "items": [
            {
                "doc_id": "a",
                "facet_overlap": {"target": 2, "problem": "x", "method": 1.0, "place": 9},
            },
            {"doc_id": "b"},
            {"doc_id": "zzz", "facet_overlap": {"target": 2}},
        ]
    }
    out = parse_facet_overlaps(data, ["a", "b"])
    assert set(out) == {"a"} and out["a"].as_dict() == {
        "target": 2,
        "problem": 0,
        "method": 1,
        "place": 0,
    }
    assert (
        parse_facet_overlaps({"items": "no"}, ["a"]) == {} and parse_facet_overlaps(None, []) == {}
    )
    assert FacetOverlap(target=2, problem=2, method=2, place=2).all_high()


def test_apply_verdicts_attaches_facet_overlap_without_changing_blocking():
    a = OverlapAlert(doc_id="a", title="t", tier="own", similarity=0.9, blocking=True)
    b = OverlapAlert(doc_id="b", title="t", tier="own", similarity=0.9, blocking=True)
    fo = {"a": FacetOverlap(target=2, problem=1)}
    out = apply_verdicts([a, b], {"a": ("partial", ""), "b": ("same", "")}, ["a", "b"], "argon", fo)
    by = {x.doc_id: x for x in out}
    assert by["a"].facet_overlap == fo["a"] and not by["a"].blocking
    assert by["b"].facet_overlap is None and by["b"].blocking
    plain = apply_verdicts([a, b], {"a": ("partial", ""), "b": ("same", "")}, ["a", "b"], "argon")
    assert all(x.facet_overlap is None for x in plain)
