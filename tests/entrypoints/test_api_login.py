"""REST 로그인 (레인 A): 직원(사번)·공용 계정·관리 토큰, 잠금, 소유자 분리(남의 run 404),
공용 계정의 internal 제외, 일일 상한, 사번 원문 미기록, 외부 검토 예산 소진 알림."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from rra.adapters.security import SessionStore
from rra.application.services.scoped_repository import PublicOnlyRepository
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.login import Login
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.composition import api_middlewares
from rra.domain.models import Chunk, Document
from rra.domain.rules.auth_policy import LOGIN_FAILED_MESSAGE
from rra.domain.rules.overlap import OwnUnit
from rra.entrypoints.api import create_app
from rra.entrypoints.api.app import SessionAuth
from rra.settings import Settings
from tests.application.test_login import FakeAuthStore
from tests.entrypoints.test_api import SLOTS, TOKEN
from tests.entrypoints.ui.fake_app import ANSWERS, KEYS, make_assistant
from tests.fakes import FakeLLM, FakePromptLibrary

STAFF_A = "K-2026-0001"
STAFF_B = "K-2026-0002"
GUEST = ("team", "pw-secret-99")
INTERNAL_DOC = Document(
    doc_id="alio:internal-9",
    source="alio",
    doc_type="internal_report",
    title="사내 비공개 궤도 보고서",
    body="궤도 틀림 사내 비공개 분석",
    orgs=["korail"],
    department="철도연구원",
    text_basis="summary",
    visibility="internal",
)
INTERNAL_CHUNK = Chunk(
    chunk_id="alio:internal-9#0",
    doc_id="alio:internal-9",
    ordinal=0,
    text="궤도 틀림 사내 비공개 분석",
    basis="summary",
    visibility="internal",
)


class FakeBudget:
    def __init__(self, exhausted=False):
        self._exhausted = exhausted

    def try_spend(self, n=1):
        return not self._exhausted

    def exhausted(self):
        return self._exhausted

    def remaining(self):
        return 0 if self._exhausted else 100


def build(*, limits=None, budget=None, store=None):
    a = make_assistant()
    a.repo.seed([INTERNAL_DOC], [INTERNAL_CHUNK])
    public_repo = PublicOnlyRepository(a.repo)
    a.manager.generate_public = GenerateProposal(
        FakeLLM(list(ANSWERS)), public_repo, FakePromptLibrary(), a.manager.generate.rules, KEYS
    )
    if budget is not None:
        a.manager.reviewer = object()  # 예산이 막으면 호출되지 않는다
        a.manager.review_budget = budget
    auth_store = store or FakeAuthStore(staff={STAFF_A, STAFF_B}, guest=GUEST)
    settings = Settings(_env_file=None)
    sessions = SessionStore()
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        repo=a.repo,
        user=a.user,
        middlewares=api_middlewares(settings, TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
        login=Login(auth_store, clock=lambda: 1000.0),
        auth_limits=limits or {"guest_runs_per_day": 10, "staff_runs_per_day": 20},
        guest_services={
            "repo": public_repo,
            "precheck": PrecheckOverlap(
                public_repo, own=OwnUnit(org="korail", departments=frozenset({"철도연구원"}))
            ),
        },
        sse_poll_sec=0.01,
    )
    return app, a, sessions


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")


async def login(c: httpx.AsyncClient, **body) -> dict[str, str]:
    r = await c.post("/v1/session", json=body)
    assert r.status_code == 200, r.text
    return {"X-RRA-CSRF": r.json()["csrf"]}


async def wait_drafted(c, run_id, headers):
    for _ in range(300):
        r = await c.get(f"/v1/runs/{run_id}", headers=headers)
        if r.json()["status"] not in ("queued", "running", "draft_reviewing"):
            return r.json()
        await asyncio.sleep(0.01)
    raise AssertionError("run did not finish")


AUTH = {"X-RRA-Token": TOKEN}


async def test_staff_login_sets_cookie_and_session_reports_kind_only():
    app, _, sessions = build()
    async with client_for(app) as c:
        r = await c.post("/v1/session", json={"kind": "staff", "staff_no": STAFF_A})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "staff" and body["label"] == "직원" and body["csrf"]
        assert (
            "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"]
        )
        assert STAFF_A not in r.text
        r = await c.get("/v1/session")
        assert r.json()["kind"] == "staff" and r.json()["staff_enabled"] is True
        assert STAFF_A not in r.text and "staff:" not in r.text  # 가명 ID 도 화면에 주지 않는다
        assert all(
            s.who.kind == "staff" and STAFF_A not in s.who.id for s in sessions._sessions.values()
        )
        csrf = body["csrf"]
        r = await c.request("DELETE", "/v1/session", headers={"X-RRA-CSRF": csrf})
        assert r.status_code == 204
        assert (await c.get("/v1/runs")).status_code == 401


async def test_unregistered_staff_and_wrong_guest_share_one_message_and_legacy_token_body():
    app, _, _ = build()
    async with client_for(app) as c:
        for body in (
            {"kind": "staff", "staff_no": "K-0000"},
            {"kind": "guest", "id": "team", "password": "wrong"},
            {"kind": "guest", "id": "nobody", "password": GUEST[1]},
            {"kind": "staff"},
        ):
            r = await c.post("/v1/session", json=body)
            assert r.status_code == 401 and r.json()["detail"] == LOGIN_FAILED_MESSAGE
            assert "set-cookie" not in r.headers
        r = await c.post("/v1/session", json={"token": TOKEN})  # 옛 본문 = 관리 토큰
        assert r.status_code == 200 and r.json()["kind"] == "admin"
        r = await c.get("/v1/session")
        assert r.json()["kind"] == "admin" and r.json()["label"] == "관리자"


async def test_guest_login_and_account_lockout_after_five_failures():
    app, _, _ = build()
    async with client_for(app) as c:
        for _ in range(5):
            r = await c.post("/v1/session", json={"kind": "guest", "id": "team", "password": "x"})
            assert r.status_code == 401
        r = await c.post("/v1/session", json={"kind": "guest", "id": "team", "password": GUEST[1]})
        assert r.status_code == 401 and r.json()["detail"] == LOGIN_FAILED_MESSAGE  # 잠금
    app, _, _ = build()
    async with client_for(app) as c:
        csrf = await login(c, kind="guest", id="team", password=GUEST[1])
        r = await c.get("/v1/session")
        assert r.json()["kind"] == "guest" and r.json()["label"] == "공용 계정"
        r = await c.post("/v1/precheck", json=SLOTS, headers=csrf)
        assert r.status_code == 200


async def test_ip_lockout_after_twenty_failures_from_one_address():
    app, _, _ = build()
    async with client_for(app) as c:
        for i in range(20):
            await c.post("/v1/session", json={"kind": "staff", "staff_no": f"NO-{i}"})
        r = await c.post("/v1/session", json={"kind": "staff", "staff_no": STAFF_A})
        assert r.status_code == 401  # 같은 IP 는 등록된 사번도 잠긴다


async def test_owner_isolation_other_staff_gets_404_admin_sees_everything(caplog):
    caplog.set_level(logging.INFO)
    app, a, _ = build()
    async with (
        client_for(app) as alice,
        client_for(app) as bob,
        client_for(app) as admin,
        client_for(app) as guest,
    ):
        h_a = await login(alice, kind="staff", staff_no=STAFF_A)
        h_b = await login(bob, kind="staff", staff_no=STAFF_B)
        h_g = await login(guest, kind="guest", id="team", password=GUEST[1])
        r = await alice.post("/v1/runs", json=SLOTS, headers=h_a)
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        await wait_drafted(alice, run_id, {})
        # 소유자: 목록·조회 모두 보인다
        assert [x["run_id"] for x in (await alice.get("/v1/runs")).json()["runs"]] == [run_id]
        assert (await alice.get(f"/v1/runs/{run_id}/draft")).status_code == 200
        # 남의 run: 목록에 없고 모든 경로가 404
        assert (await bob.get("/v1/runs")).json()["runs"] == []
        assert (await guest.get("/v1/runs")).json()["runs"] == []
        for path in (
            "",
            "/draft",
            "/events",
            "/versions",
            "/render-check",
            "/submit-check",
            "/usage",
        ):
            assert (await bob.get(f"/v1/runs/{run_id}{path}")).status_code == 404, path
            assert (await guest.get(f"/v1/runs/{run_id}{path}")).status_code == 404, path
        for path, body in (
            ("/finalize", {}),
            ("/review", None),
            ("/confirm", {"task_type": "applied"}),
        ):
            r = await bob.post(f"/v1/runs/{run_id}{path}", json=body, headers=h_b)
            assert r.status_code == 404, path
            r = await guest.post(f"/v1/runs/{run_id}{path}", json=body, headers=h_g)
            assert r.status_code == 404, path
        # 관리자(토큰): 모든 run 을 본다
        assert run_id in [
            x["run_id"] for x in (await admin.get("/v1/runs", headers=AUTH)).json()["runs"]
        ]
        assert (await admin.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).status_code == 200
        # 기존 run(소유자 없음 = local)은 관리자만
        r = await admin.post("/v1/runs", json=SLOTS, headers=AUTH)
        legacy_id = r.json()["run_id"]
        await wait_drafted(admin, legacy_id, AUTH)
        assert (await alice.get(f"/v1/runs/{legacy_id}")).status_code == 404
        assert (await admin.get(f"/v1/runs/{legacy_id}", headers=AUTH)).status_code == 200
        ids = {x["run_id"] for x in (await admin.get("/v1/runs", headers=AUTH)).json()["runs"]}
        assert ids == {run_id, legacy_id}
    # 사번 원문은 run 소유자 키·상태·로그 어디에도 없다
    owners = {user for user, _ in a.manager.store.states}
    assert any(o.startswith("staff-") for o in owners) and "local" in owners
    assert all(STAFF_A not in o and STAFF_B not in o for o in owners)
    assert all(STAFF_A not in str(s.model_dump()) for s in a.manager.store.states.values())
    assert STAFF_A not in caplog.text and STAFF_B not in caplog.text


async def test_guest_search_precheck_and_run_exclude_internal_documents():
    app, a, _ = build()
    async with client_for(app) as guest, client_for(app) as admin:
        h_g = await login(guest, kind="guest", id="team", password=GUEST[1])
        r = await guest.get("/v1/search", params={"q": "궤도 틀림 사내 비공개", "k": 10})
        assert r.status_code == 200
        assert all(c["doc_id"] != INTERNAL_DOC.doc_id for c in r.json()["chunks"])
        r = await admin.get(
            "/v1/search", params={"q": "궤도 틀림 사내 비공개", "k": 10}, headers=AUTH
        )
        assert any(c["doc_id"] == INTERNAL_DOC.doc_id for c in r.json()["chunks"])
        a.repo.similar = [
            (INTERNAL_DOC, 0.95)
        ]  # 유사과제 후보가 internal 뿐이면 공용 계정은 못 본다
        r = await guest.post("/v1/precheck", json=SLOTS, headers=h_g)
        assert r.status_code == 200 and r.json()["alerts"] == []
        r = await admin.post("/v1/precheck", json=SLOTS, headers=AUTH)
        assert r.json()["alerts"] != []
        a.repo.similar = []
        r = await guest.post("/v1/runs", json=SLOTS, headers=h_g)
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        await wait_drafted(guest, run_id, {})
        state = a.manager.store.states[("guest-team", run_id)]
        assert state.scope == "public"
        snapshot = a.manager.store.snapshots[("guest-team", run_id)]
        assert INTERNAL_DOC.doc_id not in snapshot.retrieved_ids


async def test_daily_run_limit_per_user_returns_429():
    app, _, _ = build(limits={"guest_runs_per_day": 1, "staff_runs_per_day": 20})
    async with client_for(app) as guest:
        h = await login(guest, kind="guest", id="team", password=GUEST[1])
        r = await guest.post("/v1/runs", json=SLOTS, headers=h)
        assert r.status_code == 202
        await wait_drafted(guest, r.json()["run_id"], {})
        r = await guest.post("/v1/runs", json=SLOTS, headers=h)
        assert r.status_code == 429 and "오늘 생성 상한" in r.json()["detail"]


async def test_exhausted_review_budget_skips_review_and_tells_the_screen():
    app, _, _ = build(budget=FakeBudget(exhausted=True))
    async with client_for(app) as c:
        r = await c.post("/v1/runs", json=SLOTS, headers=AUTH)
        run_id = r.json()["run_id"]
        state = await wait_drafted(c, run_id, AUTH)
        assert state["status"] == "drafted" and state["flow"]["draft_review_skipped"] == "budget"
        draft = (await c.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
        assert draft["review"]["skipped"] is True
        r = await c.post(f"/v1/runs/{run_id}/final-review", headers=AUTH)
        assert r.status_code == 409 and "상한" in r.json()["detail"]
        r = await c.post(f"/v1/runs/{run_id}/finalize", json={}, headers=AUTH)
        assert r.status_code == 200  # 검토 없이 마무리할 수 있다


@pytest.mark.parametrize("kind", ["staff", "guest"])
async def test_login_without_login_usecase_fails_closed(kind):
    a = make_assistant()
    settings = Settings(_env_file=None)
    sessions = SessionStore()
    app = create_app(
        manager=a.manager,
        precheck=a.precheck,
        repo=a.repo,
        user=a.user,
        middlewares=api_middlewares(settings, TOKEN, sessions=sessions),
        session_auth=SessionAuth(TOKEN, sessions),
    )
    async with client_for(app) as c:
        body = {"kind": kind, "staff_no": "K-1", "id": "team", "password": "x"}
        r = await c.post("/v1/session", json=body)
        assert r.status_code == 401
