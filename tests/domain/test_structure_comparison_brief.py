"""U2·U4·U5 순수 규칙 — 구조화 해석·보완 질문·답 합치기, 비교표 추출, 브리핑 검증."""

from __future__ import annotations

from datetime import date

from rra.domain.models import Chunk, Document, OverlapAlert, ProposalRequest
from rra.domain.rules import brief, comparison, structure
from rra.domain.rules.keywords import KeywordRule

TEXT = "궤도 틀림이 자주 생기는데 노반 침하가 원인이고 지금은 임계치만 봐서 열화 예측이 안 됨."


def test_parse_structure_blanks_fields_with_numbers_or_names_not_in_the_text():
    data = {
        "current_state": "궤도 틀림이 자주 생김.",
        "root_cause": "노반 침하 때문임.",
        "limitation": "정확도 95% 수준에 그침.",  # 원문에 없는 수치 → 빈 칸
        "goal": "국가철도망 구축계획에 따라 예측함.",  # 원문에 없는 고유명 → 빈 칸
        "extra": "무시",
    }
    fields = structure.parse_structure(data, [TEXT])
    assert fields["current_state"] == "궤도 틀림이 자주 생김."
    assert fields["limitation"] == "" and fields["goal"] == ""
    assert structure.parse_structure(None, [TEXT]) == {k: "" for k in fields}
    idea = structure.structured(fields)
    assert [q.field for q in idea.questions] == ["limitation", "goal"] and not idea.complete
    assert idea.as_request_fields()["root_cause"] == "노반 침하 때문임."


def test_followup_short_fields_and_cap_at_four():
    qs = structure.followup_questions(
        {"current_state": "짧음", "root_cause": "", "limitation": "", "goal": ""}
    )
    assert len(qs) == 4 and qs[0].reason == "short" and qs[1].reason == "empty"
    assert (
        structure.followup_questions({k: "충분히 긴 설명 문장임." for k in structure.QUESTIONS})
        == []
    )


def test_merge_answers_fills_empty_and_appends_to_existing():
    fields = {"current_state": "궤도 틀림이 잦음.", "root_cause": "", "limitation": "", "goal": ""}
    merged = structure.merge_answers(
        fields, {"root_cause": "노반 침하", "current_state": "주 1회", "x": "y"}
    )
    assert (
        merged["root_cause"] == "노반 침하"
        and merged["current_state"] == "궤도 틀림이 잦음. 주 1회"
    )
    assert structure.structured(merged).questions[0].field == "limitation"


# ── U4 ─────────────────────────────────────────────────
BODY = """■ 연구목적
궤도 상태를 자동으로 감지함. 점검 비용을 줄임.
◦ 연구내용: 센서를 설치함. 데이터를 분석함.
기대효과
점검 주기를 늘림.
"""


def test_section_sentences_by_heading_and_fallback():
    parts = comparison.section_sentences(BODY)
    assert parts["objective"] == ["궤도 상태를 자동으로 감지함.", "점검 비용을 줄임."]
    assert parts["method"] == ["센서를 설치함.", "데이터를 분석함."]
    assert parts["outcome"] == ["점검 주기를 늘림."]
    assert comparison.section_sentences("머리말 없는 글임.") == {}


def test_comparison_table_top5_title_only_and_proposal_side():
    req = ProposalRequest(
        current_state="궤도 틀림",
        root_cause="노반",
        limitation="임계치만",
        goal="열화 예측",
        beneficiaries="시설처",
        differentiation="열화 속도 추정으로 확장",
        title_hint="궤도 열화 예측",
    )
    alerts = [
        OverlapAlert(
            doc_id=f"own:{i}",
            title=f"과제 {i}",
            tier="own",
            similarity=0.9 - i * 0.01,
            blocking=i == 0,
        )
        for i in range(7)
    ]
    docs = {
        "own:0": Document(
            doc_id="own:0", source="own", doc_type="rnd_project", title="과제 0", body=BODY
        ),
        "own:1": Document(doc_id="own:1", source="own", doc_type="rnd_project", title="과제 1"),
        "own:2": Document(
            doc_id="own:2",
            source="own",
            doc_type="rnd_project",
            title="과제 2",
            abstract="머리말 없는 초록임. 둘째 문장임. 셋째.",
        ),
    }
    table = comparison.comparison_table(req, alerts, docs, differentiation=req.differentiation)
    assert [c.doc_id for c in table.projects] == [f"own:{i}" for i in range(5)]
    assert table.projects[0].cells["objective"].startswith("궤도 상태를 자동으로")
    assert (
        table.projects[1].title_only and table.projects[1].cells["method"] == "정보 없음(제목 기준)"
    )
    assert table.projects[2].cells["objective"] == "머리말 없는 초록임. 둘째 문장임."
    assert table.projects[2].cells["method"] == "정보 없음"
    assert table.proposal.cells["differentiation"] == "열화 속도 추정으로 확장"
    assert table.proposal.cells["scope"] == "시설처" and table.proposal.title == "궤도 열화 예측"
    assert [a["key"] for a in table.aspects] == [
        "objective",
        "method",
        "scope",
        "outcome",
        "differentiation",
    ]


# ── U5 ─────────────────────────────────────────────────
def _picked():
    docs = {
        "openalex:W1": Document(
            doc_id="openalex:W1",
            source="openalex",
            doc_type="paper",
            title="Track degradation",
            pub_date=date(2023, 1, 1),
        ),
        "own:1": Document(
            doc_id="own:1",
            source="own",
            doc_type="rnd_project",
            title="궤도 열화 과제",
            pub_date=date(2023, 5, 1),
        ),
        "kipris_kr:1": Document(
            doc_id="kipris_kr:1", source="kipris_kr", doc_type="patent", title="특허"
        ),
        "alio:2": Document(
            doc_id="alio:2", source="alio", doc_type="internal_report", title="보고서"
        ),
    }
    chunks = [
        Chunk(
            chunk_id="openalex:W1#0",
            doc_id="openalex:W1",
            ordinal=0,
            text="degradation rate 12% per year",
        ),
        Chunk(chunk_id="openalex:W1#1", doc_id="openalex:W1", ordinal=1, text="second chunk"),
        Chunk(chunk_id="kipris_kr:1#0", doc_id="kipris_kr:1", ordinal=0, text="patent text"),
        Chunk(chunk_id="own:1#0", doc_id="own:1", ordinal=0, text="궤도 열화 속도를 추정함"),
        Chunk(chunk_id="alio:2#overlap", doc_id="alio:2", ordinal=0, text="x"),
    ]
    return brief.pick_items(chunks, docs), docs


def test_pick_items_one_per_paper_or_report_in_rank_order():
    picked, _ = _picked()
    assert [c.chunk_id for c, _ in picked] == ["openalex:W1#0", "own:1#0"]  # 특허·overlap 제외
    assert brief.year_counts(d for _, d in picked) == {"2023": 2}
    kws = brief.top_keywords(["궤도 열화 속도 추정", "궤도 열화 과제"], KeywordRule())
    assert "궤도" in kws and "열화" in kws


def test_validate_brief_keeps_grounded_summaries_and_gaps_only():
    picked, _ = _picked()
    data = {
        "summaries": [
            {"chunk_id": "openalex:W1#0", "summary": "연간 12% 열화율을 보고함."},
            {"chunk_id": "own:1#0", "summary": "정확도 95% 달성함."},  # 청크에 없는 수치
            {"chunk_id": "nope#0", "summary": "x"},
        ],
        "gaps": [
            {"text": "재래선 자료가 없음.", "evidence": ["openalex:W1#0"]},
            {"text": "근거 없는 공백.", "evidence": ["ntis:9"]},
            {"text": "漢字 섞임.", "evidence": ["own:1#0"]},
        ],
    }
    items, gaps, discarded = brief.validate_brief(data, picked)
    assert items[0].summary == "연간 12% 열화율을 보고함." and not items[0].summary_missing
    assert items[1].summary == "" and items[1].summary_missing
    assert [g.text for g in gaps] == ["재래선 자료가 없음."]
    assert {d["reason"] for d in discarded} == {
        "unsupported_number",
        "evidence_out_of_range",
        "foreign_script",
    }
    items, gaps, _ = brief.validate_brief(None, picked)
    assert all(i.summary_missing for i in items) and gaps == []
