"""현재 공인 IP 조회 (PublicIpPort) — `rra sources check` 가 자료원 등록 IP 와 대조한다 (레인 I).

GuardedClient 로만 나간다(보안 C: 조회 URL 의 호스트는 security.yaml allowed_domains 에 있어야
한다).
응답은 IP 문자열 하나만 받아들인다 — 그 외(HTML·긴 본문)는 FetchError. 비밀을 보내지 않는다.
"""

from __future__ import annotations

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.domain.rules.source_ip import normalize_ip

MAX_BODY_BYTES = 64


class PublicIpProbe:
    def __init__(self, client: GuardedClient, *, url: str):
        self.client = client
        self.url = url

    def __repr__(self) -> str:
        return f"PublicIpProbe(url={self.url!r})"

    async def current_ip(self) -> str:
        _headers, body, safe = await self.client.get_raw(self.url, None)
        if len(body) > MAX_BODY_BYTES:
            raise FetchError(f"공인 IP 응답이 IP 문자열이 아닙니다: {safe}")
        ip = normalize_ip(body.decode("ascii", "replace").strip().strip('"'))
        if not ip:
            raise FetchError(f"공인 IP 응답이 IP 문자열이 아닙니다: {safe}")
        return ip

    async def aclose(self) -> None:
        await self.client.aclose()
