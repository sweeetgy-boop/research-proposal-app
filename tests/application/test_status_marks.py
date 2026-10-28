"""항목 21 — 상태 표시는 버전을 만들지 않는다 (ADR 0042). FakeLLM·가짜 이미지 생성기만."""

import json

import pytest

from rra.domain.models import (
    Chunk,
    Document,
    DraftVersion,
    EvidenceDecision,
    Section,
    Sentence,
)
from rra.domain.models.figure import ConceptBox, ConceptSpec, Figure, FigureRecommendation
from rra.domain.models.marks import VersionMarks
from rra.domain.rules import status_marks
from rra.domain.rules.change_count import count_changes
from rra.domain.rules.version_history import (
    figure_name,
    note_label,
    version_rows,
    writer_label,
)
from tests.application.test_run_manager_figures import CONCEPT, REQ, USER, make_manager
from tests.fakes import InMemoryRepository


@pytest.fixture
def repo():
    r = InMemoryRepository()
    r.seed(
        [
            Document(
                doc_id="alio:1",
                source="alio",
                doc_type="internal_report",
                title="궤도",
                body="본문",
            )
        ],
        [Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론")],
    )
    return r


def _fig(fid="f:objective:1", kind="concept", **kw) -> Figure:
    spec = ConceptSpec(boxes=[ConceptBox(label="현황", lines=["궤도"])] * 4)
    return Figure(id=fid, kind=kind, section="objective", spec=spec, image_sha="a" * 64, **kw)


def _v(n, *, figures=(), sections=None, origin="edit", note="", decisions=()) -> DraftVersion:
    return DraftVersion(
        version=n,
        origin=origin,
        note=note,
        sections=sections
        or [Section(key="objective", sentences=[Sentence(text="목표 문장임.", evidence=["d#0"])])],
        figures=list(figures),
        evidence_decisions=list(decisions),
        created_at=f"2026-10-28T0{n}:00:00+00:00",
    )


# ── 순수 규칙 ─────────────────────────────────────────
def test_apply_marks_overlays_figure_and_evidence_without_touching_the_file():
    v = _v(1, figures=[_fig()])
    marks = status_marks.mark_figure(None, 1, _fig(confirmed=True), "confirm", label="연구 개념도")
    merged = status_marks.apply_marks(v, marks)
    assert merged.figures[0].confirmed is True and v.figures[0].confirmed is False
    # 표시한 뒤 그림이 바뀌었으면(해시 다름) 표시를 적용하지 않는다
    redrawn = v.model_copy(update={"figures": [_fig().model_copy(update={"image_sha": "b" * 64})]})
    assert status_marks.apply_marks(redrawn, marks).figures[0].confirmed is False
    d = EvidenceDecision(sentence_id="s:objective:0", evidence_id="d#0", action="exclude")
    ev = status_marks.mark_evidence(None, 1, [d], [d], at="t")
    assert status_marks.apply_marks(v, ev).evidence_decisions == [d]
    assert [m.kind for m in ev.log] == ["evidence_exclude"]
    assert status_marks.is_evidence_mark([d]) and not status_marks.is_evidence_mark(
        [d.model_copy(update={"action": "replace", "replacement": "x"})]
    )


def test_status_only_legacy_versions_fold_and_descriptions_use_real_diff():
    """시범 run 처럼 그림 confirm 으로 v2~v4 가 생긴 경우 — 지우지 않고 "확인 기록" 으로 접는다.
    예전 changed_sections(그림의 섹션)는 실제로 바뀐 섹션이 아니다."""
    figs = [_fig("f:objective:1"), _fig("f:method:t1", kind="concept")]
    v1 = _v(1, figures=figs, origin="local")
    c1 = [figs[0].model_copy(update={"confirmed": True}), figs[1]]
    v2 = _v(2, figures=c1, note="그림 confirm").model_copy(
        update={"changed_sections": ["objective"]}
    )
    edited = [Section(key="objective", sentences=[Sentence(text="고친 문장임.")])]
    v3 = _v(3, figures=c1, sections=edited, note="수정")
    rows = version_rows([v1, v2, v3], writer="gemini", local_sections=2)
    assert rows[0].origin_label == "Argon 작성(일부 로컬)" and rows[0].description == "초안 작성"
    assert rows[1].status_only and rows[1].changed_sections == []
    assert rows[1].marks == ["그림 확인 — 연구 개념도"]
    assert rows[1].description == "그림 확인 — 연구 개념도"  # "그림 confirm" 이 아니라
    assert not rows[2].status_only and rows[2].changed_sections == ["objective"]
    # 메모 문구·이름
    assert note_label("그림 words", ["추진 체계도"]) == "그림 말로 고치기 — 추진 체계도"
    assert note_label("내 메모") == "내 메모"
    assert figure_name(_fig()) == "연구 개념도"
    assert writer_label("gemini") == "Argon 작성" and writer_label("local") == "로컬 작성"


def test_change_count_splits_changes_and_confirmations():
    base = _v(2, figures=[_fig()], origin="argon")
    cur = base.model_copy(update={"figures": [_fig(confirmed=True)]})
    summary = count_changes(base, cur, confirmed_after_base=True)
    assert summary.total == 0 and summary.confirmations == 2
    out = summary.dump()
    assert out["items"] == [] and {i["label"] for i in out["confirm_items"]} == {
        "그림 확인",
        "선택형 확정",
    }


# ── RunManager ──────────────────────────────────────
async def test_three_figure_confirms_keep_version_count_and_reach_views_and_finalize(repo):
    mgr, _ = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    ids = [f.id for f in mgr.store.load_version(USER, rid, 1).figures]
    assert len(ids) == 3
    for fid in ids:
        v = await mgr.figure_action(USER, rid, fid, "confirm", base_version=1)
        assert v.version == 1
    assert mgr.store.list_versions(USER, rid) == [1]
    draft = await mgr.get_draft(USER, rid)
    assert all(f.confirmed for f in draft.figures) and draft.version == 1
    check = {i.key: i for i in (await mgr.submit_check(USER, rid)).items}
    assert check["figures_unconfirmed"].ok
    state = await mgr.status(USER, rid)
    assert state.draft_version == 1 and state.status == "drafted"
    assert all(row.get("confirmed") for row in state.figures)
    versions, rows = await mgr.version_history(USER, rid)
    assert len(versions) == 1 and rows[0].marks[0].startswith("그림 확인 — ")
    changes = await mgr.changes(USER, rid)
    assert changes.total == 0 and changes.confirmations == 3
    # 내용 변경 → 새 버전은 합친 현재 버전에서 출발 (확인 표시가 이어진다)
    mgr.figures.llm.responses = [json.dumps(CONCEPT, ensure_ascii=False)]
    v2 = await mgr.add_figure(USER, rid, "concept", "method")
    assert v2.version == 2
    kept = {f.id: f.confirmed for f in mgr.store.load_version(USER, rid, 2).figures}
    assert all(kept[fid] for fid in ids)
    # 마무리: 추천이 아닌 그림 [빼기] 는 내용 변경, 그 그림만 빠진다
    await mgr.figure_action(USER, rid, ids[0], "exclude")
    result = await mgr.finalize(
        USER, rid, choices={"task_type": ["applied"], "utilization": ["software"]}
    )
    assert ids[0] not in mgr.renderer.calls[-1]["figures"]
    assert result.state.status == "finalized"


async def test_choice_confirm_is_logged_on_current_version(repo):
    mgr, _ = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    await mgr.confirm(USER, rid, {"task_type": ["applied"]})
    marks = mgr.store.load_marks(USER, rid, 1)
    assert isinstance(marks, VersionMarks) and [m.kind for m in marks.log] == ["choice_confirm"]
    assert mgr.store.list_versions(USER, rid) == [1]
    await mgr.record_mark(USER, rid, "suggestion_ignore", label="방법 섹션 제안")
    assert [m.kind for m in mgr.store.load_marks(USER, rid, 1).log][-1] == "suggestion_ignore"


async def test_dismiss_mark_reaches_finalize(repo):
    mgr, _ = make_manager(repo)
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    v1 = mgr.store.load_version(USER, rid, 1)
    rec = FigureRecommendation(technique="swot", status="pending")
    fid = v1.figures[1].id
    patched = v1.model_copy(
        update={
            "figures": [
                f.model_copy(update={"recommendation": rec}) if f.id == fid else f
                for f in v1.figures
            ]
        }
    )
    mgr.store.save_version(USER, rid, patched)
    v = await mgr.figure_action(USER, rid, fid, "dismiss", base_version=1)
    assert v.version == 1 and not next(f for f in v.figures if f.id == fid).included
    await mgr.finalize(USER, rid, choices={"task_type": ["applied"], "utilization": ["software"]})
    assert fid not in mgr.renderer.calls[-1]["figures"]


class _BlockingLLM:
    """최종 검토가 끝나지 않는 Argon — [취소] 시험용."""

    def __init__(self):
        import asyncio

        self.started = asyncio.Event()

    async def complete(self, prompt, **kw):
        import asyncio

        self.started.set()
        await asyncio.sleep(3600)
        return "[]"


async def test_cancel_final_review_returns_to_previous_state_without_round(repo):
    mgr, _ = make_manager(repo, review="[]")
    state = await mgr.wait(USER, (await mgr.submit(USER, REQ)).run_id)
    rid = state.run_id
    before = (await mgr.status(USER, rid)).status
    rounds = mgr.store.list_reviews(USER, rid)
    blocking = _BlockingLLM()
    mgr.reviewer.llm = blocking
    started = await mgr.final_review(USER, rid)
    assert started.status == "final_reviewing"
    await blocking.started.wait()
    after = await mgr.cancel_final_review(USER, rid)
    assert after.status == before and mgr.store.list_reviews(USER, rid) == rounds
    assert after.final_reviews == 0 and mgr.store.list_versions(USER, rid) == [1]
    import pytest

    from rra.application.services.run_manager import EditRejected

    with pytest.raises(EditRejected):
        await mgr.cancel_final_review(USER, rid)
