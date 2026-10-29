"""그림 단계의 로컬 대체 호출 = 로컬 슬롯 안 (레인 A, ADR 0032 뒤).

- Argon 작성 run 3건이 동시에 돌 때 그림 명세의 로컬 대체(Argon 실패 뒤 local LLM)는 한 번에 하나,
  Argon·Nano Banana 호출은 겹친다 (슬롯 밖)
- 로컬 작성 run 은 run 전체가 슬롯을 잡고 있으므로 그림 단계가 다시 잡지 않는다 (재진입 없음)
- [말로 고치기]·[다른 그림 추가]의 로컬 대체도 슬롯을 잡는다
FakeLLM·가짜 이미지 생성기만.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re

from rra.application.services import RunManager
from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Chunk, Document, ProposalRequest, Section, Sentence
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.rules.lint import LintRules
from tests.fakes import (
    FakeFigureRenderer,
    FakeImageGenerator,
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

USER = "local"
KEYS = ["objective", "method"]
REQ = ProposalRequest(
    current_state="궤도 틀림 점검이 수작업",
    root_cause="센서 부재",
    limitation="주기 점검만 가능",
    goal="상시 자동 감지",
)
_SECTION = re.compile(r"\[섹션: ([^\]]+)\]")
_KIND = re.compile(r"^\[그림 (?:명세|수정): ([a-z_]+)\]")
CONCEPT = {
    "boxes": [
        {"label": "현황", "lines": ["objective 문장"]},
        {"label": "문제(근본 원인)", "lines": ["method 문장"]},
        {"label": "해결 방안", "lines": ["method 문장"]},
        {"label": "기대효과", "lines": ["objective 문장"]},
    ]
}
PROCESS = {"stages": [{"name": "method 문장"}, {"name": "objective 문장"}, {"name": "method"}]}
AS_IS = {
    "as_is": [{"tag": t, "text": "objective 문장"} for t in ("현황", "원인", "한계")],
    "to_be": [{"tag": t, "text": "method 문장"} for t in ("목표", "해결 방안", "기대효과")],
    "solution": "method 문장",
}
SPECS = {"concept": CONCEPT, "process": PROCESS, "as_is_to_be": AS_IS}


class Tracking:
    """동시 실행 수를 재는 LLM fake. fail 이면 지연 뒤 ConnectionError (Argon 장애 자리)."""

    def __init__(self, *, delay=0.02, fail=False):
        self.delay, self.fail = delay, fail
        self.calls: list[str] = []
        self.active = self.max_active = 0

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(prompt)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise ConnectionError("down")
            m = _KIND.match(prompt)
            if m:  # 그림 명세·수정
                spec = SPECS.get(m.group(1), PROCESS)
                if prompt.startswith("[그림 수정"):
                    return json.dumps({"spec": None, "style": "테두리 굵게"}, ensure_ascii=False)
                return json.dumps(spec, ensure_ascii=False)
            key = _SECTION.search(prompt).group(1)  # 섹션 작성
            return json.dumps([{"text": f"{key} 문장", "evidence": []}], ensure_ascii=False)
        finally:
            self.active -= 1


class TrackingImages(FakeImageGenerator):
    def __init__(self):
        super().__init__()
        self.active = self.max_active = 0

    async def generate(self, prompt, reference, **kw):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.1)  # 그림 호출이 로컬 대체보다 길다 → run 끼리 겹친다
            return await super().generate(prompt, reference, **kw)
        finally:
            self.active -= 1


class Pool:
    """run_slot 자리 — N 칸."""

    def __init__(self, size):
        self._sem = asyncio.Semaphore(size)

    @contextlib.asynccontextmanager
    async def acquire(self):
        async with self._sem:
            yield


class CountingSlot(FakeSlot):
    def __init__(self):
        super().__init__()
        self.entered = 0

    @contextlib.asynccontextmanager
    async def acquire(self):
        async with super().acquire():
            self.entered += 1
            yield


def _repo():
    repo = InMemoryRepository()
    repo.seed(
        [Document(doc_id="alio:1", source="alio", doc_type="internal_report", title="t", body="b")],
        [Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론")],
    )
    return repo


def _figures(local, argon, images, slot):
    return MakeFigures(
        local,
        FakePromptLibrary(),
        FakeFigureRenderer(),
        images=images,
        argon=argon,
        config=FigureConfig(max_default=3),
        clock=lambda: "2026-10-28T10:00:00+00:00",
        local_slot=slot,
    )


def _manager(*, remote, slot, figures, run_slot=None):
    rules = LintRules(sections=KEYS, required_sections=KEYS, titles={k: k for k in KEYS})
    gen = GenerateProposal(
        Tracking(delay=0.0),
        _repo(),
        FakePromptLibrary(),
        rules,
        KEYS,
        writer_llm=remote,
        writer_provider="gemini" if remote is not None else "",
        writer_model="gemini-4-argon" if remote is not None else "",
        local_slot=slot,
    )
    return RunManager(
        gen,
        InMemoryRunStore(),
        slot,
        FakeRunLog(),
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T10:00:00+00:00",
        renderer=FakeRenderer(),
        max_queued=5,
        run_slot=run_slot,
        figures=figures,
    )


async def test_three_concurrent_runs_serialize_only_the_local_figure_fallback():
    slot = FakeSlot()  # RunManager·섹션 작성·그림이 같은 로컬 슬롯
    fig_local, fig_argon, images = Tracking(), Tracking(fail=True), TrackingImages()
    mgr = _manager(
        remote=Tracking(delay=0.0),
        slot=slot,
        figures=_figures(fig_local, fig_argon, images, slot),
        run_slot=Pool(3),
    )
    runs = [await mgr.submit(USER, REQ) for _ in range(3)]
    finals = await asyncio.wait_for(
        asyncio.gather(*(mgr.wait(USER, r.run_id) for r in runs)), timeout=10
    )
    assert all(f.status == "drafted" for f in finals)
    for f in finals:
        v1 = mgr.store.load_version(USER, f.run_id, 1)
        assert sorted(x.kind for x in v1.figures) == ["as_is_to_be"]  # v2 기본 (연구기간 없음)
        assert {x.spec_model for x in v1.figures} == {"local"}  # Argon 실패 → 로컬 대체
    assert len(fig_local.calls) == 3  # run 3 × 그림 1
    assert fig_local.max_active == 1  # 로컬 대체는 한 번에 하나 (슬롯 안)
    assert fig_argon.max_active > 1  # Argon 명세 호출은 run 끼리 겹친다 (슬롯 밖)
    assert images.max_active > 1  # Nano Banana 도 겹친다
    assert slot.max_active == 1


async def test_local_writer_run_does_not_reacquire_the_slot_for_figures():
    slot = CountingSlot()  # asyncio.Lock — 다시 잡으면 교착
    fig_local = Tracking(delay=0.0)
    mgr = _manager(
        remote=None,
        slot=slot,
        figures=_figures(fig_local, Tracking(delay=0.0, fail=True), FakeImageGenerator(), slot),
    )
    st = await mgr.submit(USER, REQ)
    final = await asyncio.wait_for(mgr.wait(USER, st.run_id), timeout=5)
    assert final.status == "drafted" and len(fig_local.calls) == 1  # v2 기본 As-Is/To-Be 1
    # ADR 0045 — 그림은 생성이 슬롯을 놓은 뒤 백그라운드로 그린다. 명세의 로컬 대체는 그때 슬롯을
    # 다시 잡는다(겹치지 않게 차례로 — 교착 없음)
    assert slot.entered == 2 and slot.max_active == 1


async def test_words_edit_local_fallback_takes_the_slot_but_argon_does_not():
    slot = CountingSlot()
    fig_local, fig_argon = Tracking(delay=0.0), Tracking(delay=0.0)
    uc = _figures(fig_local, fig_argon, FakeImageGenerator(), slot)
    fig = Figure(
        id="f:objective:1", kind="concept", section="objective", spec=parse_spec("concept", CONCEPT)
    )
    sections = [
        Section(key=k, sentences=[Sentence(text=f"{k} 문장")]) for k in ("objective", "method")
    ]
    await uc.edit_by_words(fig, "테두리 굵게", sections=sections, request=REQ, snapshot=None)
    assert len(fig_argon.calls) == 1 and fig_local.calls == [] and slot.entered == 0
    uc.argon = Tracking(delay=0.0, fail=True)
    await uc.edit_by_words(fig, "테두리 굵게", sections=sections, request=REQ, snapshot=None)
    assert len(fig_local.calls) == 1 and slot.entered == 1
    # 이미 잡고 있다고 알려 주면(로컬 작성 run 의 그림 단계) 잡지 않는다
    await uc.make_spec("concept", "objective", sections, REQ, None, local_held=True)
    assert len(fig_local.calls) == 2 and slot.entered == 1
