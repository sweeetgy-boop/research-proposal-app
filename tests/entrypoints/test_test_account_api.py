"""시험 계정 세션 REST (ADR 0056 2026-11-04 덧붙임) — 가짜 모드.

시험 계정(배포 확인용 임시 사번)으로 로그인한 세션의 [선택 적용]·생성 요청 기록 줄과 과제안 측정
줄에는 `test: true` 가 붙고, 일반 직원·관리 토큰 세션의 줄에는 키가 없다. 중복 한 줄 규칙은 그대로.
응답(세션 상태 포함)에는 시험 표시·사번이 나가지 않는다.
"""

from __future__ import annotations

import httpx
import pytest

from rra.adapters.fake.auth import FAKE_STAFF
from rra.adapters.logging.choice_log import ALLOWED_KEYS, MemoryChoiceLog
from tests.application.test_recommend_metrics import MemoryMetrics
from tests.entrypoints.test_choice_log_apply_api import (
    APPLY,
    AUTH,
    IDEA,
    _app,
    _body,
    _client,
    _rows,
)

TEST_NO = "E2E-T-0001"  # 가짜 저장소에만 있는 시험 사번


@pytest.fixture
def parts(tmp_path, monkeypatch):
    import rra.adapters.fake as fake_pkg
    from rra import composition

    base = fake_pkg.ScriptedAuthStore

    class WithTestAccount(base):
        def __init__(self) -> None:
            super().__init__()
            self.add_staff(TEST_NO, test=True)

    monkeypatch.setattr(fake_pkg, "ScriptedAuthStore", WithTestAccount)
    metrics = MemoryMetrics()
    monkeypatch.setattr(composition, "build_recommend_metrics", lambda settings=None: metrics)
    log = MemoryChoiceLog()
    return {"app": _app(tmp_path, monkeypatch, log), "log": log, "metrics": metrics}


async def _login(c: httpx.AsyncClient, staff_no: str) -> dict[str, str]:
    r = await c.post("/v1/session", json={"kind": "staff", "staff_no": staff_no})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"csrf", "expires_in", "kind", "label"}  # 시험 표시는 응답에 없다
    return {"X-RRA-CSRF": body["csrf"]}


async def test_test_session_lines_carry_test_true_and_normal_sessions_do_not(parts):
    app, log, metrics = parts["app"], parts["log"], parts["metrics"]
    async with _client(app) as c:
        first, second = await _rows(c)
        chosen = _body((first, "unrelated", "user"), (second, "similar", "ai_prefill"))

        # 관리 토큰 — 키 없음 (② 자동 과제안 측정 줄 포함)
        await c.post(APPLY, json=chosen, headers=AUTH)
        assert len(log.records) == 2 and all("test" not in r for r in log.records)
        assert all("test" not in row for row in metrics.rows)
        n0 = len(metrics.rows)

        # 시험 계정 세션 — [선택 적용]·생성 요청 줄 모두 test: true
        tester = await _login(c, TEST_NO)
        session = (await c.get("/v1/session")).json()
        assert session["kind"] == "staff" and "test" not in session
        r = await c.post(APPLY, json=chosen, headers=tester)
        assert r.status_code == 200, r.text
        await c.post(APPLY, json=chosen, headers=tester)  # 같은 선택 잇따라 — 한 줄(중복 규칙)
        r = await c.post("/v1/runs", json=chosen, headers=tester)
        assert r.status_code == 202, r.text
        tested = log.records[2:]
        assert [(x["event"], x.get("test")) for x in tested] == [
            ("apply", True),
            ("apply", True),
            ("generate", True),
            ("generate", True),
        ]

        # 과제안 — 시험 세션의 측정 줄만 test: true
        r = await c.post("/v1/precheck/recommendations", json=IDEA, headers=tester)
        assert r.status_code == 200, r.text
        rec_id = r.json()["recommendations"]["id"]
        r = await c.post(
            "/v1/precheck/recommendations/more",
            json={"request": IDEA, "rec_id": rec_id},
            headers=tester,
        )
        assert r.status_code == 200, r.text
        test_rows = list(metrics.rows[n0:])
        assert test_rows and all(row.get("test") is True for row in test_rows)
        assert {row["mode"] for row in test_rows} >= {"initial", "more"}

        # 일반 직원 세션(같은 클라이언트에서 다시 로그인) — 키 없음
        normal = await _login(c, FAKE_STAFF[0])
        before = len(log.records)
        await c.post(APPLY, json=chosen, headers=normal)
        r = await c.post("/v1/runs", json=chosen, headers=normal)
        assert r.status_code == 202, r.text
        assert len(log.records) == before + 4
        assert all("test" not in x for x in log.records[before:])
        n = len(metrics.rows)
        r = await c.post("/v1/precheck/recommendations", json=IDEA, headers=normal)
        assert r.status_code == 200, r.text
        assert len(metrics.rows) > n and all("test" not in row for row in metrics.rows[n:])

    for rec in log.records:
        assert set(rec) <= ALLOWED_KEYS
    flat = str(log.records) + str(metrics.rows)
    for raw in (TEST_NO, TEST_NO.replace("-", ""), FAKE_STAFF[0], "staff:"):
        assert raw not in flat
