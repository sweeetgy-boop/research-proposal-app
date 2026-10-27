"""접속자 IP (임시 구현 — 레인 [W] feat/tunnel 이 같은 경로·같은 서명으로 만든다; 합칠 때 [W] 판).

규칙: 설정 trust_cf_connecting_ip 가 true 이고 요청 peer 가 127.0.0.1 일 때만 CF-Connecting-IP
헤더를 믿고, 아니면 request.client.host.
"""

from __future__ import annotations

from typing import Any

LOOPBACK = ("127.0.0.1", "::1", "localhost")
CF_HEADER = "cf-connecting-ip"


def client_ip(request: Any, *, trust_cf: bool = False) -> str:
    client = getattr(request, "client", None)
    peer = (getattr(client, "host", None) or "") if client is not None else ""
    if trust_cf and peer in LOOPBACK:
        forwarded = (request.headers.get(CF_HEADER) or "").strip()
        if forwarded:
            return forwarded[:64]
    return peer or "unknown"
