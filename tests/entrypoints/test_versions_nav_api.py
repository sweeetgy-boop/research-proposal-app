"""레인 D 항목 21 REST — 근거 승인은 버전을 만들지 않고 버전 목록 확인 기록·변경/확인 세기에 나온다,
예전 상태만 바뀐 버전은 status_only, v1 작성자 배지, 최종 검토 [취소] 경로 (가짜 LLM)."""

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


async def drafted(client) -> str:
    r = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    assert r.status_code == 202
    rid = r.json()["run_id"]
    await client.assistant.manager.wait("local", rid)
    return rid


async def test_bulk_approve_is_a_mark_listed_in_versions_and_changes(client):
    rid = await drafted(client)
    mgr = client.assistant.manager
    before = (await client.get(f"/v1/runs/{rid}/versions", headers=AUTH)).json()["versions"]
    r = await client.post(f"/v1/runs/{rid}/evidence-decisions/bulk-approve", json={}, headers=AUTH)
    assert r.status_code == 200 and r.json()["version"] == before[-1]["version"]
    after = (await client.get(f"/v1/runs/{rid}/versions", headers=AUTH)).json()["versions"]
    assert len(after) == len(before)
    last = after[-1]
    assert last["confirmations"] >= 1 and all(m == "근거 승인" for m in last["marks"])
    assert last["status_only"] is False and "description" in last
    first = after[0]
    assert first["origin_label"] in ("로컬 작성", "Argon 작성", "Argon 작성(일부 로컬)")
    changes = (await client.get(f"/v1/runs/{rid}/changes", headers=AUTH)).json()
    assert changes["total"] == 0 and changes["confirmations"] >= 1
    assert {i["type"] for i in changes["confirm_items"]} == {"evidence_approve"}
    # 버전 파일은 그대로 — 표시는 marks 파일에만
    raw = mgr.store.load_version("local", rid, last["version"])
    assert raw.evidence_decisions == [] and len(r.json()["evidence_decisions"])


async def test_legacy_status_only_version_is_folded_with_korean_description(client):
    rid = await drafted(client)
    mgr = client.assistant.manager
    state = await mgr.status("local", rid)
    cur = mgr.store.load_version("local", rid, state.draft_version)
    # 예전 run 흉내: 내용은 같고 메모만 "그림 confirm" 인 버전 (그림이 없으면 근거 승인으로)
    from rra.domain.models import EvidenceDecision

    sent = next((s, i) for s in cur.sections for i, x in enumerate(s.sentences) if x.evidence)
    sec, idx = sent
    legacy = cur.model_copy(
        update={
            "version": cur.version + 1,
            "origin": "edit",
            "note": "근거 판단",
            "changed_sections": [sec.key],
            "evidence_decisions": [
                EvidenceDecision(
                    sentence_id=f"s:{sec.key}:{idx}",
                    evidence_id=sec.sentences[idx].evidence[0],
                    action="approve",
                )
            ],
        }
    )
    mgr.store.save_version("local", rid, legacy)
    state.draft_version = legacy.version
    mgr.store.save_state(state)
    rows = (await client.get(f"/v1/runs/{rid}/versions", headers=AUTH)).json()["versions"]
    row = rows[-1]
    assert row["status_only"] is True and row["changed_sections"] == []  # 실제로는 안 바뀜
    assert row["marks"] == ["근거 승인"]


async def test_final_review_cancel_route_rejects_when_nothing_runs(client):
    rid = await drafted(client)
    r = await client.post(f"/v1/runs/{rid}/final-review/cancel", headers=AUTH)
    assert r.status_code == 409 and "최종 검토" in r.json()["detail"]
    r = await client.post("/v1/runs/20991231000000-deadbeef/final-review/cancel", headers=AUTH)
    assert r.status_code == 404
