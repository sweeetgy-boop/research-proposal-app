"""adapters/security/client_ip — 역프록시 뒤 접속자 IP 네 경우 + Access 이메일 해시."""

from __future__ import annotations

import hashlib

import pytest
from starlette.requests import Request

from rra.adapters.security import access_user_hash, client_ip

CF_IP = "203.0.113.7"
EMAIL = "Colleague@Example.org"


def scope(peer: str | None, headers: dict[str, str] | None = None) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/v1/runs",
        "client": (peer, 50000) if peer else None,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }


@pytest.mark.parametrize(
    ("trust_cf", "peer", "header", "expected"),
    [
        (False, "127.0.0.1", CF_IP, "127.0.0.1"),  # 신뢰 안 함 → peer
        (True, "127.0.0.1", CF_IP, CF_IP),  # 신뢰 + 루프백 peer → CF-Connecting-IP
        (True, "10.0.0.9", CF_IP, "10.0.0.9"),  # 신뢰해도 peer 가 루프백이 아니면 peer
        (True, "127.0.0.1", None, "127.0.0.1"),  # 헤더 없음 → peer
    ],
)
def test_client_ip_four_cases(trust_cf, peer, header, expected):
    headers = {"CF-Connecting-IP": header} if header else {}
    assert client_ip(scope(peer, headers), trust_cf) == expected


def test_client_ip_rejects_non_ip_header_and_ignores_x_forwarded_for():
    bad = scope("127.0.0.1", {"CF-Connecting-IP": "evil; DROP", "X-Forwarded-For": CF_IP})
    assert client_ip(bad, True) == "127.0.0.1"
    only_xff = scope("127.0.0.1", {"X-Forwarded-For": CF_IP})
    assert client_ip(only_xff, True) == "127.0.0.1"
    assert client_ip(scope("127.0.0.1", {"CF-Connecting-IP": "2001:db8::1"}), True) == "2001:db8::1"
    assert client_ip(scope(None), True) == ""


def test_forwarded_for_rightmost_only_from_loopback_when_enabled():
    """Tailscale serve/Funnel: 프록시가 X-Forwarded-For 끝에 접속자를 붙인다. 왼쪽은 위조 가능."""
    spoofed = scope("127.0.0.1", {"X-Forwarded-For": "1.2.3.4, 198.51.100.20"})
    assert client_ip(spoofed, False, trust_forwarded=True) == "198.51.100.20"
    assert client_ip(spoofed, False) == "127.0.0.1"  # 기본은 믿지 않는다
    one = scope("127.0.0.1", {"X-Forwarded-For": "2001:db8::5"})
    assert client_ip(one, False, trust_forwarded=True) == "2001:db8::5"
    remote = scope("10.0.0.9", {"X-Forwarded-For": "198.51.100.20"})
    assert client_ip(remote, False, trust_forwarded=True) == "10.0.0.9"  # 루프백 peer 만
    bad = scope("127.0.0.1", {"X-Forwarded-For": "198.51.100.20, not-an-ip"})
    assert client_ip(bad, False, trust_forwarded=True) == "127.0.0.1"  # 맨 오른쪽이 이상하면 peer
    both = scope("127.0.0.1", {"X-Forwarded-For": "198.51.100.20", "CF-Connecting-IP": CF_IP})
    assert client_ip(both, True, trust_forwarded=True) == CF_IP  # Cloudflare 가 먼저
    assert client_ip(scope("127.0.0.1"), True, trust_forwarded=True) == "127.0.0.1"


def test_client_ip_accepts_starlette_request():
    request = Request(scope("127.0.0.1", {"CF-Connecting-IP": CF_IP}))
    assert client_ip(request, True) == CF_IP
    assert client_ip(request, False) == "127.0.0.1"


def test_access_user_hash_is_sha256_prefix_without_raw_email():
    digest = access_user_hash(scope("127.0.0.1", {"Cf-Access-Authenticated-User-Email": EMAIL}))
    expected = hashlib.sha256(EMAIL.strip().lower().encode()).hexdigest()[:12]
    assert digest == expected and len(digest) == 12
    assert "@" not in digest and "example" not in digest
    # 대소문자·공백만 다른 주소는 같은 사람
    same = access_user_hash(
        scope("127.0.0.1", {"Cf-Access-Authenticated-User-Email": " colleague@example.org "})
    )
    assert same == digest
    assert access_user_hash(scope("127.0.0.1")) is None
    assert (
        access_user_hash(scope("127.0.0.1", {"Cf-Access-Authenticated-User-Email": "  "})) is None
    )
    assert (
        access_user_hash(Request(scope("127.0.0.1", {"Cf-Access-Authenticated-User-Email": EMAIL})))
        == digest
    )
