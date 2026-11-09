"""novel 과제안 응답 시간 (2026-11-09 레인 A) — 새로움 확인 ∥ 유추 검색 ∥ 참고 논문 동시 실행,
부분 실패·시간 초과는 그 협력자만 빠짐, 진행 콜백 순서(사례 먼저 → 작성), 같은 입력 재사용(메모),
측정 줄 단계 칸. FakeLLM, 네트워크 없음."""

from __future__ import annotations

import asyncio
import time

from rra.application.ports.auth import BudgetExhausted
from rra.application.usecases.novel_contract import NoveltyOutcome
from rra.application.usecases.recommend_projects import (
    PROGRESS_ANALOGIES,
    PROGRESS_STAGE,
    STAGE_ANALOGY,
    STAGE_GENERATE,
    STAGE_SEARCH,
)
from rra.domain.models.novel import NoveltyCoverage
from rra.domain.rules.recommend_metrics import STAGE_FIELDS
from tests.application.test_recommend_metrics import MemoryMetrics
from tests.application.test_recommend_novel import (
    ANALOGY,
    DIFFERENT,
    NEW_ALERT,
    REQ,
    StubAnalogies,
    StubNovelty,
    diff_reply,
    make,
    plan,
    reply,
)


class SlowNovelty(StubNovelty):
    def __init__(self, delay: float, **kw):
        super().__init__(**kw)
        self.delay = delay
        self.started: list[float] = []

    async def __call__(self, req, alerts, *, core_keywords=None):
        self.started.append(time.perf_counter())
        await asyncio.sleep(self.delay)
        return await super().__call__(req, alerts, core_keywords=core_keywords)


class SlowAnalogies(StubAnalogies):
    def __init__(self, delay: float, **kw):
        super().__init__(**kw)
        self.delay = delay
        self.started: list[float] = []

    async def __call__(self, req, *, core_keywords=None):
        self.started.append(time.perf_counter())
        await asyncio.sleep(self.delay)
        return await super().__call__(req, core_keywords=core_keywords)


def _progress():
    seen: list[tuple[str, dict]] = []
    return seen, (lambda name, data: seen.append((name, data)))


async def test_novelty_and_analogies_run_concurrently_and_metrics_have_stage_seconds():
    novelty, analogies = SlowNovelty(0.2), SlowAnalogies(0.2)
    uc, _ = make([reply([plan()])], novelty=novelty, analogies=analogies)
    uc.metrics = MemoryMetrics()
    started = time.perf_counter()
    out = await uc(REQ, [DIFFERENT], similar_only=True, core_keywords=["비둘기"])
    elapsed = time.perf_counter() - started
    assert out.mode == "novel" and [a.doc_id for a in out.analogies] == ["openalex:W9"]
    assert elapsed < 0.36  # 순차(0.4+)가 아니라 동시
    assert abs(novelty.started[0] - analogies.started[0]) < 0.05  # 거의 같이 출발
    (row,) = uc.metrics.rows
    assert set(STAGE_FIELDS) <= set(row)
    assert 0.2 <= row["seconds_search"] < 0.35 and 0.2 <= row["seconds_analogy"] < 0.35
    assert row["seconds_generate"] is not None and row["seconds_generate"] >= 0
    assert row["branch"] == "novel"


async def test_progress_sends_analogies_before_generation_and_nothing_secret():
    seen, progress = _progress()
    uc, llm = make([reply([plan()])], novelty=StubNovelty(), analogies=StubAnalogies())
    out = await uc(REQ, [DIFFERENT], similar_only=True, progress=progress)
    names = [n for n, _ in seen]
    assert names == [PROGRESS_STAGE, PROGRESS_ANALOGIES, PROGRESS_STAGE]
    assert seen[0][1] == {"stage": STAGE_SEARCH, "status": "started"}
    analog = seen[1][1]
    assert analog["coverage"] == out.coverage and [a.doc_id for a in analog["analogies"]] == [
        "openalex:W9"
    ]
    assert seen[2][1] == {"stage": STAGE_GENERATE, "status": "started"}
    assert all("prompt" not in d for _, d in seen) and llm.calls  # 프롬프트는 콜백에 없다


async def test_progress_on_revert_reports_reverted_and_no_analogies_event():
    seen, progress = _progress()
    novelty = StubNovelty(NoveltyOutcome(coverage=NoveltyCoverage(), new_alerts=[NEW_ALERT]))
    uc, _ = make([diff_reply("보완 과제")], novelty=novelty, analogies=StubAnalogies())
    out = await uc(REQ, [DIFFERENT], similar_only=True, progress=progress)
    assert out.novelty_reverted is True
    assert [(n, d.get("status")) for n, d in seen] == [
        (PROGRESS_STAGE, "started"),
        (PROGRESS_STAGE, "reverted"),
        (PROGRESS_STAGE, "started"),
    ]
    assert seen[-1][1]["stage"] == STAGE_GENERATE


async def test_progress_callback_errors_never_break_the_recommendation():
    def boom(name, data):
        raise RuntimeError("ui gone")

    uc, _ = make([reply([plan()])], novelty=StubNovelty(), analogies=StubAnalogies())
    out = await uc(REQ, [DIFFERENT], similar_only=True, progress=boom)
    assert out.mode == "novel" and len(out.novel) == 1


async def test_one_collaborator_failing_or_slow_does_not_block_the_other(caplog):
    # 새로움 확인 실패 → 저장 자료만, 유추 사례는 그대로
    uc, _ = make(
        [reply([plan()])],
        novelty=StubNovelty(error=RuntimeError("x")),
        analogies=SlowAnalogies(0.05),
    )
    out = await uc(REQ, [DIFFERENT], similar_only=True)
    assert out.coverage.live is False and [a.doc_id for a in out.analogies] == ["openalex:W9"]
    # 유추 검색 실패 → 사례 없이, 확인 범위는 그대로
    uc, _ = make(
        [reply([plan(evidence=["scienceon:P1"])])],
        novelty=SlowNovelty(0.05),
        analogies=StubAnalogies(error=TimeoutError()),
    )
    out = await uc(REQ, [DIFFERENT], similar_only=True)
    assert out.coverage.live is True and out.analogies == []
    assert any(
        "recommend.analogies_failed kind=TimeoutError" in r.getMessage() for r in caplog.records
    )


async def test_budget_exhausted_in_novelty_cancels_the_analogy_task():
    analogies = SlowAnalogies(0.5)
    uc, _ = make([], novelty=StubNovelty(error=BudgetExhausted("daily")), analogies=analogies)
    try:
        await uc(REQ, [DIFFERENT], similar_only=True)
    except BudgetExhausted:
        pass
    else:
        raise AssertionError("BudgetExhausted 가 올라와야 한다")
    await asyncio.sleep(0.05)
    assert analogies.calls == 0  # 0.5초 자다 취소됨 — super().__call__ 에 닿지 않았다


async def test_analogy_overlapping_a_reference_paper_is_dropped_after_concurrent_fetch():
    req = REQ.model_copy(update={"reference_ids": ["openalex:W9"]})
    analogies = StubAnalogies(found=[ANALOGY])
    uc, llm = make([reply([plan()])], novelty=StubNovelty(), analogies=analogies)
    seen, progress = _progress()
    out = await uc(req, [DIFFERENT], similar_only=True, progress=progress)
    assert out.analogies == [] and out.reference_doc_ids == ["openalex:W9"]
    assert seen[1][1]["analogies"] == []  # 진행 이벤트도 최종 응답과 같다
    assert "[참고 논문]" in llm.calls[0] and 'kind="analogy"' not in llm.calls[0]


async def test_same_input_reuses_collaborator_results_within_session():
    """협력자의 메모(usecases/novelty._Memo)는 협력자 안에 있다 — 여기서는 같은 입력으로 두 번
    불러도 추천이 협력자를 그대로 부르고(메모는 협력자 몫), 결과 모양이 같은지 본다."""
    novelty, analogies = StubNovelty(), StubAnalogies()
    uc, _ = make([reply([plan()]), reply([plan()])], novelty=novelty, analogies=analogies)
    first = await uc(REQ, [DIFFERENT], similar_only=True)
    second = await uc(REQ, [DIFFERENT], similar_only=True)
    assert first.coverage == second.coverage and len(novelty.calls) == 2 and analogies.calls == 2


async def test_differentiate_metrics_have_search_and_generate_but_no_analogy():
    uc, _ = make([diff_reply("차별화 안")])
    uc.metrics = MemoryMetrics()
    blocked = DIFFERENT.model_copy(update={"blocking": True, "doc_id": "ntis:b"})
    await uc(REQ, [blocked], similar_only=True)
    (row,) = uc.metrics.rows
    assert row["branch"] == "differentiate"
    assert row["seconds_search"] is not None and row["seconds_generate"] is not None
    assert row[f"seconds_{STAGE_ANALOGY}"] is None
