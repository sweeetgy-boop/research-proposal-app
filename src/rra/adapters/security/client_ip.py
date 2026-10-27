"""접속자 식별 — 역프록시(Cloudflare Tunnel) 뒤에서의 접속자 IP 와 Access 사용자 해시 (보안 G·I).

- `client_ip(request, trust_cf)`: 기본은 요청 peer 주소(`request.client.host`). `trust_cf` 가
  True 이고 peer 가 127.0.0.1(같은 호스트의 cloudflared)일 때만 `CF-Connecting-IP` 를 믿는다.
  그 밖의 `X-Forwarded-*` 는 어디서도 믿지 않는다. 값이 IP 형식이 아니면 peer 로 되돌린다.
- `access_user_hash(request)`: `Cf-Access-Authenticated-User-Email` 이 있으면 sha256 해시 앞 12자.
  로그·manifest 에 이메일 원문은 남기지 않는다(보안 D·I). 헤더가 없으면 None.

두 함수 모두 Starlette `Request` 와 ASGI scope(dict) 를 받는다 — 미들웨어·라우트 공용.
레인 [A](로그인)가 같은 서명을 import 한다: 경로·서명을 바꾸지 않는다.
"""

from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Mapping
from typing import Any

CF_CONNECTING_IP = "cf-connecting-ip"
CF_ACCESS_EMAIL = "cf-access-authenticated-user-email"
LOOPBACK_PEER = "127.0.0.1"
HASH_PREFIX_LEN = 12


def _scope_of(request: Any) -> Mapping[str, Any]:
    if isinstance(request, Mapping):
        return request
    scope = getattr(request, "scope", None)
    return scope if isinstance(scope, Mapping) else {}


def _peer_host(scope: Mapping[str, Any]) -> str:
    client = scope.get("client")
    if not client:
        return ""
    host = client[0] if isinstance(client, (tuple, list)) else getattr(client, "host", "")
    return str(host or "")


def _header(scope: Mapping[str, Any], name: str) -> str | None:
    target = name.lower().encode("latin-1")
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode("latin-1")
    return None


def _valid_ip(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request: Any, trust_cf: bool) -> str:
    """접속자 IP. trust_cf 이고 peer 가 127.0.0.1 일 때만 CF-Connecting-IP, 아니면 peer 주소."""
    scope = _scope_of(request)
    peer = _peer_host(scope)
    if not trust_cf or peer != LOOPBACK_PEER:
        return peer
    forwarded = _header(scope, CF_CONNECTING_IP)
    if forwarded is None:
        return peer
    return _valid_ip(forwarded) or peer


def access_user_hash(request: Any) -> str | None:
    """Cf-Access-Authenticated-User-Email → sha256 앞 12자(소문자·공백 제거 뒤). 없으면 None."""
    email = _header(_scope_of(request), CF_ACCESS_EMAIL)
    if email is None:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:HASH_PREFIX_LEN]
