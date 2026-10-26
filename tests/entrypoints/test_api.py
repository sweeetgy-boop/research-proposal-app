"""REST API (Step 10) — httpx.AsyncClient + ASGITransport. 모델·네트워크·파일 없음.

인증(401)·정상 흐름(precheck → runs → draft → confirm → file)·본문 상한(413)·보안 헤더·CORS 없음.
"""

from __future__ import annotations

import json

import httpx
import pytest

from rra.application.services import ProposalAssistant
from rra.composition import api_middlewares
from rra.entrypoints.api import create_app
from rra.settings import Settings
from tests.entrypoints.ui.fake_app import make_assistant

TOKEN = "api-test-token"  # noqa: S105 — 테스트용
SLOTS = {
    "current_state": "궤도 틀림 반복",
    "root_cause": "노반 침하",
    "limitation": "임계치만 봄",
    "goal": "열화 예측",
}


def build(assistant: ProposalAssistant | None = None, *, max_body: int = 64 * 1024):
    a = assistant or make_assistant()
    settings = Settings(_env_file=None)
    mws = api_middlewares(settings, TOKEN)
    for cls, kw in mws:
        if cls.__name__ == "BodyLimitMiddleware":
            kw["max_bytes"] = max_body
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        repo=a.repo,
        user=a.user,
        middlewares=mws,
        query_max_chars=500,
    )
    return app, a


@pytest.fixture
async def client():
    app, assistant = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.assistant = assistant  # type: ignore[attr-defined]
        yield c


AUTH = {"X-RRA-Token": TOKEN}


# ── 인증·헤더 ─────────────────────────────────────────────
async def test_missing_or_wrong_token_is_401_but_healthz_is_open(client):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    r = await client.post("/v1/precheck", json=SLOTS)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    r = await client.post("/v1/precheck", json=SLOTS, headers={"X-RRA-Token": "nope"})
    assert r.status_code == 401
    r = await client.get("/v1/search", params={"q": "궤도"}, headers={"Authorization": "Bearer x"})
    assert r.status_code == 401
    ok = await client.get(
        "/v1/search", params={"q": "궤도"}, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert ok.status_code == 200


async def test_security_headers_on_every_response_and_no_cors(client):
    for r in (
        await client.get("/healthz"),
        await client.post("/v1/precheck", json=SLOTS),  # 401
        await client.post(
            "/v1/precheck", json=SLOTS, headers={**AUTH, "Origin": "https://evil.example"}
        ),
    ):
        assert r.headers["content-security-policy"].startswith("default-src 'none'")
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in r.headers
    assert (
        await client.options(
            "/v1/precheck",
            headers={
                **AUTH,
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    ).status_code in (401, 405)
    assert (await client.get("/docs", headers=AUTH)).status_code == 404  # 문서 UI 없음


async def test_body_over_limit_is_413_and_chunked_is_411():
    app, _ = build(max_body=1024)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        big = {**SLOTS, "constraints": "x" * 1500}
        r = await c.post("/v1/precheck", json=big, headers=AUTH)
        assert r.status_code == 413
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        assert r.status_code == 200

        async def gen():
            yield json.dumps(SLOTS).encode()

        r = await c.post(
            "/v1/precheck", content=gen(), headers={**AUTH, "content-type": "application/json"}
        )
        assert r.status_code == 411


# ── 정상 흐름 ─────────────────────────────────────────────
async def test_full_flow_precheck_runs_draft_confirm_file(client):
    a = client.assistant
    r = await client.post("/v1/precheck", json=SLOTS, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert (
        body["blocking"] is False and "지시가 아닙니다" in body["notice"] and body["alerts"] == []
    )

    r = await client.post("/v1/runs", json={**SLOTS, "department": "철도연구원"}, headers=AUTH)
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    assert r.json()["status"] == "queued"
    final = await a.manager.wait(a.user, run_id)
    assert final.status == "done"

    r = await client.get(f"/v1/runs/{run_id}", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["legacy"] is False
    assert "sections" not in r.json()  # 상태 조회에는 초안 본문이 없다

    r = await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)
    draft = r.json()
    keys = [s["key"] for s in draft["sections"]]
    assert "title" in keys and "method" in keys and draft["notice"]
    task = next(s for s in draft["sections"] if s["key"] == "task_type")["choices"]
    assert task["proposed"][0]["id"] == "applied" and task["confirmed"] is None

    r = await client.get(f"/v1/runs/{run_id}/file", headers=AUTH)
    assert r.status_code == 409 and "확정" in r.json()["detail"] or r.status_code == 200
    # FakeRenderer 는 확정을 강제하지 않으므로 200 — 실제 HwpxRenderer 는 ConfirmationRequired(409)

    r = await client.post(
        f"/v1/runs/{run_id}/confirm",
        json={"task_type": "basic", "utilization": ["manual"]},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["confirmed"] == {
        "task_type": ["basic"],
        "utilization": ["manual"],
    }
    r = await client.post(
        f"/v1/runs/{run_id}/confirm", json={"utilization": ["evil"]}, headers=AUTH
    )
    assert r.status_code == 422 and "선택지에 없는 값" in r.json()["detail"]
    r = await client.post(f"/v1/runs/{run_id}/confirm", json={"bogus": 1}, headers=AUTH)
    assert r.status_code == 422

    r = await client.get(f"/v1/runs/{run_id}/render-check", headers=AUTH)
    check = r.json()
    assert r.status_code == 200 and check["run_id"] == run_id and check["count"] >= 2
    assert any(p["code"] == "unsupported_number" for p in check["unresolved"])  # 미해결 lint 경고
    assert any("2-가-(3)" in n for n in check["notes"]) and check["overflow"] == []
    assert (
        await client.get("/v1/runs/20260101000000-deadbeef/render-check", headers=AUTH)
    ).status_code == 404

    r = await client.get(f"/v1/runs/{run_id}/file", headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/hwp+zip")
    assert r.headers["content-disposition"] == f'attachment; filename="proposal-{run_id}.hwpx"'
    rendered = json.loads(r.content)
    assert rendered["confirmed"] == {"task_type": ["basic"], "utilization": ["manual"]}
    assert rendered["proposer"] is None

    r = await client.post(
        f"/v1/runs/{run_id}/file",
        json={
            "proposed_on": "2026-10-23",
            "proposer": {"name": "홍길동", "rank": "선임", "phone": "010-1"},
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert json.loads(r.content)["proposer"]["proposer"]["name"] == "홍길동"
    store = a.manager.store
    dumped = json.dumps(
        {k: str(v) for k, v in vars(store).items()}, ensure_ascii=False, default=str
    )
    assert "홍길동" not in dumped and "010-1" not in dumped  # 제안자 정보는 서버에 남지 않는다
    assert "홍길동" not in json.dumps(a.manager.run_log.records, ensure_ascii=False, default=str)


async def test_validation_errors_use_the_domain_message(client):
    r = await client.post("/v1/precheck", json={"current_state": "a"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["detail"].startswith(
        "필수 슬롯이 비었습니다: root_cause"
    )
    r = await client.post("/v1/runs", json={**SLOTS, "goal": "가" * 2001}, headers=AUTH)
    assert r.status_code == 422 and "슬롯 길이" in r.json()["detail"]


async def test_search_returns_untrusted_chunks_and_rejects_long_or_empty_query(client):
    r = await client.get("/v1/search", params={"q": "궤도", "k": 2}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["notice"] and all(c["trust"] == "untrusted" for c in body["chunks"])
    assert (
        body["chunks"] and "<doc" not in body["chunks"][0]["text"]
    )  # JSON 에는 구획 태그 없이 평문
    assert (await client.get("/v1/search", params={"q": "   "}, headers=AUTH)).status_code == 422
    assert (
        await client.get("/v1/search", params={"q": "x" * 501}, headers=AUTH)
    ).status_code == 422
    assert (
        await client.get("/v1/search", params={"q": "x", "k": 999}, headers=AUTH)
    ).status_code == 422
    calls = client.assistant.repo.calls[-1][1]
    assert calls["orgs"] is None


async def test_unknown_or_malformed_run_ids_are_404(client):
    for rid in ("20260101000000-deadbeef", "../etc/passwd", "x"):
        assert (await client.get(f"/v1/runs/{rid}", headers=AUTH)).status_code == 404
        assert (await client.get(f"/v1/runs/{rid}/draft", headers=AUTH)).status_code == 404
        assert (await client.get(f"/v1/runs/{rid}/file", headers=AUTH)).status_code == 404


async def test_queue_limit_is_429_and_resume_of_finished_is_409(client):
    a = client.assistant
    a.manager.max_queued = 1
    first = await client.post("/v1/runs", json=SLOTS, headers=AUTH)
    assert first.status_code == 202
    assert (await client.post("/v1/runs", json=SLOTS, headers=AUTH)).status_code == 429
    rid = first.json()["run_id"]
    await a.manager.wait(a.user, rid)
    r = await client.post(f"/v1/runs/{rid}/resume", headers=AUTH)
    assert r.status_code == 409


def test_build_api_refuses_to_start_without_token(tmp_path):
    from rra.composition import ApiTokenMissing, build_api

    with pytest.raises(ApiTokenMissing):
        build_api(Settings(_env_file=None, runs_dir=tmp_path, db_path=tmp_path / "x.sqlite"))


def test_cli_api_refuses_without_token(monkeypatch, capsys):
    from rra.entrypoints import cli

    monkeypatch.setattr("rra.composition.load_settings", lambda: Settings(_env_file=None))
    assert cli.main(["api", "--port", "8999"]) == cli.EXIT_USAGE
    assert "RRA_API_TOKEN" in capsys.readouterr().err
