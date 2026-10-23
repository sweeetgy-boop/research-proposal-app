"""FileRunStore·FileRunLog·FlockSlot — 실제 파일·프로세스 간 락. 모델 호출 없음."""

import asyncio
import json
import os
import signal
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from rra.adapters.logging import FileRunLog
from rra.adapters.runs import AsyncioTaskRunner, FileRunStore, FlockSlot
from rra.application.ports import RunBusy, RunNotFound
from rra.domain.models import Section, Sentence

ROOT = Path(__file__).parents[2]
STEPS = ["retrieve", "section:background", "finalize"]


@pytest.fixture
def store(tmp_path):
    return FileRunStore(tmp_path / "runs")


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def hold_lock_in_child(path: Path) -> subprocess.Popen:
    """다른 프로세스가 flock 을 잡고 있는 상황. 'ok' 를 찍으면 잡은 것."""
    code = textwrap.dedent(f"""
        import fcntl, os, sys, time
        fd = os.open({str(path)!r}, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        print("ok", flush=True)
        time.sleep(60)
    """)
    # 인자는 전부 테스트 상수
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", code], stdout=subprocess.PIPE, text=True
    )
    assert proc.stdout.readline().strip() == "ok"
    return proc


def test_create_layout_and_permissions(store, req):
    st = store.create("local", req, STEPS, "t0")
    run = store.root / "local" / st.run_id
    assert {p.name for p in run.iterdir()} == {"request.json", "state.json", "sections"}
    for d in (store.root, store.root / "local", run, run / "sections"):
        assert mode(d) == 0o700
    for f in ("request.json", "state.json"):
        assert mode(run / f) == 0o600
    assert store.load_request("local", st.run_id) == req
    assert [s.name for s in store.load_state("local", st.run_id).steps] == STEPS


def test_checkpoints_roundtrip(store, req, chunks):
    from rra.domain.models import RetrievalSnapshot

    st = store.create("local", req, STEPS, "t0")
    assert store.load_snapshot("local", st.run_id) is None
    snap = RetrievalSnapshot.of("q", chunks)
    store.save_snapshot("local", st.run_id, snap)
    assert store.load_snapshot("local", st.run_id) == snap
    sec = Section(key="background", sentences=[Sentence(text="문장", evidence=["alio:1#0"])])
    store.save_section("local", st.run_id, sec)
    assert store.load_sections("local", st.run_id) == {"background": sec}


def test_atomic_write_leaves_no_temp_files(store, req):
    st = store.create("local", req, STEPS, "t0")
    for i in range(5):
        st.updated_at = f"t{i}"
        store.save_state(st)
    run = store.root / "local" / st.run_id
    assert not [p for p in run.iterdir() if p.name.endswith(".tmp")]
    assert json.loads((run / "state.json").read_text())["updated_at"] == "t4"


@pytest.mark.parametrize("bad", ["../x", "20260101000000-zzzzzzzz", "", "a/b", "..", "x" * 40])
def test_bad_run_ids_never_touch_the_filesystem(store, bad):
    with pytest.raises(RunNotFound):
        store.load_state("local", bad)


@pytest.mark.parametrize("bad_user", ["../etc", "Local", "", "a/b", "x" * 40])
def test_bad_user_names_rejected(store, req, bad_user):
    with pytest.raises(ValueError):
        store.create(bad_user, req, STEPS, "t0")


def test_bad_section_key_rejected(store, req):
    st = store.create("local", req, STEPS, "t0")
    with pytest.raises(ValueError):
        store.save_section("local", st.run_id, Section(key="../../x", sentences=[]))


def test_users_are_isolated(store, req):
    st = store.create("alice", req, STEPS, "t0")
    with pytest.raises(RunNotFound):
        store.load_state("bob", st.run_id)
    assert store.list_runs("bob") == []
    assert [s.run_id for s in store.list_runs("alice")] == [st.run_id]


def test_claim_is_exclusive_and_releasable(store, req):
    st = store.create("local", req, STEPS, "t0")
    claim = store.claim("local", st.run_id)
    assert store.is_alive("local", st.run_id)
    with pytest.raises(RunBusy):
        store.claim("local", st.run_id)
    claim.release()
    claim.release()  # 두 번 불러도 안전
    assert not store.is_alive("local", st.run_id)


def test_lock_held_by_dead_process_is_released(store, req):
    st = store.create("local", req, STEPS, "t0")
    child = hold_lock_in_child(store.root / "local" / st.run_id / ".lock")
    try:
        assert store.is_alive("local", st.run_id)
        with pytest.raises(RunBusy):
            store.claim("local", st.run_id)
    finally:
        child.send_signal(signal.SIGKILL)
        child.wait()
    assert not store.is_alive("local", st.run_id)  # 커널이 락을 풀었다
    store.claim("local", st.run_id).release()


async def test_slot_is_exclusive_across_processes(tmp_path):
    lock = tmp_path / "runs" / ".generate.lock"
    lock.parent.mkdir()
    slot = FlockSlot(lock, poll_sec=0.02)
    child = hold_lock_in_child(lock)
    try:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.2):
                async with slot.acquire():
                    pytest.fail("다른 프로세스가 슬롯을 잡고 있는데 들어왔다")
    finally:
        child.send_signal(signal.SIGKILL)
        child.wait()
    async with asyncio.timeout(1):
        async with slot.acquire():
            pass


def test_run_log_writes_manifest_next_to_state(store, req, tmp_path):
    st = store.create("local", req, STEPS, "t0")
    log = FileRunLog(store.root)
    log.record(st.run_id, {"run_id": st.run_id, "status": "queued"})
    manifest = store.root / "local" / st.run_id / "manifest.json"
    assert json.loads(manifest.read_text())["status"] == "queued"
    assert mode(manifest) == 0o600
    with pytest.raises(ValueError):
        log.record("../../etc/passwd", {})
    with pytest.raises(FileNotFoundError):
        log.record("20260101000000-deadbeef", {})


# ── 실제 파일 + 프로세스 kill 후 재개 (RunManager 통합) ──────
CHILD = textwrap.dedent("""
    import asyncio, json, sys
    from pathlib import Path
    from rra.adapters.logging import FileRunLog
    from rra.adapters.runs import AsyncioTaskRunner, FileRunStore, FlockSlot
    from rra.application.services import RunManager
    from rra.application.usecases.generate_proposal import GenerateProposal
    from rra.domain.models import ProposalRequest
    from rra.domain.rules.lint import LintRules
    from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

    class HangOnThird(FakeLLM):
        async def complete(self, prompt, **kw):
            if len(self.calls) == 2:
                print("hang", flush=True)
                await asyncio.sleep(3600)
            return await super().complete(prompt, **kw)

    async def main():
        root = Path(sys.argv[1])
        keys = ["background", "problem", "objective"]
        ans = [json.dumps([{"text": k + " 문장", "evidence": []}]) for k in keys]
        gen = GenerateProposal(HangOnThird(ans), InMemoryRepository(), FakePromptLibrary(),
                               LintRules(required_sections=keys), keys)
        mgr = RunManager(gen, FileRunStore(root), FlockSlot(root / ".generate.lock"),
                         FileRunLog(root), AsyncioTaskRunner())
        req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
        st = await mgr.submit("local", req)
        print(st.run_id, flush=True)
        await mgr.wait("local", st.run_id)

    asyncio.run(main())
""")


async def test_process_killed_mid_run_is_resumed_from_files(tmp_path):
    from rra.application.services import RunManager
    from rra.application.usecases.generate_proposal import GenerateProposal
    from rra.domain.rules.lint import LintRules
    from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

    root = tmp_path / "runs"
    child = subprocess.Popen(  # noqa: S603 - 인자는 테스트 상수와 tmp 경로
        [sys.executable, "-c", CHILD, str(root)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT}"},
    )
    run_id = child.stdout.readline().strip()
    assert child.stdout.readline().strip() == "hang"  # 세 번째 섹션에서 멈춤
    child.send_signal(signal.SIGKILL)  # 정리 코드 없이 죽는다
    child.wait()

    keys = ["background", "problem", "objective"]
    llm = FakeLLM([json.dumps([{"text": "목표 문장", "evidence": []}], ensure_ascii=False)])
    gen = GenerateProposal(
        llm, InMemoryRepository(), FakePromptLibrary(), LintRules(required_sections=keys), keys
    )
    store = FileRunStore(root)
    mgr = RunManager(
        gen,
        store,
        FlockSlot(root / ".generate.lock", poll_sec=0.02),
        FileRunLog(root),
        AsyncioTaskRunner(),
    )

    state = await mgr.status("local", run_id)
    assert state.status == "interrupted"  # 상태 파일은 running 이었지만 락이 비어 있다
    assert set(store.load_sections("local", run_id)) == {"background", "problem"}

    await mgr.resume("local", run_id)
    done = await mgr.wait("local", run_id)
    assert done.status == "done" and len(llm.calls) == 1
    draft = json.loads((root / "local" / run_id / "draft.json").read_text())
    assert [s["key"] for s in draft["sections"]] == keys
    manifest = json.loads((root / "local" / run_id / "manifest.json").read_text())
    assert manifest["status"] == "done" and "목표 문장" not in json.dumps(manifest)


# ── 양식 개정 (확정값·예전 run) ──────────────────────────────
def test_confirmation_roundtrip_is_private(store, req):
    from rra.domain.models import Confirmation

    state = store.create("local", req, STEPS, "t")
    assert store.load_confirmation("local", state.run_id) is None
    store.save_confirmation(
        "local", state.run_id, Confirmation(choices={"task_type": ["applied"]}, updated_at="t")
    )
    path = store.root / "local" / state.run_id / "confirmed.json"
    assert mode(path) == 0o600
    assert store.load_confirmation("local", state.run_id).choices == {"task_type": ["applied"]}


def test_confirmation_keys_are_validated(store, req):
    from rra.domain.models import Confirmation

    state = store.create("local", req, STEPS, "t")
    with pytest.raises(ValueError):
        store.save_confirmation("local", state.run_id, Confirmation(choices={"../x": ["a"]}))


def test_legacy_request_with_proposer_still_loads(store, req):
    """양식 개정 전 request.json (proposer 필드 포함, 새 필드 없음)."""
    state = store.create("local", req, STEPS, "t")
    path = store.root / "local" / state.run_id / "request.json"
    old = {k: getattr(req, k) for k in ("current_state", "root_cause", "limitation", "goal")}
    path.write_text(json.dumps({**old, "constraints": "", "proposer": "홍길동"}), encoding="utf-8")
    loaded = store.load_request("local", state.run_id)
    assert loaded.goal == req.goal and loaded.policy_basis == "" and loaded.budget is None
    assert "proposer" not in loaded.model_dump()


def test_new_request_json_has_no_personal_fields(store, req):
    state = store.create("local", req, STEPS, "t")
    saved = json.loads((store.root / "local" / state.run_id / "request.json").read_text())
    assert not {"proposer", "name", "phone", "rank", "head"} & set(saved)


# ── 보존기간 삭제 (Step 9) ─────────────────────────────────
def test_list_users_and_delete_run_remove_the_whole_directory(store, req):
    a = store.create("local", req, STEPS, "t0")
    b = store.create("alice", req, STEPS, "t0")
    (store.root / "not-a-user!").mkdir()  # 형식이 틀린 이름은 사용자가 아니다
    assert store.list_users() == ["alice", "local"]
    store.delete_run("local", a.run_id)
    assert not (store.root / "local" / a.run_id).exists()
    assert (store.root / "alice" / b.run_id / "state.json").is_file()
    from rra.application.ports import RunNotFound

    with pytest.raises(RunNotFound):
        store.delete_run("local", a.run_id)
    with pytest.raises(RunNotFound):
        store.delete_run("alice", "../../etc")


def test_run_log_rejects_manifest_with_unexpected_or_long_fields(store, req):
    from rra.adapters.logging import check_manifest

    st = store.create("local", req, STEPS, "t0")
    log = FileRunLog(store.root)
    with pytest.raises(ValueError, match="허용되지 않은 키"):
        log.record(st.run_id, {"run_id": st.run_id, "request": {"goal": "원문"}})
    with pytest.raises(ValueError, match="step"):
        check_manifest({"steps": [{"name": "x", "message": "lint 메시지"}]})
    with pytest.raises(ValueError, match="problem"):
        check_manifest({"problems": [{"section": "a", "code": "b", "message": "원문"}]})
    with pytest.raises(ValueError, match="긴 문자열"):
        check_manifest({"run_id": "x" * 201})
    assert not (store.root / "local" / st.run_id / "manifest.json").exists()
