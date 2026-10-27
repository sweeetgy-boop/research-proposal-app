"""REST 공개 주소(config/api.yaml public_origin·trust_cf_connecting_ip).

세션 쿠키 Secure, Origin 검사, 거부 로그의 접속자 IP·Access 사용자 해시(원문 없음), 설정 로더.
네트워크·모델 없음."""

from __future__ import annotations

import logging

import httpx
import pytest

from rra.composition import api_middlewares
from rra.config_loader import api_config
from rra.entrypoints.api import create_app
from rra.settings import Settings
from tests.entrypoints.test_api import SLOTS, TOKEN
from tests.entrypoints.ui.fake_app import make_assistant

PUBLIC = "https://rra.example.test"
PUBLIC_HOST = "rra.example.test"
EMAIL = "colleague@example.org"


def make_app(*, public_origin: str = "", trust_cf: bool = False):
    from rra.adapters.security import SessionStore
    from rra.entrypoints.api.app import SessionAuth

    a = make_assistant()
    sessions = SessionStore()
    mws = api_middlewares(Settings(_env_file=None), TOKEN, sessions=sessions)
    for cls, kw in mws:
        if cls.__name__ == "TokenAuthMiddleware":
            kw["public_origin"], kw["trust_cf"] = public_origin, trust_cf
    return create_app(
        manager=a.manager,
        precheck=a.precheck,
        repo=a.repo,
        user=a.user,
        middlewares=mws,
        session_auth=SessionAuth(TOKEN, sessions),
        public_origin=public_origin,
        sse_poll_sec=0.01,
    )


def client_for(app, base_url: str = "http://127.0.0.1:8000") -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base_url)


async def login(c: httpx.AsyncClient, **headers) -> tuple[dict, str, str]:
    r = await c.post("/v1/session", json={"token": TOKEN}, headers=headers)
    assert r.status_code == 200, r.text
    return {"rra_session": r.cookies["rra_session"]}, r.json()["csrf"], r.headers["set-cookie"]


# ── 쿠키 Secure ─────────────────────────────────────────
async def test_cookie_secure_only_for_public_host_or_https():
    app = make_app(public_origin=PUBLIC)
    async with client_for(app) as c:  # 127.0.0.1 직접 접속 — 로컬 개발·e2e 는 그대로
        _, _, cookie = await login(c)
        assert "Secure" not in cookie and "HttpOnly" in cookie
    # 터널 경유 — 안쪽은 http, Host 는 공개 주소
    async with client_for(app, f"http://{PUBLIC_HOST}") as c:
        _, _, cookie = await login(c)
        assert "Secure" in cookie
    async with client_for(app, "https://127.0.0.1") as c:  # https 요청은 예전처럼 Secure
        _, _, cookie = await login(c)
        assert "Secure" in cookie


async def test_cookie_not_secure_without_public_origin():
    async with client_for(make_app(), f"http://{PUBLIC_HOST}") as c:
        _, _, cookie = await login(c)
        assert "Secure" not in cookie


# ── Origin 검사 ─────────────────────────────────────────
async def test_origin_public_or_same_host_allowed_and_others_rejected():
    app = make_app(public_origin=PUBLIC)
    async with client_for(app) as c:
        jar, csrf, _ = await login(c)
        ok = {"X-RRA-CSRF": csrf}
        assert (
            await c.post("/v1/precheck", json=SLOTS, cookies=jar, headers=ok)
        ).status_code == 200
        for origin in (PUBLIC, PUBLIC + "/", "http://127.0.0.1:8000", "HTTPS://RRA.EXAMPLE.TEST"):
            r = await c.post(
                "/v1/precheck", json=SLOTS, cookies=jar, headers={**ok, "Origin": origin}
            )
            assert r.status_code == 200, origin
        for origin in ("https://evil.example", "null", "http://rra.example.test.evil"):
            r = await c.post(
                "/v1/precheck", json=SLOTS, cookies=jar, headers={**ok, "Origin": origin}
            )
            assert r.status_code == 403 and "Origin" in r.json()["detail"], origin
        # 조회(GET)는 Origin 과 무관, 헤더 토큰 인증은 CSRF 대상이 아니다
        r = await c.get("/v1/runs", cookies=jar, headers={"Origin": "https://evil.example"})
        assert r.status_code == 200
        r = await c.post(
            "/v1/precheck",
            json=SLOTS,
            headers={"X-RRA-Token": TOKEN, "Origin": "https://evil.example"},
        )
        assert r.status_code == 200


async def test_login_rejects_foreign_origin_without_public_origin_too():
    async with client_for(make_app()) as c:
        r = await c.post("/v1/session", json={"token": TOKEN}, headers={"Origin": PUBLIC})
        assert r.status_code == 403
        r = await c.post(
            "/v1/session", json={"token": TOKEN}, headers={"Origin": "http://127.0.0.1:8000"}
        )
        assert r.status_code == 200
    async with client_for(make_app(public_origin=PUBLIC)) as c:
        r = await c.post("/v1/session", json={"token": TOKEN}, headers={"Origin": PUBLIC})
        assert r.status_code == 200


# ── 거부 로그: 접속자 IP + Access 사용자 해시 ─────────────
async def test_reject_log_has_cf_ip_and_email_hash_not_raw(caplog):
    from rra.adapters.security import access_user_hash

    app = make_app(public_origin=PUBLIC, trust_cf=True)
    headers = {"CF-Connecting-IP": "203.0.113.7", "Cf-Access-Authenticated-User-Email": EMAIL}
    with caplog.at_level(logging.INFO, logger="rra.api.auth"):
        async with client_for(app) as c:  # ASGITransport 의 peer 는 127.0.0.1
            assert (await c.get("/v1/runs", headers=headers)).status_code == 401
    text = "\n".join(r.getMessage() for r in caplog.records)
    digest = access_user_hash(
        {"headers": [(b"cf-access-authenticated-user-email", EMAIL.encode())]}
    )
    assert "ip=203.0.113.7" in text and f"access_user={digest}" in text
    assert EMAIL not in text and "example.org" not in text


async def test_reject_log_uses_peer_when_cf_not_trusted(caplog):
    with caplog.at_level(logging.INFO, logger="rra.api.auth"):
        async with client_for(make_app()) as c:
            r = await c.get("/v1/runs", headers={"CF-Connecting-IP": "203.0.113.7"})
            assert r.status_code == 401
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "ip=127.0.0.1" in text and "203.0.113.7" not in text and "access_user=-" in text


# ── 설정 로더·조립 ───────────────────────────────────────
def settings_with(tmp_path, body: str | None) -> Settings:
    if body is not None:
        (tmp_path / "api.yaml").write_text(body, encoding="utf-8")
    return Settings(_env_file=None, config_dir=tmp_path)


def test_api_config_defaults_when_file_missing(tmp_path):
    assert api_config(settings_with(tmp_path, None)) == {
        "public_origin": "",
        "trust_cf_connecting_ip": False,
    }
    assert api_config(settings_with(tmp_path, "public_origin: ''\n")) == {
        "public_origin": "",
        "trust_cf_connecting_ip": False,
    }


def test_api_config_normalizes_and_validates(tmp_path):
    cfg = api_config(
        settings_with(
            tmp_path, "public_origin: HTTPS://RRA.Example.test/\ntrust_cf_connecting_ip: true\n"
        )
    )
    assert cfg == {"public_origin": "https://rra.example.test", "trust_cf_connecting_ip": True}
    for bad in (
        "public_origin: http://rra.example.test\n",
        "public_origin: https://rra.example.test/app\n",
        "public_origin: rra.example.test\n",
        "trust_cf_connecting_ip: yes-please\n",
        "unknown_key: 1\n",
    ):
        with pytest.raises(ValueError):
            api_config(settings_with(tmp_path, bad))


def test_repo_api_yaml_sets_public_origin_and_middleware_gets_it():
    settings = Settings(_env_file=None)
    cfg = api_config(settings)
    assert cfg["public_origin"] == "https://rra.ai-edu-lab.co.kr"
    assert cfg["trust_cf_connecting_ip"] is False  # 터널 기동 전 기본값
    (_, auth_kw), *_ = api_middlewares(settings, TOKEN)
    assert auth_kw["public_origin"] == cfg["public_origin"]
    assert auth_kw["trust_cf"] is False
