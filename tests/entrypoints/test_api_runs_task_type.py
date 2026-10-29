"""run 목록·상태 응답의 task_type (홈·내 제안서 표의 과제유형, UI Research Studio 레인 2)."""

from __future__ import annotations

import httpx
import pytest

from tests.entrypoints.test_api import AUTH, SLOTS, build


@pytest.fixture
async def client():
    app, assistant = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.assistant = assistant  # type: ignore[attr-defined]
        yield c


async def test_list_and_status_carry_task_type_label(client):
    r = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    rid = r.json()["run_id"]
    await client.assistant.manager.wait("local", rid)
    listed = (await client.get("/v1/runs", headers=AUTH)).json()["runs"]
    assert "task_type" in listed[0]
    assert listed[0]["task_type"] in (None, "기초연구", "응용연구", "개발연구")
    c = await client.post(f"/v1/runs/{rid}/confirm", json={"task_type": "applied"}, headers=AUTH)
    assert c.status_code == 200
    listed = (await client.get("/v1/runs", headers=AUTH)).json()["runs"]
    assert listed[0]["task_type"] == "응용연구"
    one = (await client.get(f"/v1/runs/{rid}", headers=AUTH)).json()
    assert one["task_type"] == "응용연구"
