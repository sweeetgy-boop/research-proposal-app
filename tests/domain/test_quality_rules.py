"""[Q] 순수 규칙 — Q4 본보기(exemplars), Q3 섹션 질의(section_search), Q2 설계도 검증(outline)."""

from rra.domain.models import Document, ProposalRequest
from rra.domain.models.outline import Outline, SectionPlan
from rra.domain.rules.exemplars import eligible, exemplar_ids, pick_exemplars, section_sentences
from rra.domain.rules.outline import (
    DISCARD_EVIDENCE,
    DISCARD_FOREIGN,
    DISCARD_UNKNOWN_SECTION,
    validate_outline,
)
from rra.domain.rules.section_search import SECTION_FIELDS, section_queries

SUMMARY = (
    "연구목적: 궤도 틀림을 예측함. 보수 주기를 정함.\n"
    "연구내용: 검측 이력을 분석함. 열화 모형을 만듦. 셋째 문장임.\n"
    "기대효과: 보수 비용을 줄임.\n"
    "비고: 무시"
)


def doc(doc_id="own:1", status="completed", visibility="public", body=SUMMARY, basis="summary"):
    return Document(
        doc_id=doc_id,
        source="own",
        doc_type="internal_report",
        title="궤도 틀림 예측",
        body=body,
        orgs=["korail"],
        text_basis=basis,
        visibility=visibility,
        raw={"status": status},
    )


# ── Q4 본보기 ──────────────────────────────────────────────
def test_section_sentences_split_by_heading_and_cap_per_section():
    out = section_sentences(doc(), per_section=2)
    assert out["objective"] == ["궤도 틀림을 예측함.", "보수 주기를 정함."]
    assert out["method"] == ["검측 이력을 분석함.", "열화 모형을 만듦."]  # 2개 상한
    assert out["expected_management"] == ["보수 비용을 줄임."]
    assert "비고" not in str(out)


def test_pick_exemplars_filters_status_visibility_exclusion_and_limit():
    hits = [
        (doc("own:x", status="rejected", basis="full_text"), 0.95),  # 채택 안 됨
        (doc("own:i", visibility="internal"), 0.94),  # 사내 전용 → 제외
        (doc("own:g"), 0.93),  # 골든셋 정답 → 제외
        (doc("own:a"), 0.92),
        (doc("own:b", status="ongoing"), 0.91),
        (doc("own:c"), 0.90),  # limit 2 로 잘림
        (doc("own:e", body="항목 머리 없음"), 0.89),
    ]
    picked = pick_exemplars(hits, limit=2, exclude={"own:g"})
    assert [p["doc_id"] for p in picked] == ["own:a", "own:b"]
    assert picked[0]["status"] == "completed" and picked[0]["similarity"] == 0.92
    assert set(picked[0]["sections"]) == {"objective", "method", "expected_management"}
    assert exemplar_ids(picked) == {"own:a", "own:b"}
    assert not eligible(doc(status="", basis="full_text")) and eligible(
        doc(status="", basis="summary")
    )


# ── Q3 섹션 질의 ──────────────────────────────────────────
def test_section_queries_use_section_fields_plus_outline_message_and_cap_length():
    req = ProposalRequest(
        current_state="현황",
        root_cause="원인",
        limitation="한계",
        goal="목표",
        title_hint="가제",
        beneficiaries="시설처",
    )
    outline = Outline(sections=[SectionPlan(key="method", message="이력 분석으로 열화 모형")])
    q = section_queries(req, ["title", "task_type", "method", "utilization", "objective"], outline)
    assert set(q) == {"method", "utilization", "objective"}  # 제목·선택형은 전체 근거를 쓴다
    assert q["method"] == "이력 분석으로 열화 모형 가제 목표"
    assert q["utilization"] == "가제 목표 시설처" and "시설처" not in q["objective"]
    long = req.model_copy(update={"goal": "목표 " * 300})
    assert len(section_queries(long, ["objective"])["objective"]) <= 500
    assert set(SECTION_FIELDS) >= {"tech_importance", "expected_management"}


def test_section_queries_skip_sections_whose_fields_are_all_empty():
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    assert "expected_standing" in section_queries(req, ["expected_standing"])
    bare = req.model_copy(update={"goal": "", "title_hint": ""})
    assert section_queries(bare, ["expected_standing"]) == {}


# ── Q2 설계도 검증 ────────────────────────────────────────
def test_validate_outline_keeps_known_sections_in_form_order_and_discards_bad_ones():
    data = {
        "sections": {
            "method": {
                "message": "이력 분석",
                "evidence": ["openalex:W1#0"],
                "links": ["objective", "zzz"],
            },
            "objective": {"message": "예측", "evidence": ["openalex:W9"]},  # 검색 밖 근거
            "title": {"message": "日本語"},  # 외국 문자
            "bogus": {"message": "x"},
            "utilization": {"message": ""},
        }
    }
    outline, errors = validate_outline(
        data,
        section_keys=["title", "objective", "method", "utilization"],
        allowed_ids={"openalex:W1#0"},
    )
    assert errors == [] and [s.key for s in outline.sections] == ["method"]
    assert outline.sections[0].links == ["objective"]
    reasons = {d["key"]: d["reason"] for d in outline.discarded}
    assert reasons["objective"] == DISCARD_EVIDENCE and reasons["title"] == DISCARD_FOREIGN
    assert reasons["bogus"] == DISCARD_UNKNOWN_SECTION and "utilization" in reasons
    assert outline.summary_text() == "method: 이력 분석"


def test_validate_outline_accepts_list_form_and_reports_empty_result():
    outline, errors = validate_outline(
        {"sections": [{"key": "method", "message": "m", "evidence": "openalex:W1"}]},
        section_keys=["method"],
        allowed_ids={"openalex:W1"},
    )
    assert not errors and outline.plan("method").evidence == ["openalex:W1"]
    _, errors = validate_outline({"sections": []}, section_keys=["method"], allowed_ids=set())
    assert errors
