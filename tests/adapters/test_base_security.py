import socket

import pytest

from rra.adapters.sources._base import (
    BlockedURL,
    cache_key,
    check_url,
    host_allowed,
    resolves_private,
    strip_secrets,
)


def test_strip_secrets_removes_key_params():
    u = "https://apis.data.go.kr/x?serviceKey=SECRET&q=rail&pageNo=1"
    assert "SECRET" not in strip_secrets(u)
    assert cache_key(u) == cache_key("https://apis.data.go.kr/x?q=rail&pageNo=1")


def test_host_allowlist():
    allowed = {"api.openalex.org"}
    assert host_allowed("https://api.openalex.org/works", allowed)
    assert not host_allowed("https://api.openalex.org.evil.com/works", allowed)


def test_private_ip_detection():
    assert resolves_private("localhost")
    assert resolves_private("127.0.0.1")


# ── check_url: 요청 직전 관문 ─────────────────────────────
ALLOWED = {"api.openalex.org"}


def public(_host):
    return False


def private(_host):
    return True


def test_check_url_passes_allowed_https():
    url = "https://api.openalex.org/works?search=rail"
    assert check_url(url, ALLOWED, resolver=public) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openalex.org/works",  # https 만
        "https://user@api.openalex.org/works",  # userinfo
        "https://api.openalex.org@evil.com/works",  # userinfo 로 위장
        "https://api.openalex.org:8443/works",  # 443 외 포트
        "https://evil.com/works",  # 허용목록 밖
        "https://api.openalex.org.evil.com/works",  # 접미사 위장
        "https://127.0.0.1/works",  # IP 리터럴
        "https://[::1]/works",
        "file:///etc/passwd",
    ],
)
def test_check_url_rejects(url):
    with pytest.raises(BlockedURL):
        check_url(url, ALLOWED, resolver=public)


def test_check_url_rejects_allowed_host_resolving_private():
    with pytest.raises(BlockedURL):
        check_url("https://api.openalex.org/works", ALLOWED, resolver=private)


def test_blocked_message_has_no_secret():
    with pytest.raises(BlockedURL) as exc:
        check_url("https://evil.com/x?serviceKey=SECRET&q=1", ALLOWED, resolver=public)
    assert "SECRET" not in str(exc.value)


@pytest.mark.parametrize(
    "ip", ["0.0.0.0",  # noqa: S104 — 바인딩이 아니라 거부 대상 주소
           "100.64.0.1", "fe80::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1"]
)
def test_added_private_ranges(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", (ip, 0))])
    assert resolves_private("anything.example")


def test_public_address_is_not_private(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("104.18.0.1", 0))]
    )
    assert not resolves_private("api.openalex.org")
