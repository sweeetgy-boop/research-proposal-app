"""RunManager — 재개·단계 기록·동시성·manifest. FakeLLM·InMemory 저장소만 (모델·파일 없음)."""

import asyncio
import json

import pytest

from rra.application.ports import RunBusy, RunNotFound
from rra.application.services import QueueFull, RunManager, RunNotResumable
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Chunk
from rra.domain.rules.lint import LintRules
from tests.fakes import (
    FakeLLM,
    FakePromptLibrary,
    FakeRunLog,
    FakeSlot,
    InMemoryRepository,
    InMemoryRunStore,
)

KEYS = ["background", "problem", "prior_work", "objective"]
USER = "local"


def sentence(text, ev=()):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


ANSWERS = [
    sentence("배경 문장"),
    sentence("문제 문장"),
    sentence("선행연구 문장", ["alio:1#0"]),
    sentence("목표 문장"),
]


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    r.upsert(docs, chunks)
    return r


def build(repo, llm, *, store=None, slot=None, log=None, required=None, **kw):
    rules = LintRules(required_sections=required or KEYS, evidence_required=["prior_work"])
    gen = GenerateProposal(llm, repo, FakePromptLibrary(), rules, KEYS)
    store = store or InMemoryRunStore()
    return RunManager(
        gen,
        store,
        slot or FakeSlot(),
        log or FakeRunLog(),
        model="local-14b",
        clock=lambda: "2026-01-01T00:00:00+00:00",
        **kw,
    ), store


async def run_to_end(mgr, req):
    state = await mgr.submit(USER, req)
    return await mgr.wait(USER, state.run_id)


async def test_happy_path_records_every_step(repo, req):
    mgr, store = build(repo, FakeLLM(ANSWERS))
    seen = []
    state = await mgr.submit(USER, req, on_step=lambda st, step: seen.append(step.name))
    assert state.status == "queued"
    final = await mgr.wait(USER, state.run_id)

    assert final.status == "done" and final.progress == (6, 6)
    assert seen == ["retrieve", *(f"section:{k}" for k in KEYS), "finalize"]
    prior = final.step("section:prior_work")
    assert (prior.sentences, prior.evidence, len(prior.prompt_hash)) == (1, ["alio:1#0"], 16)
    assert store.drafts[(USER, state.run_id)].section("prior_work").sentences[0].evidence == [
        "alio:1#0"
    ]
    assert not store.claimed  # 끝나면 락을 푼다


async def test_failure_mid_run_then_resume_only_redoes_missing_sections(repo, req):
    llm = FakeLLM(list(ANSWERS), fail_at={2})  # 세 번째 섹션(prior_work)에서 LLM 실패
    mgr, store = build(repo, llm)
    interrupted = await run_to_end(mgr, req)

    assert interrupted.status == "interrupted"
    assert interrupted.step("section:prior_work").status == "error"
    assert interrupted.step("section:prior_work").error == "TimeoutError"  # 메시지는 남기지 않음
    assert set(store.sections[(USER, interrupted.run_id)]) == {"background", "problem"}

    calls_before = len(llm.calls)
    searches_before = len(repo.calls)
    await mgr.resume(USER, interrupted.run_id)
    done = await mgr.wait(USER, interrupted.run_id)

    assert done.status == "done"
    assert len(llm.calls) - calls_before == 2  # prior_work·objective 만 다시 호출
    assert len(repo.calls) == searches_before  # 검색은 다시 하지 않는다 (스냅샷 재사용)
    draft = store.drafts[(USER, done.run_id)]
    assert [s.key for s in draft.sections] == KEYS
    assert draft.section("background").sentences[0].text == "배경 문장"


async def test_resumed_draft_equals_uninterrupted_draft(repo, req):
    whole, whole_store = build(repo, FakeLLM(list(ANSWERS)))
    a = await run_to_end(whole, req)
    broken, broken_store = build(repo, FakeLLM(list(ANSWERS), fail_at={1}))
    b = await run_to_end(broken, req)
    await broken.resume(USER, b.run_id)
    await broken.wait(USER, b.run_id)
    da = whole_store.drafts[(USER, a.run_id)]
    db = broken_store.drafts[(USER, b.run_id)]
    assert [s.model_dump() for s in da.sections] == [s.model_dump() for s in db.sections]
    assert da.retrieved_ids == db.retrieved_ids


async def test_resume_keeps_the_original_evidence_set_even_if_db_changed(repo, req, docs):
    llm = FakeLLM(
        [
            sentence("배경"),
            sentence("문제"),
            sentence("새 문서 인용", ["new:1#0"]),
            sentence("목표"),
        ],
        fail_at={2},
    )
    mgr, store = build(repo, llm)
    st = await run_to_end(mgr, req)
    # 중단 사이에 ingest 가 새 문서를 넣었다
    repo.upsert([], [Chunk(chunk_id="new:1#0", doc_id="new:1", ordinal=0, text="새 자료")])
    await mgr.resume(USER, st.run_id)
    done = await mgr.wait(USER, st.run_id)
    # 스냅샷에 없던 id 는 인용할 수 없다 → 근거 필수 섹션이 비어 invalid
    assert done.status == "invalid"
    assert {p["code"] for p in done.problems} == {"missing"}
    assert done.step("section:prior_work").dropped == 1


async def test_lint_failure_is_a_state_not_an_exception(repo, req):
    mgr, _ = build(repo, FakeLLM([sentence("배경"), "자유 텍스트", sentence("x"), sentence("y")]))
    final = await run_to_end(mgr, req)
    assert final.status == "invalid"
    assert {"section": "problem", "code": "missing"}.items() <= final.problems[0].items()


async def test_manifest_has_no_raw_text(repo, req):
    log = FakeRunLog()
    mgr, _ = build(repo, FakeLLM(list(ANSWERS), fail_at={3}), log=log)
    st = await run_to_end(mgr, req)
    last = log.records[-1][1]
    dumped = json.dumps(last, ensure_ascii=False)
    for secret in ("궤도", "센서", "배경 문장", "선행연구 문장", "127.0.0.1", "응답 없음"):
        assert secret not in dumped
    assert last["run_id"] == st.run_id and last["status"] == "interrupted"
    assert last["query_hash"] and "alio:1#0" in last["retrieved"]
    assert last["model"] == "local-14b"
    assert {s["name"]: s["error"] for s in last["steps"]}["section:objective"] == "TimeoutError"


async def test_concurrent_submits_run_one_at_a_time(repo, req):
    slot = FakeSlot()
    mgr, _ = build(repo, FakeLLM(ANSWERS * 2), slot=slot)
    a = await mgr.submit(USER, req)
    b = await mgr.submit(USER, req)
    ra, rb = await asyncio.gather(mgr.wait(USER, a.run_id), mgr.wait(USER, b.run_id))
    assert ra.status == rb.status == "done"
    assert slot.max_active == 1


async def test_queue_limit(repo, req):
    mgr, _ = build(repo, FakeLLM(ANSWERS * 3), max_queued=2)
    await mgr.submit(USER, req)
    await mgr.submit(USER, req)
    with pytest.raises(QueueFull):
        await mgr.submit(USER, req)


async def test_dead_process_is_reported_as_interrupted_and_resumable(repo, req):
    store = InMemoryRunStore()
    mgr, _ = build(repo, FakeLLM(list(ANSWERS)), store=store)
    # 다른 프로세스가 running 으로 남기고 죽은 상황: 상태는 running, 락은 없음
    st = store.create(USER, req, ["retrieve", *(f"section:{k}" for k in KEYS), "finalize"], "t")
    st.status = "running"
    store.save_state(st)

    assert (await mgr.status(USER, st.run_id)).status == "interrupted"
    await mgr.resume(USER, st.run_id)
    assert (await mgr.wait(USER, st.run_id)).status == "done"


async def test_live_run_elsewhere_is_not_resumable(repo, req):
    store = InMemoryRunStore()
    mgr, _ = build(repo, FakeLLM(list(ANSWERS)), store=store)
    st = store.create(USER, req, ["retrieve", "finalize"], "t")
    st.status = "interrupted"
    store.save_state(st)
    store.claim(USER, st.run_id)  # 다른 프로세스가 막 이어서 돌리기 시작함
    with pytest.raises(RunBusy):
        await mgr.resume(USER, st.run_id)


async def test_finished_run_is_not_resumable(repo, req):
    mgr, _ = build(repo, FakeLLM(list(ANSWERS)))
    st = await run_to_end(mgr, req)
    with pytest.raises(RunNotResumable):
        await mgr.resume(USER, st.run_id)


async def test_users_are_isolated_and_bad_ids_rejected(repo, req):
    mgr, _ = build(repo, FakeLLM(list(ANSWERS)))
    st = await run_to_end(mgr, req)
    with pytest.raises(RunNotFound):
        await mgr.status("other", st.run_id)
    with pytest.raises(RunNotFound):
        await mgr.get_draft(USER, "../local/" + st.run_id)


async def test_partial_draft_and_citations(repo, req):
    mgr, _ = build(repo, FakeLLM(list(ANSWERS), fail_at={3}))
    st = await run_to_end(mgr, req)
    view = await mgr.get_draft(USER, st.run_id)
    assert [s.key for s in view.sections] == ["background", "problem", "prior_work"]
    assert [(c.id, c.doc_id, c.title) for c in view.citations] == [
        ("alio:1#0", "alio:1", "궤도 상태 자동 감지 연구")
    ]


async def test_cancel_marks_interrupted_and_releases_lock(repo, req):
    class SlowLLM(FakeLLM):
        async def complete(self, prompt, **kw):
            await asyncio.sleep(3600)

    mgr, store = build(repo, SlowLLM())
    st = await mgr.submit(USER, req)
    await asyncio.sleep(0.01)
    mgr._tasks[st.run_id].cancel()
    with pytest.raises(asyncio.CancelledError):
        await mgr.wait(USER, st.run_id)
    final = store.load_state(USER, st.run_id)
    assert final.status == "interrupted" and not store.claimed
    assert final.step("section:background").error == "CancelledError"
