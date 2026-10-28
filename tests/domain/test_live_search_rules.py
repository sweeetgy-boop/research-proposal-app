"""[4] 실시간 자료 검색 규칙 (domain/rules/live_search) — 순수 함수."""

from __future__ import annotations

from datetime import date

from rra.domain.models import Document, ProposalRequest
from rra.domain.models.live_search import (
    LiveKeywords,
    LiveSearchConfig,
    LiveSearchSummary,
    LiveSourceResult,
)
from rra.domain.rules.live_search import (
    cache_key,
    clean_keyword,
    clean_list,
    dedup_live,
    identity_keys,
    keyword_input,
    keywords_from_llm,
    match_existing,
    overall_status,
    prepare_live,
    rule_keywords,
    session_key,
    source_queries,
    top_up,
)


def _req(**kw) -> ProposalRequest:
    base = {
        "title_hint": "열차 운행 지연 예측 모델",
        "current_state": "열차 지연이 반복된다. 담당자 홍길동 010-1234-5678",
        "root_cause": "운행 데이터 분석 부족",
        "limitation": "수작업 분석",
        "goal": "머신러닝 기반 지연 예측",
    }
    return ProposalRequest(**{**base, **kw})


def _doc(doc_id: str, **kw) -> Document:
    base = {"source": doc_id.split(":")[0], "doc_type": "paper", "title": "제목 기본값 열차 지연"}
    return Document(doc_id=doc_id, **{**base, **kw})


def test_clean_keyword_lang_operators_and_personal():
    assert clean_keyword("열차 지연 예측", "ko") == "열차 지연 예측"
    assert clean_keyword("train delay", "ko") is None  # 국문 목록에 한글 없음
    assert clean_keyword("열차 지연", "en") is None
    assert clean_keyword("train delay|track", "en") == "train delay track"  # 연산자 제거
    assert clean_keyword('"delay" OR prediction', "en") == "delay prediction"
    assert clean_keyword("담당자 홍길동", "ko") is None  # 개인정보 섞인 키워드는 버린다
    assert clean_keyword("a@b.com", "en") is None
    assert clean_keyword(123, "ko") is None
    assert clean_keyword("가" * 41, "ko") is None


def test_clean_list_dedup_and_limit():
    out = clean_list(["열차", "열차", "궤도", "신호", "전차선", "역사", "차량", "선로"], "ko")
    assert out == ["열차", "궤도", "신호", "전차선", "역사"]
    assert clean_list("열차", "ko") == []


def test_keywords_from_llm_needs_korean():
    kw = keywords_from_llm(
        {"ko": ["K-철도 2030 전략", "열차 지연"], "en": ["train delay"]}, "argon"
    )
    assert kw is not None and kw.ko[0] == "K-철도 2030 전략"  # 정책명은 그대로
    assert kw.origin == "argon"
    assert keywords_from_llm({"en": ["x"]}, "argon") is None
    assert keywords_from_llm(None, "argon") is None


def test_rule_keywords_strip_personal_and_generic():
    kw = rule_keywords(_req())
    assert kw.origin == "rule"
    assert kw.ko and all("홍길동" not in k for k in kw.ko)
    assert "연구" not in kw.ko  # 일반어 제외
    assert len(kw.ko) <= 5


def test_keyword_input_removes_personal():
    text = keyword_input(_req())
    assert "010-1234-5678" not in text and "홍길동" not in text
    assert "열차 운행 지연 예측 모델" in text


def test_top_up_fills_from_rule():
    primary = LiveKeywords(ko=["열차 지연"], en=["train delay"], origin="argon")
    fallback = LiveKeywords(ko=["지연", "예측", "머신러닝"], en=["ML"], origin="rule")
    out = top_up(primary, fallback)
    assert out.ko == ["열차 지연", "지연", "예측"]
    assert out.en == ["train delay", "ML"]
    assert out.origin == "argon"


def test_source_queries_and_off():
    assert source_queries(["열차 지연", "예측", "모델"]) == ["열차 지연 예측", "열차 지연", "예측"]
    assert source_queries(["하나"]) == ["하나"]
    assert source_queries([]) == []


def test_cache_key_normalized_and_per_source():
    a = cache_key("scienceon", ["열차  지연", "Train"], 30)
    assert a == cache_key("scienceon", ["열차 지연", "train"], 30)
    assert a != cache_key("ntis", ["열차 지연", "train"], 30)
    assert a != cache_key("scienceon", ["열차 지연", "train"], 10)
    assert len(a) == 64


def test_session_key_owner_and_input():
    assert session_key("u1", _req()) == session_key("u1", _req())
    assert session_key("u1", _req()) != session_key("u2", _req())
    assert session_key("u1", _req()) != session_key("u1", _req(goal="다른 목표"))


def test_prepare_live_removes_names_and_marks():
    d = _doc(
        "openalex:W1",
        authors=["Hong Gildong"],
        abstract="Contact hong@example.com for data.",
        visibility="internal",
    )
    out = prepare_live(d, "abc123")
    assert out.authors == []
    assert "hong@example.com" not in (out.abstract or "")
    assert out.visibility == "public"
    assert out.raw["live"] is True and out.raw["live_first_seen"] == "abc123"


def test_dedup_live_across_sources():
    ntis_report = _doc(
        "ntis:R1",
        doc_type="report",
        title="궤도 회로 고장 진단 보고서",
        raw={"project_no": "1415-0001"},
        pub_date=date(2024, 1, 1),
    )
    sci_report = _doc(
        "scienceon:TRKO1",
        doc_type="internal_report",
        title="궤도 회로 고장 진단 보고서",
        raw={"project_no": "14150001"},
        pub_date=date(2024, 5, 1),
    )
    sci_paper = _doc("scienceon:JAKO1", title="Track circuit fault diagnosis", doi="10.1/ABC")
    oa_paper = _doc("openalex:W9", title="Track circuit fault diagnosis!", doi="10.1/abc")
    oa_same_title = _doc("openalex:W8", title="열차 지연 예측 모델 연구", pub_date=date(2023, 1, 1))
    sci_same_title = _doc(
        "scienceon:JAKO2", title="열차 지연 예측 모델 연구", pub_date=date(2023, 6, 1)
    )
    other_year = _doc("openalex:W7", title="열차 지연 예측 모델 연구", pub_date=date(2020, 1, 1))
    kept, alias = dedup_live(
        [ntis_report, sci_report, sci_paper, sci_same_title, oa_paper, oa_same_title, other_year]
    )
    ids = [d.doc_id for d in kept]
    assert ids == ["ntis:R1", "scienceon:JAKO1", "scienceon:JAKO2", "openalex:W7"]
    assert alias == {
        "scienceon:TRKO1": "ntis:R1",
        "openalex:W9": "scienceon:JAKO1",
        "openalex:W8": "scienceon:JAKO2",
    }


def test_projects_never_merge_by_title():
    a = _doc("ntis:P1", doc_type="rnd_project", title="같은 제목의 과제 이름입니다")
    b = _doc("ntis:P2", doc_type="rnd_project", title="같은 제목의 과제 이름입니다")
    kept, alias = dedup_live([a, b])
    assert len(kept) == 2 and alias == {}
    assert identity_keys(a) == ["project:ntis:P1"]


def test_match_existing_against_db():
    stored = [_doc("scienceon:JAKO1", title="Track circuit fault diagnosis", doi="10.1/abc")]
    new = [
        _doc("openalex:W9", title="Different title", doi="10.1/abc"),
        _doc("openalex:W10", title="Unrelated work entirely"),
        _doc("scienceon:JAKO1", title="Track circuit fault diagnosis", doi="10.1/abc"),
    ]
    assert match_existing(new, stored) == {"openalex:W9": "scienceon:JAKO1"}


def test_overall_status():
    ok = LiveSourceResult(source="ntis", status="ok")
    bad = LiveSourceResult(source="openalex", status="timeout")
    off = LiveSourceResult(source="scienceon", status="off")
    assert overall_status([ok, off], finished=True) == "done"
    assert overall_status([ok, bad], finished=True) == "partial"
    assert overall_status([ok], finished=False) == "pending"
    assert overall_status([off], finished=True) == "off"


def test_summary_payload_shape_and_manifest_has_no_text():
    s = LiveSearchSummary(
        status="done",
        keywords=LiveKeywords(ko=["열차 지연"], en=["train delay"], origin="argon"),
        sources=[LiveSourceResult(source="ntis", status="ip_blocked", notice="IP 안내")],
        doc_ids=["ntis:1"],
        session="abc",
    )
    p = s.payload()
    assert set(p) == {"status", "keywords", "sources"}
    assert p["keywords"] == {"ko": ["열차 지연"], "en": ["train delay"]}
    row = p["sources"][0]
    assert {"source", "status", "count", "seconds", "notice"} <= set(row)
    m = s.manifest()
    assert "열차" not in str(m) and m["keywords"] == {"ko": 1, "en": 1}


def test_config_defaults_off():
    cfg = LiveSearchConfig()
    assert cfg.enabled is False
    assert cfg.enabled_sources() == ["scienceon", "ntis", "openalex"]
