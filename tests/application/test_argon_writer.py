"""[3] Argon 먼저 작성 (ADR 0032) — FakeLLM 만.

- compose.writer=gemini: 섹션은 원격(Argon)이 먼저 쓰고 로컬은 건드리지 않는다
- 원격 실패(error·rate_limit·budget)·교정 재요청 뒤 무효(invalid) → 그 섹션만 로컬이
  local_slot 을 잡고 쓴다
- 공용 계정 run 은 internal 청크를 원격 프롬프트에 넣지 않는다(PublicOnlyRepository + 전송 범위)
- manifest: 섹션별 작성자·사유·전송 doc_id·호출 수 (본문 없음), Gemini 호출 수
- writer=local 이면 예전 흐름(로컬 먼저, run 전체가 슬롯 안)
- review.first_pass off → 1차 검토 건너뜀(self_review), 최종 검토·마무리는 그대로
- local_check: 지지|부분|불일치 판정, 불일치 → 경고, 섹션당 시간 상한 → 건너뜀
- 동시 run 3건이 실제로 겹치고, 로컬 모델 단계는 한 번에 하나
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re

import pytest

from rra.adapters.logging.file_run_log import check_manifest
from rra.application.ports.auth import BudgetExhausted
from rra.application.ports.llm import RateLimited
from rra.application.services import RunManager
from rra.application.services.run_manager import FinalizeRejected
from rra.application.services.scoped_repository import PublicOnlyRepository
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import Chunk, Document
from rra.domain.rules.lint import LintRules
from rra.domain.rules.writer import LOCAL_EVIDENCE_MISMATCH
from rra.entrypoints.views import draft_payload, run_state_payload
from tests.fakes import (
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

KEYS = ["problem", "prior_work"]
KEYS4 = ["problem", "prior_work", "objective", "method"]
USER = "local"
_SECTION = re.compile(r"\[섹션: ([^\]]+)\]")
INTERNAL_DOCS = [
    Document(
        doc_id="own:9",
        source="own",
        doc_type="internal_report",
        title="사내",
        body="내부",
        visibility="internal",
    )
]
INTERNAL_CHUNKS = [
    Chunk(chunk_id="own:9#0", doc_id="own:9", ordinal=0, text="내부 자료", visibility="internal")
]


def js(text, ev=("alio:1#0",)):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


class Limited(RateLimited):
    """어댑터의 LLMRateLimited 와 같은 자리 (429 재시도 소진)."""


class KeyedLLM:
    """프롬프트의 [섹션: key] 로 답을 고른다 — 동시 호출 순서와 무관하다. 동시 실행 수를 잰다.

    answers[key]: 문자열 | 예외 클래스·인스턴스 | 목록(차례로 꺼냄). 없으면 기본 문장
    (근거 alio:1#0).
    check: local_check 프롬프트([근거 자료])에 대한 답 함수(key → 문자열).
    delays[key]: 그 섹션 지연."""

    def __init__(self, answers=None, *, delay=0.0, delays=None, check=None, prefix=""):
        self.answers = dict(answers or {})
        self.delay, self.delays = delay, dict(delays or {})
        self.check, self.prefix = check, prefix
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        key = _SECTION.search(prompt).group(1)
        self.calls.append(prompt)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delays.get(key, self.delay))
            if "[근거 자료]" in prompt and self.check is not None:
                return self.check(key)
            ans = self.answers.get(key)
            if isinstance(ans, list):
                ans = ans.pop(0) if ans else None
            if isinstance(ans, BaseException) or (
                isinstance(ans, type) and issubclass(ans, BaseException)
            ):
                raise ans
            return ans if ans is not None else js(f"{self.prefix}{key} 문장")
        finally:
            self.active -= 1


class CountingPool:
    """GenerationSlot fake — N 칸. 동시에 들어온 수(max_active)를 잰다 (run_slot 자리)."""

    def __init__(self, size):
        self._sem = asyncio.Semaphore(size)
        self.active = 0
        self.max_active = 0

    @contextlib.asynccontextmanager
    async def acquire(self):
        async with self._sem:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                yield
            finally:
                self.active -= 1


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    r.seed(docs, chunks)
    return r


def make(
    local, repo, remote=None, *, keys=KEYS, slot=None, include_internal=True, choices=None, **kw
):
    rules = LintRules(
        template="v2026",
        sections=list(keys),
        required_sections=[k for k in keys if k not in (choices or {})],
        evidence_required=["prior_work"] if "prior_work" in keys else [],
        choices=choices or {},
    )
    return GenerateProposal(
        local,
        repo,
        FakePromptLibrary(),
        rules,
        list(keys),
        writer_llm=remote,
        writer_provider="gemini" if remote is not None else "",
        writer_model="gemini-4-argon" if remote is not None else "",
        writer_include_internal=include_internal,
        local_provider="mlx",
        local_model="qwen-7b",
        local_slot=slot,
        compose_concurrency=4,
        **kw,
    )


def manager(gen, *, slot=None, run_slot=None, reviewer=None, first_pass=True, public=None):
    log = FakeRunLog()
    mgr = RunManager(
        gen,
        InMemoryRunStore(),
        slot or FakeSlot(),
        log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T00:00:00+00:00",
        renderer=FakeRenderer(),
        reviewer=reviewer,
        max_queued=5,
        run_slot=run_slot,
        first_pass=first_pass,
        generate_public=public,
    )
    return mgr, log


# ── 작성자 전환 ─────────────────────────────────────────
async def test_argon_writes_every_section_and_the_local_model_is_untouched(req, repo):
    local, remote = KeyedLLM(), KeyedLLM(prefix="아르곤 ")
    uc = make(local, repo, remote)
    assert uc.writes_remotely and uc.writer == "gemini"
    snap = await uc.retrieve(req)
    for key in KEYS:
        composed = await uc.compose_section(key, req, snap)
        assert composed.section.sentences[0].text == f"아르곤 {key} 문장"
        assert composed.writer == {
            "provider": "gemini",
            "model": "gemini-4-argon",
            "local_fallback": False,
            "reason": None,
            "public_doc_ids": sorted({c.doc_id for c in uc.chunks_for(key, snap)}),
            "internal_doc_ids": [],
            "calls": 1,
        }
        assert composed.fallback is None and composed.retries == 0
    assert local.calls == [] and len(remote.calls) == 2


@pytest.mark.parametrize(
    ("answer", "reason", "calls"),
    [
        (ConnectionError("https://generativelanguage.googleapis.com 응답 없음"), "error", 1),
        (Limited("LLM 오류 429"), "rate_limit", 1),
        (BudgetExhausted("오늘 상한"), "budget", 0),
        (["자유 텍스트", "또 자유 텍스트"], "invalid", 2),  # 교정 재요청 뒤에도 형식 오류
    ],
)
async def test_failed_argon_section_is_written_locally_under_the_local_slot(
    req, repo, answer, reason, calls
):
    slot = FakeSlot()
    local = KeyedLLM(prefix="로컬 ")
    remote = KeyedLLM({"prior_work": answer})
    uc = make(local, repo, remote, slot=slot)
    snap = await uc.retrieve(req)
    composed = await uc.compose_section("prior_work", req, snap)
    assert composed.section.sentences[0].text == "로컬 prior_work 문장"
    w = composed.writer
    assert w["provider"] == "mlx" and w["model"] == "qwen-7b" and w["local_fallback"] is True
    assert w["reason"] == reason and w["calls"] == calls
    # 보낸 것이 없으면(예산) 전송 doc_id 도 없다
    assert bool(w["public_doc_ids"]) is (calls > 0)
    assert len(local.calls) == 1 and slot.max_active == 1
    # 원격이 성공한 섹션은 로컬 슬롯을 잡지 않는다
    slot2 = FakeSlot()
    ok = await make(KeyedLLM(), repo, KeyedLLM(), slot=slot2).compose_section("problem", req, snap)
    assert ok.writer["local_fallback"] is False and slot2.max_active == 0


async def test_argon_answer_citing_unshown_ids_is_invalid_then_local(req, repo):
    """보안 A: 원격 문장의 근거 id 는 보여 준 청크와 대조 — 전부 폐기되면 invalid → 로컬."""
    outside = js("스냅샷 밖 인용", ["ntis:nope#0"])
    remote = KeyedLLM({"prior_work": [outside, outside]})
    local = KeyedLLM(prefix="로컬 ")
    composed = await make(local, repo, remote).compose_section(
        "prior_work", req, await make(local, repo, remote).retrieve(req)
    )
    assert composed.writer["reason"] == "invalid" and composed.writer["calls"] == 2
    assert "검증에서 전부 폐기됐음" in remote.calls[1]
    assert composed.section.sentences[0].text == "로컬 prior_work 문장"


# ── 전송 범위 ───────────────────────────────────────────
async def test_transfer_scope_staff_sends_internal_public_scope_never(req, repo):
    repo.seed(INTERNAL_DOCS, INTERNAL_CHUNKS)
    staff_remote = KeyedLLM()
    staff = make(KeyedLLM(), repo, staff_remote)
    snap = await staff.retrieve(req)
    composed = await staff.compose_section("prior_work", req, snap)
    assert "own:9#0" in staff_remote.calls[0]
    assert composed.writer["internal_doc_ids"] == ["own:9"]
    # 전송 범위가 internal 제외면 같은 스냅샷이라도 프롬프트에 넣지 않는다
    guarded_remote = KeyedLLM()
    guarded = make(KeyedLLM(), repo, guarded_remote, include_internal=False)
    composed = await guarded.compose_section("prior_work", req, snap)
    assert "own:9" not in guarded_remote.calls[0]
    assert composed.writer["internal_doc_ids"] == []


async def test_guest_run_never_shows_internal_chunks_to_argon(req, repo):
    repo.seed(INTERNAL_DOCS, INTERNAL_CHUNKS)
    staff_remote, guest_remote = KeyedLLM(), KeyedLLM()
    staff = make(KeyedLLM(), repo, staff_remote)
    guest = make(KeyedLLM(), PublicOnlyRepository(repo), guest_remote, include_internal=False)
    mgr, log = manager(staff, public=guest)
    st = await mgr.submit("guest:demo", req, scope="public")
    final = await mgr.wait("guest:demo", st.run_id)
    assert final.status == "drafted" and final.writer == "gemini"
    assert guest_remote.calls and staff_remote.calls == []
    assert all("own:9" not in p and "내부 자료" not in p for p in guest_remote.calls)
    assert all(w["internal_doc_ids"] == [] for w in final.writers.values())
    snap = mgr.store.load_snapshot("guest:demo", st.run_id)
    assert all(c.visibility != "internal" for c in snap.chunks)
    manifest = log.records[-1][1]
    assert all(w["internal_doc_ids"] == [] for w in manifest["writers"])


# ── RunManager 기록·manifest·화면 ─────────────────────────
async def test_run_records_writer_per_section_in_state_manifest_and_payloads(req, repo):
    remote = KeyedLLM({"prior_work": ConnectionError("down")})
    mgr, log = manager(make(KeyedLLM(prefix="로컬 "), repo, remote))
    st = await mgr.submit(USER, req)
    final = await mgr.wait(USER, st.run_id)
    assert final.status == "drafted" and final.writer == "gemini"
    assert final.writers["problem"]["provider"] == "gemini"
    assert final.writers["prior_work"]["local_fallback"] is True
    assert final.writers["prior_work"]["reason"] == "error"
    manifest = log.records[-1][1]
    check_manifest(manifest)  # 허용목록 통과
    assert manifest["writer"] == "gemini" and manifest["local_sections"] == ["prior_work"]
    rows = {w["key"]: w for w in manifest["writers"]}
    assert rows["problem"]["public_doc_ids"] and rows["problem"]["calls"] == 1
    assert rows["prior_work"]["reason"] == "error" and rows["prior_work"]["calls"] == 1
    assert manifest["gemini_calls"] == {"compose": 2, "review": 0, "figures": 0, "total": 2}
    text = json.dumps(manifest, ensure_ascii=False)
    assert "로컬 prior_work 문장" not in text and "problem 문장" not in text
    assert mgr.store.load_usage(USER, st.run_id).gemini_calls["compose"] == 2
    payload = draft_payload(await mgr.get_draft(USER, st.run_id))
    assert payload["writers"] == {
        "problem": {
            "provider": "gemini",
            "model": "gemini-4-argon",
            "local_fallback": False,
            "reason": None,
        },
        "prior_work": {
            "provider": "mlx",
            "model": "qwen-7b",
            "local_fallback": True,
            "reason": "error",
        },
    }
    assert payload["local_sections"] == ["prior_work"] and payload["local_check"] is None
    state = run_state_payload(final)
    assert state["writer"] == "gemini" and state["local_sections"] == ["prior_work"]


async def test_writer_local_restores_the_old_local_first_flow(req, repo):
    slot = FakeSlot()
    held: list[int] = []

    class Watching(KeyedLLM):
        async def complete(self, prompt, **kw):
            held.append(slot.active)  # 로컬 작성: run 전체가 슬롯 안
            return await super().complete(prompt, **kw)

    local = Watching()
    uc = make(local, repo, None, slot=slot)
    assert not uc.writes_remotely and uc.writer == "local"
    mgr, log = manager(uc, slot=slot, run_slot=CountingPool(3))
    st = await mgr.submit(USER, req)
    final = await mgr.wait(USER, st.run_id)
    assert final.status == "drafted" and final.writer == "local"
    assert len(local.calls) == 2 and held == [1, 1]
    assert {w["provider"] for w in final.writers.values()} == {"mlx"}
    assert mgr.run_slot.max_active == 0  # run_slot 은 Argon 작성일 때만
    manifest = log.records[-1][1]
    assert manifest["writer"] == "local" and manifest["local_sections"] == []
    assert manifest["gemini_calls"]["compose"] == 0


# ── review.first_pass off ───────────────────────────────
FINAL_REPLY = json.dumps(
    {
        "sentences": [],
        "sections": [],
        "resolved": [],
        "scores": [
            {"criterion": "필요성", "score": 4, "reason": "r"},
            {"criterion": "차별성", "score": 3, "reason": "r"},
            {"criterion": "실현가능성", "score": 4, "reason": "r"},
            {"criterion": "기대효과", "score": 4, "reason": "r"},
        ],
    },
    ensure_ascii=False,
)


async def test_first_pass_off_skips_draft_review_but_final_review_and_finalize_work(req, repo):
    from rra.domain.rules.lint import ChoiceSpec
    from tests.fakes import FakeLLM

    choice = '{"choices": ["applied"], "sentences": [{"text": "응용임.", "evidence": []}]}'
    gen = make(
        KeyedLLM(),
        repo,
        KeyedLLM({"task_type": choice}),
        keys=["problem", "prior_work", "task_type"],
        choices={"task_type": ChoiceSpec(options="task_types")},
    )
    reviewer_llm = FakeLLM([FINAL_REPLY])  # 최종 검토 1회만 — 1차 검토에서 불리면 안 된다
    reviewer = ReviewDraft(
        reviewer_llm, FakePromptLibrary(), gen.rules, provider="gemini", model="argon"
    )
    mgr, log = manager(gen, reviewer=reviewer, first_pass=False)
    st = await mgr.submit(USER, req)
    final = await mgr.wait(USER, st.run_id)
    assert final.status == "drafted" and final.draft_review_skipped == "self_review"
    assert final.review_skipped is False and reviewer_llm.calls == []
    assert "draft_review" not in [s.name for s in final.steps]
    assert mgr.store.load_review(USER, st.run_id, 1).skipped_reason == "self_review"
    with pytest.raises(FinalizeRejected):  # 최종 검토 전에는 마무리 불가
        await mgr.finalize(USER, st.run_id)
    await mgr.final_review(USER, st.run_id)
    reviewed = await mgr.wait(USER, st.run_id)
    assert reviewed.status == "final_reviewed" and len(reviewer_llm.calls) == 1
    done = await mgr.finalize(USER, st.run_id)
    assert done.state.status == "finalized"
    manifest = log.records[-1][1]
    assert manifest["review"]["draft_review_skipped"] == "self_review"
    assert manifest["gemini_calls"]["review"] >= 1


# ── local_check ─────────────────────────────────────────
def _verdict(value):
    def answer(key):
        return json.dumps(
            {"support": [{"sentence_id": f"s:{key}:0", "support": value}]}, ensure_ascii=False
        )

    return answer


async def test_local_check_off_never_calls_the_local_model(req, repo):
    local = KeyedLLM(check=_verdict("불일치"))
    mgr, log = manager(make(local, repo, KeyedLLM()))
    final = await mgr.wait(USER, (await mgr.submit(USER, req)).run_id)
    assert final.local_check is None and local.calls == []
    assert log.records[-1][1]["local_check"] is None


async def test_local_check_has_no_time_cap_and_skips_only_an_error(req, repo):
    """L2(ADR 0040): 느린 섹션도 끝까지 기다린다 — 시간 때문에 건너뛰지 않는다. 오류 응답만
    건너뛴다."""
    slot = FakeSlot()

    def answer(key):
        if key == "prior_work":
            raise ConnectionError("down")
        return _verdict("불일치")(key)

    local = KeyedLLM(check=answer, delays={"problem": 0.3})
    gen = make(local, repo, KeyedLLM(), slot=slot, local_check=True)
    assert not hasattr(gen, "local_check_timeout")
    mgr, log = manager(gen, slot=slot)
    st = await mgr.submit(USER, req)
    final = await mgr.wait(USER, st.run_id)
    assert final.status == "drafted"
    assert final.local_check["checked_sections"] == ["problem"]  # 0.3초 걸려도 판정
    assert final.local_check["skipped_sections"] == ["prior_work"]  # 오류 응답만
    assert final.local_check["mismatches"] == 1
    assert final.local_check["counts"] == {"지지": 0, "부분": 0, "불일치": 1}
    assert final.local_check["seconds"] >= 0.3
    warn = [p for p in final.problems if p["code"] == LOCAL_EVIDENCE_MISMATCH]
    assert len(warn) == 1 and warn[0]["severity"] == "warning" and warn[0]["section"] == "problem"
    manifest = log.records[-1][1]
    check_manifest(manifest)
    assert manifest["local_check"] == {
        "enabled": True,
        "mismatches": 1,
        "skipped_sections": ["prior_work"],
        "sentences": 1,
        "checked_sections": ["problem"],
        "counts": {
            "supported": 0,
            "partial": 0,
            "mismatch": 1,
            "suggestions": 0,
            "suggestion_status": {},
            "seconds": final.local_check["seconds"],
            "suggest_seconds": 0.0,
        },
    }
    payload = draft_payload(await mgr.get_draft(USER, st.run_id))
    lc = payload["local_check"]
    assert {k: lc[k] for k in ("enabled", "mismatches", "skipped_sections")} == {
        "enabled": True,
        "mismatches": 1,
        "skipped_sections": ["prior_work"],
    }
    assert lc["verdicts"] == {"s:problem:0": "불일치"} and lc["unresolved"] == 1
    # 문장을 고치면 판정이 사라진다 (새 버전의 알림에서 빠진다)
    from rra.domain.models.review import EditRequest, SentenceEdit

    await mgr.apply_edits(
        USER,
        st.run_id,
        EditRequest(
            sentences=[
                SentenceEdit(sentence_id="s:problem:0", action="manual", text="고친 문장임.")
            ]
        ),
    )
    after = await mgr.status(USER, st.run_id)
    assert not [p for p in after.problems if p["code"] == LOCAL_EVIDENCE_MISMATCH]


async def test_local_check_supported_sentences_raise_no_alert(req, repo):
    local = KeyedLLM(check=_verdict("지지"))
    gen = make(local, repo, KeyedLLM(), local_check=True)
    mgr, _ = manager(gen)
    final = await mgr.wait(USER, (await mgr.submit(USER, req)).run_id)
    assert final.local_check["mismatches"] == 0 and final.local_check["sentences"] == 2
    assert not [p for p in final.problems if p["code"] == LOCAL_EVIDENCE_MISMATCH]


# ── 동시성 ───────────────────────────────────────────────
@pytest.mark.parametrize("pool_size", [3, 2])
async def test_concurrent_runs_overlap_while_local_steps_run_one_at_a_time(req, repo, pool_size):
    slot = FakeSlot()  # 로컬 모델 슬롯 — RunManager 와 유스케이스가 같은 것을 쓴다
    pool = CountingPool(pool_size)
    remote = KeyedLLM({"method": ConnectionError("down")}, delay=0.02)  # method 는 매번 로컬로
    local = KeyedLLM(prefix="로컬 ", delay=0.02)
    gen = make(local, repo, remote, keys=KEYS4, slot=slot)
    mgr, _ = manager(gen, slot=slot, run_slot=pool)
    runs = [await mgr.submit(USER, req) for _ in range(3)]
    finals = [await mgr.wait(USER, r.run_id) for r in runs]
    assert all(f.status == "drafted" for f in finals)
    assert all(f.writers["method"]["local_fallback"] for f in finals)
    assert pool.max_active == pool_size  # run 이 실제로 겹쳤다 (칸 수만큼)
    assert remote.max_active > 1  # 섹션·run 이 동시에 Argon 을 불렀다
    assert local.max_active == 1 and len(local.calls) == 3  # 로컬은 한 번에 하나


async def test_sections_of_one_run_are_written_concurrently_and_saved_in_order(req, repo):
    remote = KeyedLLM(delay=0.02)
    mgr, _ = manager(make(KeyedLLM(), repo, remote, keys=KEYS4))
    final = await mgr.wait(USER, (await mgr.submit(USER, req)).run_id)
    assert remote.max_active == 4  # compose_concurrency 4
    assert [s.name for s in final.steps if s.name.startswith("section:")] == [
        f"section:{k}" for k in KEYS4
    ]
    draft = await mgr.get_draft(USER, final.run_id)
    assert [s.key for s in draft.sections] == KEYS4


async def test_one_section_crash_interrupts_the_run_and_resume_finishes_it(req, repo):
    """원격·로컬이 모두 예외면 run 은 interrupted — 저장된 섹션은 남고 재개로 이어서 쓴다."""
    remote = KeyedLLM({"method": ConnectionError("down")})
    local = KeyedLLM({"method": [TimeoutError("로컬 서버 없음")]})
    gen = make(local, repo, remote, keys=KEYS4)
    mgr, _ = manager(gen)
    st = await mgr.submit(USER, req)
    first = await mgr.wait(USER, st.run_id)
    assert first.status == "interrupted"
    assert first.step("section:method").status == "error"
    assert first.step("section:method").error == "TimeoutError"
    resumed = await mgr.resume(USER, st.run_id)
    final = await mgr.wait(USER, resumed.run_id)
    assert final.status == "drafted" and final.writers["method"]["local_fallback"] is True
