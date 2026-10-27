"""용어 후보 규칙 (P2-9) — 문서빈도 통계로 철도 용어·흔한 단어 후보를 나눈다. 후보일 뿐, 반영은
사람."""

from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.term_candidates import (
    CandidateConfig,
    CorpusText,
    rail_hint,
    term_candidates,
)


def corpus():
    base = "본 연구는 철도 안전을 위해 수행한다. "  # 철도·안전·연구·수행·위해 는 모든 문서에
    docs = {
        "alio:1": ("alio", base + "궤도 틀림을 검측차로 측정한다. 궤도의 열화를 예측한다."),
        "alio:2": ("alio", base + "궤도 침목 교체 주기를 분석한다. 분기기 마모도 본다."),
        "own:3": ("own", base + "전차선 마모 예측 모델. 분기기 상태 진단."),
        "own:4": ("own", base + "역사 승강설비 현황과 정비. 침목 재료."),
        "openalex:5": ("openalex", base + "Track geometry monitoring with IMU sensors. 분기기."),
        "korail_web:6": ("korail_web", base + "경영목표와 ESG 경영. 분기기 교체 계획."),
    }
    return [CorpusText(doc_id=d, source=s, text=t) for d, (s, t) in docs.items()]


def test_generic_and_rail_candidates_are_separated_by_document_frequency():
    rule = KeywordRule()  # 기본 일반어: 철도·연구·위해 등은 이미 일반어 → 후보에서 빠진다
    report = term_candidates(corpus(), rule, CandidateConfig(min_doc_freq=2, generic_doc_ratio=0.5))
    assert report.documents == 6 and report.chunks == 6
    assert report.sources == {"alio": 2, "korail_web": 1, "openalex": 1, "own": 2}
    generic = {s.term: s for s in report.generic}
    rail = {s.term: s for s in report.rail}
    assert "철도" not in generic and "철도" not in rail  # 이미 일반어
    assert "안전" in generic and generic["안전"].doc_freq == 6  # 6/6 문서, 자료원 4
    assert "분기기" in generic and generic["분기기"].sources == {
        "alio": 1,
        "korail_web": 1,
        "openalex": 1,
        "own": 1,
    }  # 4/6 ≥ 0.5 — 흔한 말 후보에 들어가도 사람이 보고 되돌린다 (hint 는 그대로 표시)
    assert generic["분기기"].hint == "rail_seed"
    assert "궤도" in rail and rail["궤도"].doc_freq == 2 and rail["궤도"].chunk_freq == 2
    assert rail["궤도"].hint == "rail_seed" and rail["궤도"].score == 4.0
    assert rail["궤도"].examples == ["alio:1", "alio:2"] and rail["궤도"].sources == {"alio": 2}
    assert "침목" in rail and rail["침목"].sources == {"alio": 1, "own": 1}
    assert "track" not in rail and "imu" not in rail  # 라틴 토큰은 세지 않는다
    assert "마모" in rail and rail["마모"].hint is None  # "마모도" 의 조사 제거
    # 철도 어근이 있는 후보가 앞에 온다
    assert [s.term for s in report.rail][:1] == ["궤도"] or report.rail[0].hint == "rail_seed"


def test_extra_generic_terms_and_min_doc_freq_filter():
    rule = KeywordRule().with_extra_generic(["안전", "예측"])
    report = term_candidates(corpus(), rule, CandidateConfig(min_doc_freq=3, generic_doc_ratio=0.9))
    terms = {s.term for s in report.rail} | {s.term for s in report.generic}
    assert "안전" not in terms and "예측" not in terms
    assert "궤도" not in terms  # df 2 < 3
    assert "분기기" in terms and all(len(t) >= 2 for t in terms)


def test_limit_and_empty_corpus():
    report = term_candidates([], KeywordRule())
    assert report.documents == 0 and report.rail == [] and report.generic == []
    report = term_candidates(corpus(), KeywordRule(), CandidateConfig(min_doc_freq=1, limit=2))
    assert len(report.rail) == 2 and len(report.generic) <= 2


def test_rail_hint_uses_seed_morphemes():
    assert rail_hint("전차선") == "rail_seed" and rail_hint("승강설비") is None
