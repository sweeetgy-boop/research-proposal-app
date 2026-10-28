"""ADR 0045 — 초안 글 먼저, 그림은 백그라운드. FakeLLM·가짜 이미지 생성기만.

- 그리는 동안 drafted(편집 열림)·figures_status=drawing·자리 카드, 그림은 한 장씩 도착
- 그리는 중 편집 → 그림이 그 버전에 들어가고 편집은 그대로, 그림 때문에 내용 버전이 늘지 않음
- 그리는 중인 자리 동작·그림 추가·최종 검토·마무리는 거부(한국어 안내)
- 서버 재시작(작업이 사라짐) → failed·자리 실패 카드, "그리는 중" 이 남지 않음
- 시간 기록(draft_visible_seconds·figures_done_seconds)이 상태·usage·manifest 에
"""

import asyncio

import pytest

from rra.adapters.logging.file_run_log import check_manifest
from rra.application.services import RunManager
from rra.application.services.run_manager import EditRejected, FinalizeRejected
from rra.domain.models import FigureJob, FigureSlot
from rra.domain.models.review import EditRequest, SentenceEdit
from rra.domain.rules import figure_job as job_rules
from rra.domain.rules.review_flow import InvalidTransition
from tests.application.test_run_manager_figures import REQ, USER, make_manager
from tests.application.test_run_manager_figures import repo as repo  # noqa: F401 (fixture)
from tests.fakes import FakeImageGenerator, FakeTaskRunner


class GatedImages(FakeImageGenerator):
    """처음 `free` 장은 바로, 나머지는 gate 가 열릴 때까지 기다린다."""

    def __init__(self, free: int = 0):
        super().__init__()
        self.gate = asyncio.Event()
        self.free = free
        self.started = 0

    async def generate(self, prompt, reference, **kw):
        self.started += 1
        if self.started > self.free:
            await self.gate.wait()
        return await super().generate(prompt, reference, **kw)


async def _until(cond, timeout=5.0):
    async def loop():
        while not await cond():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(loop(), timeout)


async def _drafted_and_drawing(mgr, rid):
    async def ok():
        st = await mgr.status(USER, rid)
        return st.status == "drafted" and st.figures_status == "drawing"

    await _until(ok)


async def test_figures_land_one_by_one_while_draft_is_already_visible(repo):  # noqa: F811
    images = GatedImages(free=1)
    mgr, log = make_manager(repo, images=images)
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)

    async def first_landed():
        return len((await mgr.get_draft(USER, rid)).figures) == 1

    await _until(first_landed)
    st = await mgr.status(USER, rid)
    assert st.figures_status == "drawing" and st.step("figures").status == "pending"
    # 그리는 중인 자리는 카드로 (한국어 이름, 영어·코드 없음)
    drawing = [s for s in st.figure_slots if s["status"] == "drawing"]
    assert len(drawing) == 2 and all(s["display_name"] for s in drawing)
    assert all(s["reason_label"] is None for s in drawing)
    # 버전 파일은 그리는 동안 그대로 — 읽기가 합친다
    assert mgr.store.load_version(USER, rid, 1).figures == []
    assert st.draft_visible_seconds is not None and st.figures_done_seconds is None
    images.gate.set()
    final = await mgr.wait(USER, rid)
    assert final.figures_status == "done" and final.figure_slots == []
    assert len(mgr.store.load_version(USER, rid, 1).figures) == 3  # 끝나면 버전 파일에 채운다
    assert final.figures_done_seconds is not None
    assert final.figures_done_seconds >= final.draft_visible_seconds
    usage = mgr.store.load_usage(USER, rid)
    assert usage.draft_visible_seconds == final.draft_visible_seconds
    assert usage.figures_done_seconds == final.figures_done_seconds
    m = log.records[-1][1]
    check_manifest(m)
    assert m["timing"]["figures_status"] == "done"
    assert m["timing"]["figures_done_seconds"] == final.figures_done_seconds
    assert [f["id"] for f in m["figures"]] == [
        f.id for f in (await mgr.get_draft(USER, rid)).figures
    ]


async def test_edit_while_drawing_keeps_edit_and_figures_land_without_new_version(repo):  # noqa: F811
    images = GatedImages()
    mgr, _ = make_manager(repo, images=images)
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)
    v2 = await mgr.apply_edits(
        USER,
        rid,
        EditRequest(
            sentences=[
                SentenceEdit(
                    sentence_id="s:objective:0", action="manual", text="제안자가 고친 문장."
                )
            ],
            base_version=1,
        ),
    )
    assert v2.version == 2 and v2.figures == []
    images.gate.set()
    final = await mgr.wait(USER, rid)
    assert final.draft_version == 2 and mgr.store.list_versions(USER, rid) == [1, 2]
    view = await mgr.get_draft(USER, rid)
    assert len(view.figures) == 3 and view.version == 2
    current = mgr.store.load_version(USER, rid, 2)
    assert current.sections[0].sentences[0].text == "제안자가 고친 문장."
    assert len(current.figures) == 3  # 지금 버전에 그림이 들어갔다 (새 버전 없음)
    assert len(mgr.store.load_version(USER, rid, 1).figures) == 3
    assert final.status == "editing"


async def test_actions_on_pending_figures_and_finishing_steps_wait(repo):  # noqa: F811
    images = GatedImages()
    mgr, _ = make_manager(repo, images=images, review='{"sentences": []}')
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)
    st = await mgr.status(USER, rid)
    slot = st.figure_slots[0]["slot_id"]
    with pytest.raises(EditRejected, match="아직 그리는 중"):
        await mgr.figure_action(USER, rid, slot, "confirm")
    with pytest.raises(EditRejected, match="그림을 그리는 중"):
        await mgr.add_figure(USER, rid, "process", "method")
    with pytest.raises(EditRejected, match="그림을 그리는 중"):
        await mgr.retry_techniques(USER, rid)
    # 1차 검토(켜져 있으면)는 그림을 기다리지 않고 바로 — 제안자 편집과 v2 가 어긋나지 않게
    assert mgr.store.list_reviews(USER, rid) == [1]
    images.gate.set()
    final = await mgr.wait(USER, rid)
    assert final.review_rounds == 1 and final.figures_status == "done"
    assert len((await mgr.get_draft(USER, rid)).figures) == 3  # 검토가 만든 v2 에도 그림


async def test_finalize_waits_for_figures(repo):  # noqa: F811
    images = GatedImages()
    mgr, _ = make_manager(repo, images=images)  # 검토 LLM 없음 → 최종 검토 없이 마무리 가능
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)
    with pytest.raises(FinalizeRejected, match="그림 준비 중"):
        await mgr.finalize(USER, rid)
    images.gate.set()
    await mgr.wait(USER, rid)
    res = await mgr.finalize(USER, rid)
    assert res.state.status == "finalized"
    assert len([f for f in res.state.figures if f.get("placement")]) == 3  # 그림이 HWPX 에


async def test_final_review_waits_for_figures(repo):  # noqa: F811
    images = GatedImages()
    mgr, _ = make_manager(repo, images=images, review='{"sentences": []}')
    mgr.review_auto = False
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)
    with pytest.raises(InvalidTransition, match="그림 준비 중"):
        await mgr.final_review(USER, rid)
    images.gate.set()
    await mgr.wait(USER, rid)


async def test_restart_marks_interrupted_job_failed_and_cards_offer_redraw(repo):  # noqa: F811
    mgr, _ = make_manager(repo)
    rid = (await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)).run_id
    # 서버가 그리는 도중 죽은 것처럼: 작업 파일은 drawing, 락·작업은 없음
    job = mgr.store.load_figure_job(USER, rid)
    drawing = FigureJob(
        status="drawing",
        base_version=1,
        submitted_at=job.submitted_at,
        slots=[
            FigureSlot(slot_id="slot-1", kind="schedule", section="method", display_name="일정")
        ],
        figures=[],
    )
    mgr.store.save_figure_job(USER, rid, drawing)
    fresh = RunManager(
        mgr.generate,
        mgr.store,
        mgr.slot,
        mgr.run_log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T10:05:00+00:00",
        renderer=mgr.renderer,
        figures=mgr.figures,
    )
    st = await fresh.status(USER, rid)
    assert st.figures_status == "failed" and st.step("figures").status == "error"
    assert st.figure_slots[0]["status"] == "failed"
    assert "다시 시작" in st.figure_slots[0]["reason_label"]
    assert mgr.store.load_figure_job(USER, rid).status == "failed"  # 저장도 바뀌었다
    # 실패한 작업은 마무리를 막지 않는다 (그림 없이 진행 가능 — 카드가 [다시 그리기])
    assert not fresh._figures_busy(USER, rid)


async def test_runs_with_drawing_figures_are_listed_as_drawing(repo):  # noqa: F811
    images = GatedImages()
    mgr, _ = make_manager(repo, images=images)
    rid = (await mgr.submit(USER, REQ)).run_id
    await _drafted_and_drawing(mgr, rid)
    rows = {s.run_id: s for s in mgr.list_all_runs()}
    assert rows[rid].figures_status in job_rules.ACTIVE_JOB  # rra runs active 가 센다
    assert mgr.store.figures_alive(USER, rid) and not mgr.store.is_alive(USER, rid)
    images.gate.set()
    await mgr.wait(USER, rid)
    assert (await mgr.status(USER, rid)).figures_status == "done"


async def test_sections_progress_lists_finished_sections(repo):  # noqa: F811
    mgr, _ = make_manager(repo)
    rid = (await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)).run_id
    view = await mgr.sections_progress(USER, rid)
    assert view["pending"] == [] and view["sections"][0]["key"] == "objective"
    assert view["sections"][0]["sentences"] == [
        "궤도 틀림 진행 속도를 추정해 보수 우선순위를 산정함."
    ]


def test_rules_merge_land_and_finish():
    from rra.domain.models.figure import Figure

    def fig(fid, section="method"):
        return Figure.model_validate(
            {
                "id": fid,
                "kind": "process",
                "section": section,
                "caption": "c",
                "spec": {
                    "kind": "process",
                    "stages": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
                },
            }
        )

    job = job_rules.new_job(
        [("process", "method"), ("schedule", "method")],
        technique_slot=True,
        base_version=1,
        now="2026-10-29T00:01:00+00:00",
        submitted_at="2026-10-29T00:00:00+00:00",
    )
    assert [s.slot_id for s in job.slots] == ["slot-1", "slot-2", "slot-3"]
    assert job.draft_visible_seconds == 60.0 and job.slots[2].display_name == "분석 기법 추천 그림"
    job, a = job_rules.land(job, "slot-1", fig("f:method:1"))
    job, b = job_rules.land(job, "slot-2", fig("f:method:1"))  # 겹치는 id → 새 id
    assert a.id == "f:method:1" and b.id == "f:method:2"
    edited = fig("f:method:1").model_copy(update={"caption": "제안자"})
    merged = job_rules.merge_figures([edited], job.figures)
    assert [f.id for f in merged] == ["f:method:1", "f:method:2"] and merged[0].caption == "제안자"
    done = job_rules.finish(job, "2026-10-29T00:03:00+00:00")
    assert done.status == "done" and done.figures_done_seconds == 180.0
    assert done.slots[2].status == "failed"  # 끝까지 안 끝난 자리는 실패 카드
    assert job_rules.reason_label("ConnectionError", "failed").endswith("(호출 실패).")
    assert "규칙에 걸러짐" in job_rules.reason_label("invalid", "skipped")
    assert job_rules.interrupt(job, "2026-10-29T00:02:00+00:00").status == "failed"
    assert job_rules.is_pending_slot(job, "slot-3") and not job_rules.is_pending_slot(job, "slot-1")
