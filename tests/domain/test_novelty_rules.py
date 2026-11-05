"""새 과제 추천 갈래 — 새로움 확인·유추 검색 규칙 (ADR 0057, domain/rules/novelty)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.live_search import LiveSearchConfig, LiveSourceConfig
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.novelty import (
    LiveWidening,
    NoveltyConfig,
    ProblemAxisRule,
    RailFieldRule,
    domain_label,
    input_key,
    is_place_ko,
    pick_new_alerts,
    problem_phrases_en,
    problem_phrases_ko,
    problem_query,
    problem_terms,
    rail_reason,
    shared_terms,
    why_relevant,
)

AXIS = ProblemAxisRule()
RULE = KeywordRule()
RAIL = RailFieldRule()


def _pigeon(**kw) -> ProposalRequest:
    base = {
        "title_hint": "철도역사 비둘기 침입 방지",
        "current_state": "승강장 지붕에 비둘기가 침입해 분변 피해가 크다",
        "root_cause": "역사 구조물에 둥지를 틀기 쉽다",
        "limitation": "그물 설치만으로는 퇴치 효과가 짧다",
        "goal": "비둘기 침입을 막는 퇴치 기술",
    }
    return ProposalRequest(**{**base, **kw})


def _doc(doc_id: str, title: str, **kw) -> Document:
    base = {"source": doc_id.split(":")[0], "doc_type": "paper", "title": title}
    return Document(doc_id=doc_id, **{**base, **kw})


def _alert(doc_id: str, *, blocking: bool, merged=(), rule_blocking=None) -> OverlapAlert:
    return OverlapAlert(
        doc_id=doc_id,
        title=doc_id,
        tier="national_rnd",
        similarity=0.9,
        blocking=blocking,
        rule_blocking=rule_blocking,
        merged_ids=list(merged),
    )


# ── '문제' 축 ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "token,place",
    [
        ("철도역사", True),  # 철도 + 역사
        ("승강장에", True),  # 조사 뗌
        ("역사", True),
        ("철도역사내", True),
        ("역사적", False),  # "역사" + "적" — 장소 말만으로 이루어지지 않음
        ("역량", False),
        ("비둘기", False),
        ("침입", False),
    ],
)
def test_is_place_ko(token, place):
    assert is_place_ko(token, AXIS) is place


def test_problem_terms_drop_place_and_target_keep_problem():
    terms = problem_terms(_pigeon(), RULE, AXIS)
    assert terms[:3] == ["비둘기", "침입", "방지"]
    for place in ("철도역사", "역사", "승강장", "철도", "지붕"):
        assert place not in terms
    assert "침입해" not in terms  # 활용형은 앞 문제어로 충분


def test_problem_terms_core_keywords_first_and_stripped():
    terms = problem_terms(_pigeon(), RULE, AXIS, ["철도역사 비둘기 퇴치", "승강장 조류 침입 방지"])
    assert terms[:5] == ["비둘기", "퇴치", "조류", "침입", "방지"]
    assert len(terms) <= AXIS.max_terms


def test_problem_phrases_and_query_have_no_place_words():
    core = ["철도역사 비둘기 퇴치", "승강장 조류 침입 방지"]
    terms = problem_terms(_pigeon(), RULE, AXIS, core)
    ko = problem_phrases_ko(core, terms, AXIS, RULE)
    assert ko == ["비둘기 퇴치", "조류 침입 방지", "비둘기"]
    en = problem_phrases_en(
        ["pigeon deterrent railway station", "Bird intrusion at platforms"], AXIS
    )
    assert en == ["pigeon deterrent", "bird intrusion"]
    query = problem_query(terms, en)
    for word in ("철도", "역사", "승강장", "railway", "station"):
        assert word not in query
    assert "비둘기" in query and "pigeon deterrent" in query


def test_problem_terms_empty_when_only_places():
    req = _pigeon(
        title_hint="철도역사 승강장",
        current_state="승강장",
        root_cause="역사",
        limitation="철도",
        goal="철도역사",
    )
    assert problem_terms(req, RULE, AXIS) == []


# ── 철도 분야 판정 ─────────────────────────────────────────
@pytest.mark.parametrize(
    "doc,reason",
    [
        (_doc("own:1", "비둘기 퇴치"), "source"),
        (_doc("ntis:1", "조류 퇴치 장치", orgs=["korail"]), "orgs"),
        (_doc("openalex:W1", "Bird deterrent", raw={"field": "역사"}), "corpus_field"),
        (_doc("scienceon:1", "도시철도 승강장 조류 피해"), "terms"),
        (_doc("openalex:W2", "Pigeon control at rail stations"), "terms"),
        (_doc("scienceon:2", "조류 퇴치", raw={"keywords": ["철도차량"]}), "terms"),
        (_doc("ntis:2", "조류 퇴치", raw={"science_class": "교통/물류 | 철도"}), "terms"),
        (
            _doc("openalex:W3", "Bird deterrent", abstract="We study railway bird nests."),
            "abstract",
        ),
        (_doc("openalex:W4", "Bird strike prevention at airports"), None),
        (_doc("scienceon:3", "역사적 건축물의 조류 피해 방지"), None),  # 역사(history) ≠ 철도
        (_doc("openalex:W5", "Training birds", abstract="A train of thought"), None),
    ],
)
def test_rail_reason(doc, reason):
    assert rail_reason(doc, RAIL) == reason


def test_rail_rule_configurable():
    rule = RailFieldRule(sources=(), orgs=())
    assert rail_reason(_doc("own:1", "비둘기 퇴치"), rule) is None


# ── 분야 이름·이유 ─────────────────────────────────────────
def test_domain_label_from_metadata_only():
    assert domain_label(_doc("scienceon:1", "x", raw={"journal": "한국조류학회지"})) == (
        "학술지 한국조류학회지"
    )
    assert domain_label(_doc("openalex:W1", "x", raw={"venue": "Wildlife Society\nBulletin"})) == (
        "게재처 Wildlife Society Bulletin"
    )
    ntis = _doc("ntis:1", "x", doc_type="rnd_project", raw={"science_class": "농림수산식품 | 축산"})
    assert domain_label(ntis) == "과학기술표준분류 농림수산식품"
    patent = _doc("kipris_kr:1", "x", doc_type="patent", codes=["A01M-029/00"])
    assert domain_label(patent) == "특허 분류 A01M (생활필수품)"
    ministry = _doc("ntis:2", "x", doc_type="rnd_project", raw={"ministry": "환경부"})
    assert domain_label(ministry) == "소관 부처 환경부"
    # 메타데이터가 없으면 자료원 이름 — 지어내지 않는다
    assert domain_label(_doc("openalex:W2", "x")) == "OpenAlex 해외 논문"
    assert domain_label(_doc("scienceon:2", "x", raw={"journal": "  "})) == (
        "ScienceON 국내 논문·보고서"
    )


def test_why_relevant_is_rule_sentence():
    assert why_relevant(["침입", "방지"], 0.83) == "철도 밖에서 같은 문제(침입·방지)를 다룬 자료"
    assert why_relevant([], 0.8123) == "철도 밖 자료 — 문제 축 질의와 의미 유사도 0.81"


def test_shared_terms_prefix_and_english():
    doc = _doc("openalex:W1", "Pigeons and bird intrusion", abstract="deterrents reduce damage")
    assert shared_terms(["침입"], ["pigeon", "deterrent", "intrusion"], doc) == [
        "pigeon",
        "deterrent",
        "intrusion",
    ]
    ko = _doc("scienceon:1", "공항 조류 침입을 막는 퇴치 장치")
    assert shared_terms(["비둘기", "침입", "퇴치"], [], ko) == ["침입", "퇴치"]


# ── 새로움 확인 ───────────────────────────────────────────
def test_pick_new_alerts_only_new_blocking_rows():
    original = [_alert("ntis:A", blocking=False, merged=["ntis:A2"])]
    rows = [
        _alert("ntis:A", blocking=True),  # 원래 있던 행
        _alert("ntis:A2", blocking=True),  # 원래 행에 묶인 판
        _alert("ntis:B", blocking=True),  # 새로 걸림
        _alert("ntis:C", blocking=False),  # 근접 — 유사 과제 아님
        _alert("ntis:D", blocking=False, rule_blocking=True),  # 규칙 차단(AI 전 값) 기준
        _alert("ntis:E", blocking=True, merged=["ntis:A"]),  # 원래 행과 묶임
    ]
    assert [a.doc_id for a in pick_new_alerts(rows, original)] == ["ntis:B", "ntis:D"]


def test_input_key_stable_and_sensitive():
    a = input_key(_pigeon(), ["b", "a"], ["x"])
    assert a == input_key(_pigeon(), ["a", "b"], ["x"])  # 순서 무관
    assert a != input_key(_pigeon(), ["a", "b"], ["y"])
    assert a != input_key(_pigeon(goal="다른 목표"), ["a", "b"], ["x"])
    assert len(a) == 64


# ── 설정 ───────────────────────────────────────────────────
def test_live_widening_overrides_but_keeps_base_off():
    base = LiveSearchConfig(enabled=True, cache_hours=24)
    wide = LiveWidening(
        max_queries=5, wait_seconds=30, sources={"ntis": LiveSourceConfig(top_n=50)}
    ).live_config(base)
    assert wide.enabled and wide.max_queries == 5 and wide.wait_seconds == 30
    assert wide.source("ntis").top_n == 50 and wide.source("scienceon").top_n == 30
    assert wide.cache_hours == 24
    off = LiveWidening().live_config(LiveSearchConfig(enabled=False))
    assert off.enabled is False  # 가짜 모드(기존 설정 꺼짐)면 꺼진 채
    assert LiveWidening(enabled=False).live_config(base).enabled is False


def test_novelty_config_rejects_unknown_nested_keys():
    with pytest.raises(ValidationError):
        NoveltyConfig.model_validate({"analogy": {"axis": {"unknown": 1}}})
    cfg = NoveltyConfig()
    assert cfg.analogy.max_results == 5 and cfg.novelty.live.max_queries == 5


def test_relevance_floor_not_in_novelty_config():
    """관련도 하한은 overlap.yaml evidence_floor 하나 — novelty 설정에 따로 두지 않는다."""
    assert "min_similarity" not in NoveltyConfig().analogy.model_dump()
