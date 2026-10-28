"""RunManager U1·U3·U5·U6·U7·U8 — 근거 보기·판단, 다시 쓰기·보완 질문, 우선 근거, 일정 경고,
제출 전 점검, usage·만족도 (가짜 LLM·메모리 저장소)."""

from __future__ import annotations

import json

import pytest

from rra.application.services.run_manager import (
    EditRejected,
    FeatureDisabled,
    FeedbackRejected,
    RewriteRejected,
    VersionConflict,
)
from rra.domain.models import ProposalRequest, UsabilityConfig
from rra.domain.models.review import EvidenceDecision, EvidenceDecisionRequest
from tests.application.test_review_manager import PROPOSER, REQ, build, review_reply, run


def review_with_support(support="불일치"):
    data = json.loads(review_reply())
    data["support"] = [
        {"sentence_id": "s:method:0", "support": support},
        {"sentence_id": "s:method:1", "support": "지지"},
        {"sentence_id": "s:title:0", "support": "weird"},
    ]
    return json.dumps(data, ensure_ascii=False)


# ── U1 ─────────────────────────────────────────────────
async def test_draft_review_support_is_stored_and_mismatch_becomes_a_warning():
    mgr, store, log = build(review_answers=[review_with_support()])
    st = await run(mgr)
    rnd = store.load_review("local", st.run_id, 1)
    assert rnd.support == {"s:method:0": "불일치", "s:method:1": "지지"}
    assert "[근거 적합성" in mgr.reviewer.llm.calls[0]
    codes = [(p["code"], p["sentence"]) for p in st.problems]
    assert ("evidence_mismatch", 0) in codes
    manifest = log.records[-1][1]
    assert manifest["review"]["transfers"][0]["support"] == 2
    items = await mgr.sentence_evidence("local", st.run_id, "s:method:0")
    assert [i.evidence_id for i in items] == ["openalex:W1#0"]
    assert items[0].title == "t" and items[0].source_label == "OpenAlex 해외 논문"
    assert items[0].support == "불일치" and items[0].decision is None and items[0].in_snapshot
    assert items[0].text == "궤도 틀림 이력 분석" and items[0].needs_check is False
    with pytest.raises(EditRejected):
        await mgr.sentence_evidence("local", st.run_id, "s:method:9")


async def test_evidence_decisions_are_marks_and_exclusion_warns_in_required_sections():
    mgr, store, log = build()
    st = await run(mgr)
    # 근거 필수 섹션 흉내: method 를 evidence_required 로
    mgr.generate.rules = mgr.generate.rules.model_copy(update={"evidence_required": ["method"]})
    v = await mgr.decide_evidence(
        "local",
        st.run_id,
        EvidenceDecisionRequest(
            decisions=[
                EvidenceDecision(
                    sentence_id="s:method:0", evidence_id="openalex:W1#0", action="exclude"
                )
            ],
            base_version=1,
        ),
    )
    # 항목 21: 근거 승인·제외는 상태 표시 — 버전을 만들지 않는다 (상태도 그대로)
    assert v.version == 1 and store.list_versions("local", st.run_id) == [1]
    assert [d.action for d in v.evidence_decisions] == ["exclude"]
    assert store.load_version("local", st.run_id, 1).evidence_decisions == []
    state = await mgr.status("local", st.run_id)
    assert state.status == "drafted" and state.draft_version == 1
    assert ("evidence_all_excluded", 0) in [(p["code"], p["sentence"]) for p in state.problems]
    items = await mgr.sentence_evidence("local", st.run_id, "s:method:0")
    assert items[0].decision == "exclude"
    same = await mgr.decide_evidence(
        "local",
        st.run_id,
        EvidenceDecisionRequest(
            decisions=[
                EvidenceDecision(
                    sentence_id="s:method:0", evidence_id="openalex:W1#0", action="exclude"
                )
            ]
        ),
    )
    assert same.version == 1  # 같은 판단 → 기록도 그대로
    with pytest.raises(VersionConflict):
        await mgr.decide_evidence(
            "local",
            st.run_id,
            EvidenceDecisionRequest(
                decisions=[
                    EvidenceDecision(
                        sentence_id="s:method:0", evidence_id="openalex:W1#0", action="approve"
                    )
                ],
                base_version=2,
            ),
        )
    with pytest.raises(EditRejected, match="검색 집합"):
        await mgr.decide_evidence(
            "local",
            st.run_id,
            EvidenceDecisionRequest(
                decisions=[
                    EvidenceDecision(
                        sentence_id="s:method:0",
                        evidence_id="openalex:W1#0",
                        action="replace",
                        replacement="ntis:none#0",
                    )
                ]
            ),
        )
    manifest = log.records[-1][1]
    assert manifest["versions"][-1]["decisions"] == 1
    assert manifest["usage"]["decisions"] == 1 and "comment" not in json.dumps(manifest["usage"])
    usage = store.load_usage("local", st.run_id)
    assert usage.evidence.model_dump() == {"approve": 0, "replace": 0, "exclude": 1, "total": 1}


async def test_disabled_features_raise_feature_disabled():
    mgr, store, _ = build()
    mgr.usability = UsabilityConfig(evidence_view=False, submit_check=False, feedback=False)
    st = await run(mgr)
    with pytest.raises(FeatureDisabled):
        await mgr.sentence_evidence("local", st.run_id, "s:method:0")
    with pytest.raises(FeatureDisabled):
        await mgr.submit_check("local", st.run_id)
    with pytest.raises(FeatureDisabled):
        await mgr.feedback("local", st.run_id, 5)


# ── U3 ─────────────────────────────────────────────────
async def test_rewrite_keeps_proposer_sentences_and_apply_makes_a_version():
    mgr, store, _ = build()
    st = await run(mgr)
    from tests.application.test_review_manager import manual

    await mgr.apply_edits("local", st.run_id, manual("s:method:1", "제안자가 고친 문장임."))
    await mgr.save_section_answers(
        "local", st.run_id, "method", {"검증 방법": "현장 시험으로 검증"}
    )
    mgr.generate.llm.responses.append(
        '[{"text": "새로 쓴 첫 문장임.", "evidence": ["openalex:W1#0"]}, '
        '{"text": "새로 쓴 둘째 문장임.", "evidence": []}]'
    )
    view = await mgr.rewrite_section("local", st.run_id, "method")
    prompt = mgr.generate.llm.calls[-1]
    assert "[제안자 보완 메모" in prompt and "현장 시험으로 검증" in prompt
    assert "[보존 문장" in prompt and "제안자가 고친 문장임." in prompt
    texts = [s.text for s in view.candidate.sentences]
    assert texts == ["새로 쓴 첫 문장임.", "제안자가 고친 문장임.", "새로 쓴 둘째 문장임."]
    assert view.candidate.sentences[1].origin == "proposer_edit"
    assert store.load_rewrite("local", st.run_id, "method")["base_version"] == 2
    v = await mgr.apply_rewrite("local", st.run_id, "method", chosen=[0])
    assert v.version == 3 and v.note == "AI 다시 쓰기" and v.origin == "edit"
    assert [s.text for s in v.section("method").sentences] == [
        "새로 쓴 첫 문장임.",
        "제안자가 고친 문장임.",
    ]
    assert v.section("task_type").choices == ["applied"]
    assert store.load_rewrite("local", st.run_id, "method") is None
    assert store.load_usage("local", st.run_id).rewrites == 1
    with pytest.raises(RewriteRejected, match="후보가 없습니다"):
        await mgr.apply_rewrite("local", st.run_id, "method")
    with pytest.raises(RewriteRejected, match="그런 섹션"):
        await mgr.rewrite_section("local", st.run_id, "nope")


async def test_rewrite_apply_rejects_stale_candidate():
    mgr, store, _ = build()
    st = await run(mgr)
    mgr.generate.llm.responses.append('[{"text": "후보임.", "evidence": []}]')
    await mgr.rewrite_section("local", st.run_id, "method")
    from tests.application.test_review_manager import manual

    await mgr.apply_edits("local", st.run_id, manual("s:method:0", "그 사이 고침."))
    with pytest.raises(VersionConflict):
        await mgr.apply_rewrite("local", st.run_id, "method")


async def test_section_questions_come_from_checklist_and_answers_persist():
    mgr, store, _ = build()
    mgr.checklists = {
        "method": [
            {"element": "산출물", "question": "산출물은?", "keywords": ["산출물"]},
            {"element": "검증 방법", "question": "검증은?", "keywords": ["검증"]},
        ]
    }
    st = await run(mgr)
    out = await mgr.section_questions("local", st.run_id, "method")
    assert [q["element"] for q in out["questions"]] == ["산출물", "검증 방법"]
    assert out["coverage"] == 0.0 and out["answers"] == {}
    merged = await mgr.save_section_answers("local", st.run_id, "method", {"산출물": "보고서"})
    assert merged == {"산출물": "보고서"}
    out = await mgr.section_questions("local", st.run_id, "method")
    assert out["answers"] == {"산출물": "보고서"}
    assert (await mgr.section_questions("local", st.run_id, "title"))["questions"] == []
    with pytest.raises(EditRejected):
        await mgr.section_questions("local", st.run_id, "nope")


# ── U5 우선 근거 ────────────────────────────────────────
async def test_priority_evidence_is_kept_only_within_the_snapshot_and_moves_chunks_first():
    mgr, store, _ = build()
    st = await mgr.submit("local", REQ, priority_evidence=["openalex:W1", "ntis:none"])
    st = await mgr.wait("local", st.run_id)
    snap = store.load_snapshot("local", st.run_id)
    assert snap.priority_ids == ["openalex:W1"] and snap.chunks[0].doc_id == "openalex:W1"
    assert store.load_notes("local", st.run_id)["priority_evidence"] == ["openalex:W1", "ntis:none"]


# ── U6 ─────────────────────────────────────────────────
async def test_schedule_and_metric_instructions_and_exceed_warning():
    from tests.application.test_review_manager import ANSWERS

    mgr, store, _ = build()
    mgr.generate.llm.responses = [
        ANSWERS[0],
        ANSWERS[1],
        '[{"text": "1~12개월 분석함.", "evidence": ["openalex:W1#0"]}, '
        '{"text": "13~30개월 개발함.", "evidence": []}]',
        ANSWERS[3],
    ]
    req = REQ.model_copy(update={"constraints": "연구기간 2년, 예산 1억"})
    st = await mgr.submit("local", req)
    st = await mgr.wait("local", st.run_id)
    method_prompt = next(c for c in mgr.generate.llm.calls if "[섹션: method]" in c)
    assert "[추진일정" in method_prompt and "24개월" in method_prompt
    assert "schedule_exceeds_period" in [p["code"] for p in st.problems]
    assert st.status == "drafted"  # 경고만


# ── U7·U8 ───────────────────────────────────────────────
async def test_submit_check_items_and_targets():
    mgr, store, _ = build()
    mgr.generate.rules = mgr.generate.rules.model_copy(update={"evidence_required": ["method"]})
    st = await run(mgr)
    check = await mgr.submit_check("local", st.run_id)
    by_key = {i.key: i for i in check.items}
    assert set(by_key) >= {
        "required_sections",
        "unresolved_alerts",
        "evidence_approval",
        "open_memos",
        "stale_edits",
        "choices_confirmed",
        "field_limits",
        "review_state",
    }
    assert by_key["required_sections"].ok and by_key["review_state"].ok  # review_skipped → 가능
    assert (
        not by_key["choices_confirmed"].ok
        and by_key["choices_confirmed"].target == "section:task_type"
    )
    # 항목 16: 판정 불일치·부분·이미지 판독이 아닌 근거는 "확인 필요"가 아니라 일괄 승인 대상
    ev = by_key["evidence_approval"]
    assert (
        ev.ok and ev.extra["total"] == 1 and ev.extra["bulk"] == 1 and ev.extra["attention"] == []
    )
    assert "0/1" not in ev.detail and "[근거 일괄 승인]" in ev.detail and len(check.failing) == 1
    await mgr.decide_evidence(
        "local",
        st.run_id,
        EvidenceDecisionRequest(
            decisions=[
                EvidenceDecision(
                    sentence_id="s:method:0", evidence_id="openalex:W1#0", action="exclude"
                )
            ]
        ),
    )
    check = await mgr.submit_check("local", st.run_id)
    by_key = {i.key: i for i in check.items}
    assert by_key["evidence_approval"].ok and by_key["evidence_approval"].extra["bulk"] == 0
    assert not by_key["unresolved_alerts"].ok and by_key["unresolved_alerts"].extra["by_code"] == {
        "evidence_all_excluded": 1
    }
    # 화면은 코드 대신 한국어 설명 (domain/rules/problem_labels.py)
    assert by_key["unresolved_alerts"].detail == "근거를 모두 제외한 문장 1건"
    assert by_key["unresolved_alerts"].extra["by_label"][0]["label"] == "근거를 모두 제외한 문장"
    assert by_key["unresolved_alerts"].target == "sentence:s:method:0"
    assert not check.ok and len(check.failing) == 2


async def test_usage_record_and_feedback_after_finalize():
    mgr, store, log = build()
    st = await run(mgr)
    rec = await mgr.usage("local", st.run_id)
    assert rec.run_id == st.run_id and "retrieve" in rec.step_seconds and rec.hwpx_success is None
    with pytest.raises(FeedbackRejected):
        await mgr.feedback("local", st.run_id, 4, "좋음")
    result = await mgr.finalize("local", st.run_id, proposer=PROPOSER)
    assert result.state.status == "finalized"
    rec = store.load_usage("local", st.run_id)
    assert rec.hwpx_success is True
    rec = await mgr.feedback("local", st.run_id, 4, "근거 보기가 편함")
    assert rec.satisfaction.score == 4 and rec.satisfaction.comment == "근거 보기가 편함"
    manifest = log.records[-1][1]
    assert manifest["usage"] == {
        "rewrites": 0,
        "decisions": 0,
        "hwpx_success": True,
        "satisfaction_score": 4,
    }
    with pytest.raises(Exception, match="이메일"):
        await mgr.feedback("local", st.run_id, 4, "연락 a@b.c")
    mgr.usability = UsabilityConfig(usage_record=False)
    mgr2, store2, _ = build()
    mgr2.usability = UsabilityConfig(usage_record=False)
    st2 = await run(mgr2)
    assert store2.load_usage("local", st2.run_id) is None


def test_proposal_request_unchanged_by_priority_field():
    assert "priority_evidence" not in ProposalRequest.model_fields


def test_evidence_url_prefers_image_url_for_image_vision():
    from rra.application.services.run_manager import _evidence_url
    from rra.domain.models import Document

    doc = Document(
        doc_id="alio:1", source="alio", doc_type="internal_report", title="t", url="https://x/p"
    )
    assert _evidence_url(doc, {}, "summary") == "https://x/p"
    raw = {"image": {"url": "https://x/img.png", "page_url": "https://x/p"}}
    assert _evidence_url(doc, raw, "image_vision") == "https://x/img.png"
    assert (
        _evidence_url(doc, {"image": {"page_url": "https://x/p2"}}, "image_vision")
        == "https://x/p2"
    )
    assert _evidence_url(None, {}, None) is None
