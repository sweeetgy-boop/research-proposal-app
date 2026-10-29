"""ADR 0045 REST — GET /v1/runs/{id} 의 그림 작업 필드(figures_status·figure_slots·두 시간),
GET /v1/runs/{id}/sections-progress, 그리는 중 그림 동작 409."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.entrypoints.test_api_figures import AUTH, SLOTS
from tests.entrypoints.test_api_figures_v2 import PMI, PUGH, build
from tests.fakes import FakeImageGenerator
from tests.figure_v2_helpers import RoutingLLM, picks


class Gate(FakeImageGenerator):
    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()

    async def generate(self, prompt, reference, **kw):
        await self.gate.wait()
        return await super().generate(prompt, reference, **kw)


@pytest.fixture
async def client():
    argon = RoutingLLM(picks=picks("pugh"), techniques={"pugh": PUGH, "pmi": PMI})
    app, mgr = build(argon)
    images = Gate()
    mgr.figures.images = images
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.mgr, c.images = mgr, images  # type: ignore[attr-defined]
        yield c


async def test_run_state_exposes_figure_job_and_timings(client):
    r = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]

    async def drawing():
        while True:
            body = (await client.get(f"/v1/runs/{rid}", headers=AUTH)).json()
            if body["status"] == "drafted" and body["figures_status"] == "drawing":
                return body
            await asyncio.sleep(0.01)

    body = await asyncio.wait_for(drawing(), 5)
    assert body["draft_visible_seconds"] is not None and body["figures_done_seconds"] is None
    slots = body["figure_slots"]
    assert slots and {s["status"] for s in slots} == {"drawing"}
    assert set(slots[0]) == {"slot_id", "kind", "section", "display_name", "status", "reason_label"}
    # 그리는 중인 자리 동작은 409 + 한국어 안내
    r = await client.post(
        f"/v1/runs/{rid}/figures/{slots[0]['slot_id']}", json={"action": "confirm"}, headers=AUTH
    )
    assert r.status_code == 409 and "그리는 중" in r.text
    # 작성 중 섹션 먼저 보기 — 생성은 끝났으니 남은 섹션 없음
    prog = (await client.get(f"/v1/runs/{rid}/sections-progress", headers=AUTH)).json()
    assert prog["pending"] == [] and prog["sections"] and prog["notice"]
    client.images.gate.set()
    await client.mgr.wait("local", rid)
    body = (await client.get(f"/v1/runs/{rid}", headers=AUTH)).json()
    assert body["figures_status"] == "done" and body["figure_slots"] == []
    assert body["figures_done_seconds"] >= body["draft_visible_seconds"]
