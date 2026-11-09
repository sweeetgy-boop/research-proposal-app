"""REST — 과제안 SSE (`POST /v1/precheck/recommendations/stream`, 2026-11-09 레인 A).

이벤트 순서(stage → analogies → stage → recommendations → end), 일일 상한 오류, 모르는 진행
이름은 보내지 않음, keep-alive, 끊기면 작업 취소. 라우트는 `register_recommend_stream` 으로 시험
앱에 붙인다(app.py 연결은 통합 때 — PR 설명). 가짜 recommend_full, 네트워크 없음.
"""

from __future__ import annotations

import asyncio
import json

from rra.application.ports.auth import BudgetExhausted
from rra.domain.models import ProposalRequest
from rra.domain.models.novel import Analogy, NoveltyCoverage
from rra.entrypoints.api.progress_routes import _stream, register_recommend_stream, shape_event
from tests.entrypoints.test_api import AUTH, SLOTS, build
from tests.entrypoints.test_recommend_api import client_for
from tests.entrypoints.ui.fake_app import make_assistant

COVERAGE = NoveltyCoverage(
    searched=["own", "scienceon"],
    searched_labels=["사내 과제", "ScienceON"],
    live=True,
    unavailable=[{"source": "openalex", "status": "error"}],
)
ANALOGY = Analogy(
    doc_id="openalex:W9",
    title="Bird deterrence in poultry farms",
    source="openalex",
    source_label="OpenAlex",
    domain_label="축산",
    why_relevant="'조류 침입' 문제를 함께 다룸",
    url="https://openalex.org/W9",
    year=2021,
    live=True,
    similarity=0.82,
)
FINAL = {"notice": "n", "alerts": [], "recommendations": {"id": "abc", "mode": "novel"}}


def _recommend_full(*, delay: float = 0.0, error: Exception | None = None, extra_event=None):
    seen: dict = {"progress": []}

    async def run(request, req, progress):
        seen["req"] = req
        progress("stage", {"stage": "search", "status": "started"})
        if delay:
            await asyncio.sleep(delay)
        progress("analogies", {"coverage": COVERAGE, "analogies": [ANALOGY]})
        if extra_event is not None:
            progress(*extra_event)
        progress("stage", {"stage": "generate", "status": "started"})
        if error is not None:
            raise error
        return dict(FINAL)

    return run, seen


def _app(recommend_full, *, heartbeat: float = 5.0):
    app, _ = build(make_assistant(), recommend_auto=False)
    register_recommend_stream(
        app,
        api_version="v1",
        recommend_full=recommend_full,
        clean=lambda s: s.replace("<", "〈"),
        heartbeat_sec=heartbeat,
    )
    return app


async def _read(client, body=SLOTS):
    events, comments = [], 0
    async with client.stream(
        "POST", "/v1/precheck/recommendations/stream", json=body, headers=AUTH
    ) as r:
        assert r.status_code == 200, await r.aread()
        assert r.headers["content-type"].startswith("text/event-stream")
        name = None
        async for line in r.aiter_lines():
            if line.startswith(":"):
                comments += 1
            elif line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                events.append((name, json.loads(line[6:])))
    return events, comments


async def test_events_come_in_order_analogies_before_recommendations():
    run, seen = _recommend_full()
    async with client_for(_app(run)) as c:
        events, _ = await _read(c)
    assert [e[0] for e in events] == ["stage", "analogies", "stage", "recommendations", "end"]
    assert events[0][1] == {"stage": "search", "status": "started"}
    analogies = events[1][1]
    assert analogies["mode"] == "novel"
    assert analogies["coverage"]["searched"] == ["own", "scienceon"]
    assert analogies["coverage"]["unavailable"][0]["status"] == "error"
    assert analogies["analogies"][0]["title"] == ANALOGY.title
    assert (
        analogies["analogies"][0]["domain_label"] == "축산"
        and "similarity" not in analogies["analogies"][0]
    )
    assert events[2][1] == {"stage": "generate", "status": "started"}
    assert events[3][1] == FINAL and events[4][1] == {"status": "done"}
    assert seen["req"].goal == SLOTS["goal"]


async def test_budget_exhausted_is_an_error_event_then_end():
    run, _ = _recommend_full(error=BudgetExhausted("daily"))
    async with client_for(_app(run)) as c:
        events, _ = await _read(c)
    assert [e[0] for e in events] == ["stage", "analogies", "stage", "error", "end"]
    assert events[3][1]["status"] == 409 and "한도" in events[3][1]["detail"]
    assert events[4][1] == {"status": "error"}


async def test_unexpected_failure_is_a_generic_500_without_message(caplog):
    run, _ = _recommend_full(error=RuntimeError("https://x?key=SECRET"))
    async with client_for(_app(run)) as c:
        events, _ = await _read(c)
    err = dict(events)["error"]
    assert err["status"] == 500 and "SECRET" not in json.dumps(err)
    assert any(
        "api.recommend_stream_failed kind=RuntimeError" in r.getMessage() for r in caplog.records
    )


async def test_unknown_progress_names_and_values_are_dropped():
    run, _ = _recommend_full(extra_event=("secret", {"prompt": "본문"}))
    async with client_for(_app(run)) as c:
        events, _ = await _read(c)
    assert "secret" not in [e[0] for e in events]
    assert shape_event("stage", {"stage": "prompt", "status": "started"}, clean=str) is None
    assert shape_event("stage", {"stage": "search", "status": "weird"}, clean=str) is None
    assert shape_event("nope", {}, clean=str) is None


async def test_keep_alive_comments_while_waiting():
    run, _ = _recommend_full(delay=0.12)
    async with client_for(_app(run, heartbeat=0.03)) as c:
        events, comments = await _read(c)
    assert comments >= 2 and events[-1][0] == "end"


async def test_without_llm_is_503():
    async with client_for(_app(None)) as c:
        r = await c.post("/v1/precheck/recommendations/stream", json=SLOTS, headers=AUTH)
        assert r.status_code == 503


async def test_requires_auth():
    run, _ = _recommend_full()
    async with client_for(_app(run)) as c:
        r = await c.post("/v1/precheck/recommendations/stream", json=SLOTS)
        assert r.status_code == 401


async def test_disconnect_cancels_the_work():
    """스트림을 읽다 끊으면(제너레이터 닫힘) recommend_full 작업이 취소된다. ASGITransport 는 응답을
    끝까지 모으므로 제너레이터를 직접 연다."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run(request, req, progress):
        progress("stage", {"stage": "search", "status": "started"})
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return FINAL

    gen = _stream(object(), ProposalRequest(**SLOTS), run, clean=str, heartbeat=5.0)
    first = await gen.__anext__()
    assert first.startswith(b"event: stage")
    await asyncio.wait_for(started.wait(), 1)
    await gen.aclose()  # 브라우저가 끊었다
    await asyncio.wait_for(cancelled.wait(), 2)
