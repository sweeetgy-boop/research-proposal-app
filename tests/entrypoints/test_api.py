"""REST API (Step 10) — httpx.AsyncClient + ASGITransport. 모델·네트워크·파일 없음.

인증(401)·정상 흐름(precheck → runs → draft → confirm → file)·본문 상한(413)·보안 헤더·CORS 없음.
"""

from __future__ import annotations

import asyncio
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


def build(
    assistant: ProposalAssistant | None = None,
    *,
    max_body: int = 64 * 1024,
    static_dir=None,
    differentiate=None,
    recommend=None,
    recommend_auto=True,
):
    from rra.adapters.security import SessionStore
    from rra.entrypoints.api.app import SessionAuth

    a = assistant or make_assistant()
    settings = Settings(_env_file=None)
    sessions = SessionStore()
    mws = api_middlewares(settings, TOKEN, sessions=sessions)
    for cls, kw in mws:
        if cls.__name__ == "BodyLimitMiddleware":
            kw["max_bytes"] = max_body
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        differentiate=differentiate,
        recommend=recommend,
        recommend_auto=recommend_auto,
        repo=a.repo,
        user=a.user,
        middlewares=mws,
        query_max_chars=500,
        session_auth=SessionAuth(TOKEN, sessions),
        static_dir=static_dir,
        sse_poll_sec=0.01,
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
def _check_header(r):
    return json.loads(r.headers["x-rra-check"])


async def _read_sse(client, run_id, *, max_events=50):
    events = []
    async with client.stream("GET", f"/v1/runs/{run_id}/events", headers=AUTH) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                lines = raw.splitlines()
                name = next((ln[7:] for ln in lines if ln.startswith("event: ")), "message")
                data = next((ln[6:] for ln in lines if ln.startswith("data: ")), "{}")
                events.append((name, json.loads(data)))
                if name == "end" or len(events) >= max_events:
                    return events
    return events


async def test_full_flow_precheck_runs_sse_review_edits_finalize(client):
    """precheck → runs → SSE 완료 → review(건너뜀) → edits → review 2차 → finalize 파일."""
    a = client.assistant
    r = await client.post("/v1/precheck", json=SLOTS, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert (
        body["blocking"] is False and "지시가 아닙니다" in body["notice"] and body["alerts"] == []
    )
    assert body["related_research"] == []  # 관련 연구(참고) 목록은 항상 있다 (ADR 0028)
    r = await client.get("/v1/sources/status", headers=AUTH)
    rows = {s["source"]: s for s in r.json()["sources"]}
    assert rows["alio"]["count"] == 1 and rows["ntis"]["count"] == 0 and rows["ntis"]["label"]
    assert rows["alio"]["last_ingested"] == "2026-10-26"
    r = await client.post("/v1/search", json={"query": "궤도", "k": 2}, headers=AUTH)
    assert r.status_code == 200 and r.json()["chunks"]

    r = await client.post("/v1/runs", json={**SLOTS, "department": "철도연구원"}, headers=AUTH)
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    assert r.json()["status"] == "queued"
    events = await _read_sse(client, run_id)  # SSE 로 완료까지
    assert events[-1][0] == "end" and events[-1][1]["status"] == "drafted"
    assert all(e[1]["run_id"] == run_id for e in events[:-1])
    assert (
        events[-2][1]["status"] == "drafted"
        and events[-2][1]["progress"][0] == events[-2][1]["progress"][1]
    )
    r = await client.get(f"/v1/runs/{run_id}", headers=AUTH)  # 끊겨도 GET 으로 복구
    assert r.status_code == 200 and r.json()["status"] == "drafted" and r.json()["legacy"] is False
    assert "sections" not in r.json()  # 상태 조회에는 초안 본문이 없다
    r = await client.get("/v1/runs", headers=AUTH)
    assert [x["run_id"] for x in r.json()["runs"]] == [run_id]

    r = await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)
    draft = r.json()
    keys = [s["key"] for s in draft["sections"]]
    assert "title" in keys and "method" in keys and draft["notice"]
    assert draft["version"] == 1 and draft["versions"] == [1]
    assert draft["review"]["skipped"] is True and draft["review"]["rounds"] == 0  # 검토 LLM 없음
    task = next(s for s in draft["sections"] if s["key"] == "task_type")["choices"]
    assert task["proposed"][0]["id"] == "applied" and task["confirmed"] is None

    assert (
        draft["flow"]["draft_review_skipped"] == "no_review_llm" and draft["flow"]["stale"] is False
    )
    named = [e[0] for e in events]
    assert "draft_written" in named and "draft_ready" in named and "pipeline_step" in named
    r = await client.post(f"/v1/runs/{run_id}/review", headers=AUTH)  # 1차: 검토 LLM 없음 → 건너뜀
    assert r.status_code == 202 and r.json()["status"] == "drafted"
    r = await client.get(f"/v1/runs/{run_id}/draft-review", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "skipped" and r.json()["kind"] == "draft"
    r = await client.get(f"/v1/runs/{run_id}/review", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    assert (
        await client.get(f"/v1/runs/{run_id}/review", params={"round": 9}, headers=AUTH)
    ).status_code == 404
    assert (await client.get(f"/v1/runs/{run_id}/final-review", headers=AUTH)).status_code == 404

    # ④ 임시 저장(버전 아님) → 저장(새 버전) → 임시 사본 삭제
    r = await client.get(f"/v1/runs/{run_id}/draft/working", headers=AUTH)
    assert r.status_code == 404
    r = await client.put(
        f"/v1/runs/{run_id}/draft/working",
        json={"sections": [{"key": "method", "text": "임시로 고친 문장."}]},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["saved"] is True
    r = await client.get(f"/v1/runs/{run_id}/draft/working", headers=AUTH)
    assert r.status_code == 200 and r.json()["working"]["sections"][0]["key"] == "method"
    assert (await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()["flow"][
        "has_working"
    ]
    r = await client.post(
        f"/v1/runs/{run_id}/versions",
        json={
            "sentences": [
                {"sentence_id": "s:method:0", "action": "manual", "text": "직접 고친 방법 문장."}
            ],
            "note": "1차 수정",
            "base_version": 1,
        },
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["status"] == "editing"
    assert r.json()["origin"] == "edit" and r.json()["origin_label"] == "제안자 편집"
    assert r.json()["changed_sections"] == ["method"] and r.json()["note"] == "1차 수정"
    method = next(s for s in r.json()["sections"] if s["key"] == "method")
    assert (
        method["sentences"][0]["origin"] == "proposer_edit"
        and method["sentences"][0]["text"] == "직접 고친 방법 문장."
    )
    assert (await client.get(f"/v1/runs/{run_id}/draft/working", headers=AUTH)).status_code == 404
    # 동시 편집 보호: 기준 버전이 다르면 409
    r = await client.post(
        f"/v1/runs/{run_id}/versions",
        json={
            "sentences": [{"sentence_id": "s:method:0", "action": "manual", "text": "또 고침."}],
            "base_version": 1,
        },
        headers=AUTH,
    )
    assert r.status_code == 409 and "v1" in r.json()["detail"]
    # 같은 내용 저장 → 새 버전 없음 (호환 경로 /edits)
    r = await client.post(
        f"/v1/runs/{run_id}/edits",
        json={"sentences": [{"sentence_id": "s:method:0", "action": "keep"}]},
        headers=AUTH,
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    r = await client.get(f"/v1/runs/{run_id}/versions", headers=AUTH)
    assert [v["version"] for v in r.json()["versions"]] == [1, 2]
    assert r.json()["versions"][1]["origin_label"] == "제안자 편집"
    r = await client.get(
        f"/v1/runs/{run_id}/versions/diff", params={"from": 1, "to": 2}, headers=AUTH
    )
    assert r.status_code == 200 and [d["section"] for d in r.json()["sections"]] == ["method"]
    assert r.json()["sections"][0]["added"][0]["text"] == "직접 고친 방법 문장."
    assert (
        await client.get(
            f"/v1/runs/{run_id}/versions/diff", params={"from": 1, "to": 9}, headers=AUTH
        )
    ).status_code == 404
    r = await client.get(f"/v1/runs/{run_id}/draft", params={"version": 1}, headers=AUTH)
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["origin"] == "local"
    assert (
        await client.get(f"/v1/runs/{run_id}/draft", params={"version": 9}, headers=AUTH)
    ).status_code == 404
    r = await client.put(f"/v1/runs/{run_id}/draft/working", json={"sections": []}, headers=AUTH)
    assert r.status_code == 200
    r = await client.post(f"/v1/runs/{run_id}/final-review", headers=AUTH)  # 임시 편집 있음 → 409
    assert r.status_code == 409 and "임시" in r.json()["detail"]
    r = await client.request("DELETE", f"/v1/runs/{run_id}/draft/working", headers=AUTH)
    assert r.status_code == 204
    r = await client.post(f"/v1/runs/{run_id}/final-review", headers=AUTH)  # 검토 LLM 없음 → 409
    assert r.status_code == 409 and "검토 LLM" in r.json()["detail"]
    r = await client.post(f"/v1/runs/{run_id}/versions/1/restore", headers=AUTH)
    assert r.status_code == 200 and r.json()["version"] == 3 and r.json()["reverted_from"] == 1
    assert r.json()["origin"] == "revert"
    r = await client.post(f"/v1/runs/{run_id}/revert", json={"to": 2}, headers=AUTH)  # 호환 경로
    assert r.status_code == 200 and r.json()["version"] == 4 and r.json()["reverted_from"] == 2

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
    assert r.headers["content-type"].startswith("application/problem+json")
    r = await client.post(f"/v1/runs/{run_id}/confirm", json={"bogus": 1}, headers=AUTH)
    assert r.status_code == 422

    r = await client.get(f"/v1/runs/{run_id}/render-check", headers=AUTH)
    check = r.json()
    assert r.status_code == 200 and check["run_id"] == run_id and check["count"] >= 1
    assert any("2-가-(3)" in n for n in check["notes"]) and check["overflow"] == []

    r = await client.post(
        f"/v1/runs/{run_id}/finalize",
        json={
            "proposed_on": "2026-10-23",
            "department": "철도연구원 기술연구처",
            "proposer": {"name": "홍길동", "rank": "선임", "phone": "010-1"},
        },
        headers=AUTH,
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/hwp+zip")
    assert r.headers["content-disposition"] == f'attachment; filename="proposal-{run_id}-v4.hwpx"'
    assert r.headers["x-rra-status"] == "finalized" and r.headers["x-rra-version"] == "4"
    assert _check_header(r)["count"] >= 1
    rendered = json.loads(r.content)
    assert rendered["confirmed"] == {"task_type": ["basic"], "utilization": ["manual"]}
    assert rendered["proposer"]["proposer"]["name"] == "홍길동"
    assert rendered["proposer"]["department"] == "철도연구원 기술연구처"
    store = a.manager.store
    dumped = json.dumps(
        {k: str(v) for k, v in vars(store).items()}, ensure_ascii=False, default=str
    )
    assert "홍길동" not in dumped and "010-1" not in dumped  # 제안자 정보는 서버에 남지 않는다
    assert "홍길동" not in json.dumps(a.manager.run_log.records, ensure_ascii=False, default=str)
    assert (await client.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["status"] == "finalized"
    r = await client.post(f"/v1/runs/{run_id}/reopen", headers=AUTH)
    assert r.status_code == 200 and r.json()["status"] == "editing"
    r = await client.post(f"/v1/runs/{run_id}/reopen", headers=AUTH)
    assert r.status_code == 409 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "상태 충돌" and "finalized" in r.json()["detail"]
    # 다시 마무리 → 새 파일 (본문 없이도 된다: 제안값·기존 확정값). 버전을 골라 마무리할 수도 있다
    r = await client.post(f"/v1/runs/{run_id}/finalize", json={"version": 2}, headers=AUTH)
    assert r.status_code == 200 and r.headers["x-rra-version"] == "2"
    assert (
        await client.get(f"/v1/runs/{run_id}/file", headers=AUTH)
    ).status_code == 404  # 옛 경로 없음


async def test_session_cookie_login_csrf_and_logout(client):
    r = await client.post("/v1/session", json={"token": "nope"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    assert not r.cookies.get("rra_session")
    r = await client.post("/v1/session", json={"token": TOKEN})
    assert r.status_code == 200 and r.json()["csrf"]
    cookie = r.headers["set-cookie"]
    assert "rra_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    csrf = r.json()["csrf"]
    jar = {"rra_session": r.cookies["rra_session"]}
    assert (await client.get("/v1/runs", cookies=jar)).status_code == 200  # 쿠키로 조회
    r = await client.post("/v1/precheck", json=SLOTS, cookies=jar)  # 상태 변경(POST)엔 CSRF 필수
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    r = await client.post("/v1/precheck", json=SLOTS, cookies=jar, headers={"X-RRA-CSRF": "wrong"})
    assert r.status_code == 403
    r = await client.post("/v1/precheck", json=SLOTS, cookies=jar, headers={"X-RRA-CSRF": csrf})
    assert r.status_code == 200
    assert (await client.get("/v1/runs", cookies={"rra_session": "forged"})).status_code == 401
    r = await client.request("DELETE", "/v1/session", cookies=jar, headers={"X-RRA-CSRF": csrf})
    assert r.status_code == 204
    assert (await client.get("/v1/runs", cookies=jar)).status_code == 401  # 세션 소멸


async def test_problem_json_shape_for_404_and_422(client):
    r = await client.get("/v1/runs/20260101000000-deadbeef", headers=AUTH)
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body == {
        "type": "about:blank",
        "title": "없음",
        "status": 404,
        "detail": "run 을 찾을 수 없습니다.",
    }
    r = await client.post("/v1/precheck", json={"current_state": "a"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["title"] == "입력 오류"
    r = await client.post("/v1/precheck", json=SLOTS)
    assert r.status_code == 401 and r.json()["status"] == 401 and "인증" in r.json()["detail"]


async def test_static_spa_served_with_fallback_and_relaxed_csp(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    app, _ = build(static_dir=dist)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/")
        assert r.status_code == 200 and "id=app" in r.text  # 인증 없이 로그인 화면을 보여야 한다
        assert r.headers["content-security-policy"].startswith("default-src 'self'")
        assert "'unsafe-inline'" not in r.headers["content-security-policy"]
        r = await c.get("/assets/app.js")
        assert r.status_code == 200 and "console" in r.text
        r = await c.get("/runs/20260101000000-deadbeef")  # SPA 라우팅 → index.html
        assert r.status_code == 200 and "id=app" in r.text
        assert (await c.get("/../secret.txt")).status_code in (200, 404)
        assert "nope" not in (await c.get("/..%2Fsecret.txt")).text
        r = await c.get("/v1/runs")  # API 는 여전히 인증 필수 + 'none' CSP
        assert r.status_code == 401 and r.headers["content-security-policy"].startswith(
            "default-src 'none'"
        )
    app2, _ = build(static_dir=tmp_path / "missing")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t") as c:
        r = await c.get("/")
        assert r.status_code == 404 and "web/dist" in r.json()["detail"]


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
        assert (await client.post(f"/v1/runs/{rid}/finalize", headers=AUTH)).status_code == 404
        assert (await client.get(f"/v1/runs/{rid}/review", headers=AUTH)).status_code == 404


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


# ── 가짜 모드 (RRA_FAKE_LLM=1) — composition 이 가짜 LLM(작성·검토)·메모리 저장소를 끼운다 ──
async def test_fake_mode_runs_the_whole_flow_deterministically_without_db_or_model(tmp_path):
    from pydantic import SecretStr

    from rra.composition import build_api

    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never-created.sqlite",
        static_dir=tmp_path / "no-dist",
    )
    app = build_api(settings, sse_poll_sec=0.01)
    assert app.state.fake_mode is True
    assert not (tmp_path / "never-created.sqlite").exists()  # DB 를 만들지 않는다
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        assert r.status_code == 200
        r = await c.post("/v1/runs", json=SLOTS, headers=AUTH)
        run_id = r.json()["run_id"]
        events = await _read_sse(c, run_id)
        assert events[-1][1]["status"] in ("drafted", "draft_reviewing")
        # 자동 1차 검토(가짜 Argon)까지 기다린다
        for _ in range(200):
            status = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["status"]
            if (
                status == "drafted"
                and (await c.get(f"/v1/runs/{run_id}/review", headers=AUTH)).status_code == 200
            ):
                break
            await asyncio.sleep(0.01)
        assert status == "drafted"
        review = (await c.get(f"/v1/runs/{run_id}/draft-review", headers=AUTH)).json()
        assert review["round"] == 1 and review["kind"] == "draft"
        assert review["transfer"]["provider"] == "gemini"
        # ③ 검증 통과 수정안은 v2 에 자동 반영 (Argon 보완) — 의견은 resolved
        assert review["applied_ids"] and review["applied_version"] == 2
        assert review["transfer"]["internal_doc_ids"] == [
            "alio:fake-1"
        ]  # include_internal 기본 true
        draft = (await c.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
        assert draft["version"] == 2 and draft["versions"] == [1, 2]
        method = next(s for s in draft["sections"] if s["key"] == "method")
        assert method["sentences"][0]["origin"] == "argon"
        v2 = (await c.get(f"/v1/runs/{run_id}/draft", params={"version": 2}, headers=AUTH)).json()
        assert v2["origin"] == "argon" and v2["origin_label"] == "Argon 보완"
        assert any(a["kind"] == "section" for a in v2["annotations"])  # 섹션 의견은 메모로
        # ④ 저장 → ⑤ 최종 검토(가짜 Argon) → final_reviewed
        r = await c.post(
            f"/v1/runs/{run_id}/versions",
            json={
                "sentences": [
                    {"sentence_id": "s:method:0", "action": "manual", "text": "제안자가 고친 문장."}
                ],
                "note": "검토 전 수정",
            },
            headers=AUTH,
        )
        assert r.status_code == 200 and r.json()["version"] == 3
        r = await c.post(f"/v1/runs/{run_id}/final-review", headers=AUTH)
        assert r.status_code == 202 and r.json()["status"] == "final_reviewing"
        for _ in range(200):
            status = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["status"]
            if status == "final_reviewed":
                break
            await asyncio.sleep(0.01)
        assert status == "final_reviewed"
        final = (await c.get(f"/v1/runs/{run_id}/final-review", headers=AUTH)).json()
        assert (
            final["kind"] == "final" and final["final_round"] == 1 and final["draft_version"] == 3
        )
        flow = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["flow"]
        assert flow["final_reviews"] == 1 and flow["final_reviewed_version"] == 3
        r = await c.post(
            f"/v1/runs/{run_id}/finalize",
            json={
                "proposer": {"name": "홍길동", "phone": "042-000-0000"},
                "department": "철도연구원 기술연구처",
            },
            headers=AUTH,
        )
        assert r.status_code == 200 and r.headers["x-rra-status"] == "finalized"
        assert len(r.content) > 1000  # 실제 HWPX 렌더러(생성 모드)가 만든 파일
        assert (await c.get("/v1/sources/status", headers=AUTH)).json()["sources"][0]["count"] >= 0


# ── 기능 2: POST /v1/precheck/differentiate ────────────────
class _FakeDifferentiate:
    def __init__(self):
        self.calls = []

    async def __call__(self, req, alerts):
        from rra.domain.models import DifferentiationItem, DifferentiationProposal

        self.calls.append((req, alerts))
        return DifferentiationProposal(
            items=[
                DifferentiationItem(
                    doc_id="alio:1",
                    title='궤도 <doc id="x">',
                    tier="own",
                    status="rejected",
                    overlap_summary="대상이 겹침",
                    build_on="결과를 이어받음",
                    differentiation=["범위를 확장함"],
                    evidence=["alio:1"],
                )
            ],
            provider="gemini",
            model="argon",
            internal_doc_ids=["alio:1"],
            calls=1,
        )


async def test_differentiate_route_returns_alerts_and_sanitized_items():
    fake = _FakeDifferentiate()
    app, _ = build(make_assistant(blocking=True), differentiate=fake)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        r = await c.post("/v1/precheck/differentiate", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["blocking"] is True and body["alerts"][0]["doc_id"] == "alio:1"
        d = body["differentiation"]
        assert d["items"][0]["status"] == "rejected" and d["items"][0]["differentiation"] == [
            "범위를 확장함"
        ]
        assert d["transfer"]["internal_doc_ids"] == ["alio:1"] and d["provider"] == "gemini"
        assert fake.calls and fake.calls[0][0].goal == SLOTS["goal"]
        r = await c.post("/v1/precheck/differentiate", json={"goal": "x"}, headers=AUTH)
        assert r.status_code == 422


async def test_differentiate_route_is_503_without_llm(client):
    r = await client.post("/v1/precheck/differentiate", json=SLOTS, headers=AUTH)
    assert r.status_code == 503 and "LLM" in r.json()["detail"]


async def test_precheck_route_attaches_differentiation_when_blocking_and_run_records_transfer():
    fake = _FakeDifferentiate()
    app, assistant = build(make_assistant(blocking=True), differentiate=fake)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        r = await c.post("/v1/precheck", json=SLOTS, headers=AUTH)
        body = r.json()
        assert body["blocking"] and body["differentiation"]["items"][0]["doc_id"] == "alio:1"
        assert body["alerts"][0]["tier_label"] == "사내(철도연구원)"
        transfer = body["differentiation"]["transfer"]
        payload = {
            **SLOTS,
            "differentiation": body["differentiation"]["items"][0]["differentiation"][0],
            "differentiation_transfer": {
                **transfer,
                "provider": "gemini",
                "model": "argon",
                "items": 1,
            },
        }
        r = await c.post("/v1/runs", json=payload, headers=AUTH)
        assert r.status_code == 409 and "acknowledged" in r.json()["detail"]  # 서버도 게이트
        r = await c.post("/v1/runs", json={**payload, "acknowledged": True}, headers=AUTH)
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]
        await assistant.manager.wait(assistant.user, run_id)
        manifests = [m for rid, m in assistant.manager.run_log.records if rid == run_id]
        assert manifests[-1]["differentiation"]["internal_doc_ids"] == ["alio:1"]
        assert manifests[-1]["differentiation"]["chosen"] is True
        from rra.adapters.logging import check_manifest

        check_manifest(manifests[-1])
        bad = {**SLOTS, "differentiation_transfer": {"provider": "x", "secret": "no"}}
        assert (await c.post("/v1/runs", json=bad, headers=AUTH)).status_code == 422


async def test_precheck_route_without_blocking_has_no_differentiation(client):
    r = await client.post("/v1/precheck", json=SLOTS, headers=AUTH)
    assert r.status_code == 200 and "differentiation" not in r.json()
