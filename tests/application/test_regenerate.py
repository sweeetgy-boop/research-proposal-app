"""항목 17 — 초안이 있는 run 에서 ①·② 입력을 바꿔 저장: 관련 섹션만 / 전체 다시 쓰기 (가짜 LLM)."""

from __future__ import annotations

import pytest

from rra.application.ports import RunBusy
from rra.application.services.run_manager import EditRejected, VersionConflict
from rra.domain.models.review import EditRequest, SentenceEdit
from tests.application.test_review_manager import REQ, build, run

METHOD = (
    '[{"text": "새 제약에 맞춰 1년 안에 분석함.", "evidence": ["openalex:W1#0"]}, '
    '{"text": "현장 시험은 2차년도에 함.", "evidence": []}]'
)
UTIL = (
    '{"choices": ["software"], "sentences": [{"text": "시설처가 2027년 적용함.", "evidence": []}]}'
)
TITLE = '[{"text": "새 제목 궤도 열화 예측", "evidence": []}]'
TASK = '{"choices": ["applied"], "sentences": [{"text": "응용 연구임.", "evidence": []}]}'


async def drafted():
    mgr, store, _log = build()
    st = await run(mgr)
    assert st.status == "drafted" and st.draft_version == 1
    return mgr, store, st.run_id


async def test_preview_maps_changed_fields_to_sections_without_saving():
    mgr, store, rid = await drafted()
    out = await mgr.request_change_preview(
        "local", rid, REQ.model_copy(update={"constraints": "연구기간 1년"})
    )
    assert out["fields"] == ["constraints"]
    assert out["sections"] == ["method", "utilization"] and out["can_regenerate"]
    core = await mgr.request_change_preview(
        "local", rid, REQ.model_copy(update={"goal": "새 목표"})
    )
    assert core["sections"] == ["title", "task_type", "method", "utilization"]
    form_only = await mgr.request_change_preview(
        "local", rid, REQ.model_copy(update={"department": "기술연구처"})
    )
    assert form_only["fields"] == ["department"] and form_only["sections"] == []
    assert store.load_request("local", rid) == REQ  # 저장하지 않는다


async def test_sections_mode_rewrites_only_related_sections_as_a_new_version_and_keeps_edits():
    mgr, store, rid = await drafted()
    # 제안자가 method 둘째 문장을 직접 고친 v2
    await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:method:1", action="manual", text="직접 쓴 문장.")
            ]
        ),
    )
    mgr.generate.llm.responses = [METHOD, UTIL]
    new_req = REQ.model_copy(update={"constraints": "연구기간 1년"})
    result = await mgr.regenerate("local", rid, new_req, mode="sections", base_version=2)
    v = result.version
    assert v.version == 3 and v.origin == "regenerate"
    assert result.regenerated == ["method", "utilization"] and result.failed == []
    assert "관련 섹션 다시 쓰기" in v.note and "제약 조건" in v.note
    method = [s.text for s in v.section("method").sentences]
    assert "직접 쓴 문장." in method  # 제안자 수정 문장은 그 자리에
    assert "새 제약에 맞춰 1년 안에 분석함." in method
    old_title = store.load_version("local", rid, 2).section("title")
    assert v.section("title") == old_title  # 관련 없는 섹션은 그대로
    assert store.load_request("local", rid).constraints == "연구기간 1년"
    assert store.list_versions("local", rid) == [1, 2, 3]  # 이전 버전 보존
    state = await mgr.status("local", rid)
    assert state.status == "editing" and state.draft_version == 3
    notes = store.load_notes("local", rid)
    assert notes["request_history"][-1]["fields"] == ["constraints"]
    assert "연구기간" not in str(notes["request_history"])  # 칸 이름만, 본문 없음


async def test_all_mode_rewrites_every_section_and_old_draft_stays_as_previous_version():
    mgr, store, rid = await drafted()
    await mgr.apply_edits(
        "local",
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:method:1", action="manual", text="직접 쓴 문장.")
            ]
        ),
    )
    mgr.generate.llm.responses = [TITLE, TASK, METHOD, UTIL]
    result = await mgr.regenerate(
        "local", rid, REQ.model_copy(update={"goal": "예측과 자동 경보"}), mode="all"
    )
    v = result.version
    assert v.version == 3 and set(result.regenerated) == {
        "title",
        "task_type",
        "method",
        "utilization",
    }
    assert "초안 전체 다시 생성" in v.note
    assert "직접 쓴 문장." not in [s.text for s in v.section("method").sentences]
    assert v.section("title").sentences[0].text == "새 제목 궤도 열화 예측"
    previous = store.load_version("local", rid, 2)
    assert "직접 쓴 문장." in [s.text for s in previous.section("method").sentences]
    assert mgr.run_title(await mgr.status("local", rid)) == "새 제목 궤도 열화 예측"


async def test_failed_section_keeps_previous_text_and_is_reported_not_emptied():
    mgr, store, rid = await drafted()
    mgr.generate.llm.responses = ["[]", "[]", "[]", UTIL]  # method 는 빈 응답(재시도 포함)
    result = await mgr.regenerate(
        "local", rid, REQ.model_copy(update={"constraints": "1년"}), mode="sections"
    )
    assert result.regenerated == ["utilization"]
    assert [f["key"] for f in result.failed] == ["method"]
    before = store.load_version("local", rid, 1).section("method")
    assert result.version.section("method").sentences == before.sentences


async def test_all_sections_failing_saves_nothing():
    mgr, store, rid = await drafted()
    mgr.generate.llm.responses = []  # 모든 호출이 "[]"
    with pytest.raises(EditRejected):
        await mgr.regenerate(
            "local", rid, REQ.model_copy(update={"constraints": "1년"}), mode="sections"
        )
    assert store.load_request("local", rid) == REQ
    assert store.list_versions("local", rid) == [1]


async def test_form_only_change_saves_input_without_a_new_version():
    mgr, store, rid = await drafted()
    result = await mgr.regenerate(
        "local", rid, REQ.model_copy(update={"department": "기술연구처"}), mode="sections"
    )
    assert result.saved_only and result.version.version == 1
    assert store.load_request("local", rid).department == "기술연구처"
    assert store.list_versions("local", rid) == [1]


async def test_base_version_conflict_and_busy_run_are_refused():
    mgr, store, rid = await drafted()
    new_req = REQ.model_copy(update={"constraints": "1년"})
    with pytest.raises(VersionConflict):
        await mgr.regenerate("local", rid, new_req, base_version=5)
    claim = store.claim("local", rid)
    try:
        mgr.generate.llm.responses = [METHOD, UTIL]
        with pytest.raises(RunBusy):
            await mgr.regenerate("local", rid, new_req)
    finally:
        claim.release()


async def test_priority_evidence_change_targets_evidence_sections_and_stays_in_snapshot():
    mgr, store, rid = await drafted()
    mgr.generate.rules = mgr.generate.rules.model_copy(update={"evidence_required": ["method"]})
    out = await mgr.request_change_preview("local", rid, REQ, priority_evidence=["openalex:W1"])
    assert out["fields"] == ["priority_evidence"] and out["sections"] == ["method"]
    mgr.generate.llm.responses = [METHOD]
    result = await mgr.regenerate(
        "local", rid, REQ, mode="sections", priority_evidence=["openalex:W1", "ntis:none"]
    )
    assert result.regenerated == ["method"]
    snap = store.load_snapshot("local", rid)
    assert snap.priority_ids == ["openalex:W1"]  # 검색 집합 밖 id 는 버린다
