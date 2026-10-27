"""U1·U3·U6·U8 순수 규칙 — 근거 판단·적합성, 다시 쓰기 합치기·체크리스트, 일정, usage 집계."""

from __future__ import annotations

import pytest

from rra.domain.models import (
    Draft,
    EvidenceCounts,
    ProposalRequest,
    RunState,
    Satisfaction,
    Section,
    Sentence,
    StepRecord,
    UsageRecord,
)
from rra.domain.models.review import EvidenceDecision
from rra.domain.rules import checklist, evidence, rewrite, schedule, usage

REQ = ProposalRequest(
    current_state="궤도 틀림",
    root_cause="노반",
    limitation="임계치",
    goal="예측",
    constraints="연구기간 2년",
)


def _section(key="method", origins=("llm", "proposer_edit", "llm")):
    return Section(
        key=key,
        sentences=[
            Sentence(
                text=f"문장 {i}임.",
                evidence=[f"openalex:W{i}#0"] if o != "proposer_edit" else [],
                origin=o,
            )
            for i, o in enumerate(origins)
        ],
    )


# ── U1 ─────────────────────────────────────────────────
def test_basis_labels_and_needs_check():
    assert evidence.basis_label("summary") == "공개 요약"
    assert evidence.basis_label(None) == "미상"
    assert evidence.needs_check("summary") and evidence.needs_check("image_vision")
    assert not evidence.needs_check("full_text") and not evidence.needs_check("abstract")


def test_parse_support_keeps_only_sent_ids_and_allowed_values():
    raw = [
        {"sentence_id": "s:method:0", "support": "지지"},
        {"sentence_id": "s:method:0", "support": "불일치"},  # 같은 문장 두 번째는 무시
        {"sentence_id": "s:method:9", "support": "지지"},  # 보내지 않은 문장
        {"sentence_id": "s:method:1", "support": "maybe"},  # 허용 밖 값
        "junk",
    ]
    assert evidence.parse_support(raw, {"s:method:0", "s:method:1"}) == {"s:method:0": "지지"}
    assert evidence.parse_support("not a list", set()) == {}


def test_support_mismatch_becomes_a_sentence_warning():
    sec = _section()
    problems = evidence.support_problems([sec], {"s:method:2": "불일치", "s:method:0": "부분"})
    assert [(p.code, p.sentence, p.severity) for p in problems] == [
        ("evidence_mismatch", 2, "warning")
    ]


def test_apply_decisions_replace_only_within_snapshot_and_exclude_keeps_evidence():
    sec = _section()
    allowed = {"openalex:W0#0", "openalex:W2#0", "alio:1#0", "alio:1"}
    decisions = [
        EvidenceDecision(sentence_id="s:method:0", evidence_id="openalex:W0#0", action="approve"),
        EvidenceDecision(
            sentence_id="s:method:2",
            evidence_id="openalex:W2#0",
            action="replace",
            replacement="alio:1#0",
        ),
    ]
    sections, merged = evidence.apply_decisions([sec], [], decisions, allowed)
    assert sections[0].sentences[2].evidence == ["alio:1#0"]
    assert {(d.sentence_id, d.evidence_id, d.action) for d in merged} == {
        ("s:method:0", "openalex:W0#0", "approve"),
        ("s:method:2", "alio:1#0", "approve"),
    }
    sections, merged = evidence.apply_decisions(
        sections,
        merged,
        [EvidenceDecision(sentence_id="s:method:0", evidence_id="openalex:W0#0", action="exclude")],
        allowed,
    )
    assert sections[0].sentences[0].evidence == ["openalex:W0#0"]  # 제외해도 근거는 남는다
    assert {d.action for d in merged if d.sentence_id == "s:method:0"} == {"exclude"}
    with pytest.raises(evidence.DecisionRejected, match="검색 집합"):
        evidence.apply_decisions(
            [sec],
            [],
            [
                EvidenceDecision(
                    sentence_id="s:method:0",
                    evidence_id="openalex:W0#0",
                    action="replace",
                    replacement="ntis:none#0",
                )
            ],
            allowed,
        )
    with pytest.raises(evidence.DecisionRejected, match="근거가 아닙니다"):
        evidence.apply_decisions(
            [sec],
            [],
            [EvidenceDecision(sentence_id="s:method:0", evidence_id="alio:1", action="approve")],
            allowed,
        )
    with pytest.raises(evidence.DecisionRejected, match="그런 문장"):
        evidence.apply_decisions(
            [sec],
            [],
            [EvidenceDecision(sentence_id="s:method:7", evidence_id="x", action="approve")],
            allowed,
        )


def test_all_excluded_in_evidence_required_section_is_a_warning_and_counts():
    sec = _section("tech_importance", ("llm", "app"))
    decisions = [
        EvidenceDecision(
            sentence_id="s:tech_importance:0", evidence_id="openalex:W0#0", action="exclude"
        )
    ]
    problems = evidence.exclusion_problems([sec], decisions, ["tech_importance"])
    assert [(p.code, p.sentence) for p in problems] == [("evidence_all_excluded", 0)]
    assert evidence.exclusion_problems([sec], decisions, ["method"]) == []
    assert evidence.evidence_counts([sec], decisions) == {
        "approve": 0,
        "replace": 0,
        "exclude": 1,
        "total": 1,
    }
    # 편집으로 문장이 사라지면 판단도 떨어진다
    assert (
        evidence.decisions_for_sections([Section(key="tech_importance", sentences=[])], decisions)
        == []
    )


# ── U3 ─────────────────────────────────────────────────
def test_rewrite_merge_preserves_proposer_sentences_at_their_index_and_choices():
    current = Section(key="method", sentences=_section().sentences, choices=["applied"])
    new = [
        Sentence(text="새 1임.", evidence=["openalex:W0#0"]),
        Sentence(text="새 2임.", evidence=[]),
    ]
    cand = rewrite.merge_candidate(current, new)
    assert [s.text for s in cand.sentences] == ["새 1임.", "문장 1임.", "새 2임."]
    assert cand.sentences[1].origin == "proposer_edit" and cand.choices == ["applied"]
    picked = rewrite.pick(cand, [2])
    assert [s.text for s in picked.sentences] == ["문장 1임.", "새 2임."]  # 보존 문장은 항상 남는다
    rows = rewrite.side_by_side(current, cand)
    assert rows[1]["candidate"]["preserved"] is True and rows[0]["current"]["text"] == "문장 0임."


def test_checklist_questions_only_for_missing_elements():
    items = [
        {"element": "산출물", "question": "산출물은?", "keywords": ["산출물", "보고서"]},
        {"element": "검증 방법", "question": "어떻게 검증?", "keywords": ["검증", "시험"]},
    ]
    sec = Section(key="method", sentences=[Sentence(text="1차년도 보고서를 냄.")])
    assert checklist.missing_elements(sec, items) == [
        {"element": "검증 방법", "question": "어떻게 검증?"}
    ]
    assert checklist.coverage(sec, items) == 0.5 and checklist.coverage(sec, []) is None
    assert checklist.missing_elements(None, items)[0]["element"] == "산출물"
    assert checklist.clean_answers({" 검증 방법 ": " 현장 시험 ", "x": "", "": "y"}) == {
        "검증 방법": "현장 시험"
    }


# ── U6 ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("연구기간 2년", 24),
        ("1년 6개월", 18),
        ("총 18개월", 18),
        ("2개월 내 착수", None),
        ("", None),
    ],
)
def test_research_period_months(text, months):
    assert schedule.research_period_months(text) == months


def test_schedule_months_sums_ranges_and_singletons():
    assert schedule.schedule_months("1~6개월 분석, 7~12개월 개발, 검증 3개월") == 15
    assert schedule.schedule_months("1차년도 설계, 2차년도 실증") == 24
    assert schedule.schedule_months("일정 없음") == 0


def test_schedule_problem_only_when_plan_exceeds_period():
    long = Section(key="method", sentences=[Sentence(text="1~12개월 분석, 13~30개월 개발.")])
    short = Section(key="method", sentences=[Sentence(text="1~6개월 분석, 7~24개월 개발.")])
    assert [
        p.code for p in schedule.schedule_problems(Draft(run_id="r", request=REQ, sections=[long]))
    ] == ["schedule_exceeds_period"]
    assert schedule.schedule_problems(Draft(run_id="r", request=REQ, sections=[short])) == []
    no_period = REQ.model_copy(update={"constraints": ""})
    assert schedule.schedule_problems(Draft(run_id="r", request=no_period, sections=[long])) == []
    assert (
        "24개월" in schedule.schedule_instruction(24)
        and "목표치 확인 필요" in schedule.metric_instruction()
    )


# ── U8 ─────────────────────────────────────────────────
def _state():
    return RunState(
        run_id="20260101000000-00000001",
        user="local",
        status="finalized",
        steps=[
            StepRecord(
                name="retrieve",
                status="done",
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:02+00:00",
            ),
            StepRecord(
                name="section:title",
                status="done",
                started_at="2026-01-01T00:00:02+00:00",
                finished_at="2026-01-01T00:00:05+00:00",
            ),
            StepRecord(
                name="section:method",
                status="done",
                started_at="2026-01-01T00:00:05+00:00",
                finished_at="2026-01-01T00:00:09+00:00",
            ),
            StepRecord(name="finalize", status="pending"),
        ],
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:01:00+00:00",
        finalized_at="2026-01-01T00:02:00+00:00",
    )


def test_step_durations_merge_sections_and_aggregate_counts_only():
    assert usage.step_durations(_state()) == {"retrieve": 2.0, "sections": 7.0}
    assert usage.total_seconds(_state()) == 120.0
    rec = usage.refresh(
        UsageRecord(run_id="r"),
        _state(),
        counts={"approve": 3, "replace": 0, "exclude": 1, "total": 4},
        now="t",
    )
    assert rec.evidence.ratios() == {"approve": 0.75, "replace": 0.0, "exclude": 0.25}
    other = UsageRecord(
        run_id="r2",
        rewrites=2,
        hwpx_success=True,
        satisfaction=Satisfaction(score=4),
        total_seconds=60,
    )
    report = usage.aggregate([rec.model_copy(update={"hwpx_success": False}), other])
    assert report["runs"] == 2 and report["rewrites_total"] == 2
    assert report["hwpx_success"] == 1 and report["hwpx_failed"] == 1
    assert report["satisfaction_avg"] == 4.0 and report["satisfaction_distribution"]["4"] == 1
    assert report["evidence_ratio_avg"]["approve"] == 0.75 and report["evidence_decided_runs"] == 1
    assert usage.aggregate([]) == {"runs": 0}


def test_satisfaction_rejects_contact_info_and_length():
    with pytest.raises(ValueError, match="이메일"):
        Satisfaction(score=3, comment="연락 주세요 a@b.c")
    with pytest.raises(ValueError):
        Satisfaction(score=3, comment="x" * 201)
    assert EvidenceCounts().ratios() == {"approve": 0.0, "replace": 0.0, "exclude": 0.0}
