"""C. 아웃바운드 허용목록 + 7. 원본 캐시.

모든 소스 어댑터는 네트워크를 `GuardedClient` 로만 쓴다. 요청마다(리다이렉트 hop 포함)
`check_url()` 을 통과해야 한다:

- https 만, userinfo 금지, 기본 포트(443) 만
- 호스트가 config/security.yaml 의 allowed_domains 에 정확히 일치
- 호스트가 사설·루프백·링크로컬로 해석되면 거부 (해석 실패도 거부)

알려진 한계: DNS 검사 시점과 실제 연결 시점 사이의 rebinding 은 막지 못한다.
허용목록이 공개 API 도메인뿐이라 수용하고, 대신 리다이렉트는 hop 마다 다시 검사한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

SECRET_PARAMS = {"key", "apikey", "api_key", "servicekey", "accesskey", "token"}
PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]
USER_AGENT = "rra/0.1"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_TIMEOUT = httpx.Timeout(10.0, read=30.0)

Resolver = Callable[[str], bool]


class BlockedURL(ValueError):
    """허용목록·SSRF 규칙 위반. 재시도하지 않는다."""


class FetchError(RuntimeError):
    """상태 코드·크기·형식 오류. 메시지에는 비밀 제거된 URL 만 넣는다 (D)."""


def strip_secrets(url: str) -> str:
    p = urlsplit(url)
    q = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in SECRET_PARAMS
    ]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def cache_key(url: str) -> str:
    return hashlib.sha256(strip_secrets(url).encode()).hexdigest()


def host_allowed(url: str, allowed: set[str]) -> bool:
    host = urlsplit(url).hostname or ""
    return host in allowed


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 → 127.0.0.1
    return any(ip in n for n in PRIVATE_NETS)


def resolves_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if _is_private_ip(ip):
            return True
    return False


def check_url(url: str, allowed: set[str], *, resolver: Resolver = resolves_private) -> str:
    """요청 직전 단일 관문. 통과하면 url 을 그대로 돌려주고, 아니면 BlockedURL."""
    safe = strip_secrets(url)
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise BlockedURL(f"https 만 허용합니다: {safe}")
    if parts.username is not None or parts.password is not None:
        raise BlockedURL(f"URL 에 userinfo 를 넣을 수 없습니다: {safe}")
    try:
        port = parts.port
    except ValueError as exc:
        raise BlockedURL(f"잘못된 포트: {safe}") from exc
    if port not in (None, 443):
        raise BlockedURL(f"443 외 포트는 허용하지 않습니다: {safe}")
    if not host_allowed(url, allowed):
        raise BlockedURL(f"허용목록에 없는 호스트입니다: {safe}")
    if resolver(parts.hostname or ""):
        raise BlockedURL(f"사설·루프백 주소로 해석되는 호스트입니다: {safe}")
    return url


class GuardedClient:
    """허용목록 강제 httpx 클라이언트. 리다이렉트는 직접 따라가며 hop 마다 check_url()."""

    def __init__(
        self,
        allowed: Iterable[str],
        *,
        timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
        max_redirects: int = 3,
        max_response_bytes: int = 20 * 1024 * 1024,
        rate_limit: float | None = None,
        retries: int = 3,
        backoff_sec: float = 0.5,
        max_backoff_sec: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolves_private,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.allowed = {d.strip().lower().rstrip(".") for d in allowed if d.strip()}
        self.max_redirects = max_redirects
        self.max_response_bytes = max_response_bytes
        self.min_interval = 1.0 / rate_limit if rate_limit else 0.0
        self.retries = retries
        self.backoff_sec = backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self._resolver = resolver
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def __repr__(self) -> str:
        return f"GuardedClient(allowed={sorted(self.allowed)!r})"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GuardedClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        headers, body, safe = await self._get(url, params)
        ctype = headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype != "application/json" and not ctype.endswith("+json"):
            raise FetchError(f"JSON 이 아닌 응답({ctype or '없음'}): {safe}")
        try:
            return json.loads(body)
        except ValueError as exc:
            raise FetchError(f"JSON 파싱 실패: {safe}") from exc

    async def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        accept_types: Iterable[str],
    ) -> bytes:
        """파일 다운로드. content-type 이 accept_types 에 없으면 FetchError. 크기 상한 동일."""
        accepted = {t.lower() for t in accept_types}
        headers, body, safe = await self._get(url, params)
        ctype = headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype not in accepted:
            raise FetchError(f"허용되지 않은 content-type({ctype or '없음'}): {safe}")
        return body

    async def _get(
        self, url: str, params: dict[str, Any] | None
    ) -> tuple[httpx.Headers, bytes, str]:
        """재시도·상태 코드 처리 공통 경로. (헤더, 본문, 비밀 제거된 최종 URL)."""
        target = httpx.URL(url, params=params) if params else httpx.URL(url)
        attempt = 0
        while True:
            try:
                status, headers, body, final = await self._fetch(target)
            except httpx.TransportError as exc:
                if attempt >= self.retries:
                    safe = strip_secrets(str(target))
                    raise FetchError(f"{type(exc).__name__}: {safe}") from None
                await self._sleep(self._retry_delay(attempt, None))
                attempt += 1
                continue
            if status in RETRY_STATUS and attempt < self.retries:
                await self._sleep(self._retry_delay(attempt, headers.get("retry-after")))
                attempt += 1
                continue
            safe = strip_secrets(str(final))
            if status != 200:
                raise FetchError(f"HTTP {status}: {safe}")
            return headers, body, safe

    async def _fetch(self, target: httpx.URL) -> tuple[int, httpx.Headers, bytes, httpx.URL]:
        for _ in range(self.max_redirects + 1):
            check_url(str(target), self.allowed, resolver=self._resolver)
            await self._throttle()
            async with self._client.stream("GET", target) as resp:
                if resp.has_redirect_location:
                    target = target.join(resp.headers["location"])
                    continue  # 다음 hop 도 check_url 을 다시 거친다
                body = await self._read_capped(resp, target)
                return resp.status_code, resp.headers, body, target
        safe = strip_secrets(str(target))
        raise BlockedURL(f"리다이렉트가 {self.max_redirects}회를 넘었습니다: {safe}")

    async def _read_capped(self, resp: httpx.Response, target: httpx.URL) -> bytes:
        declared = resp.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_response_bytes:
            raise FetchError(f"응답이 상한을 넘습니다: {strip_secrets(str(target))}")
        buf = bytearray()
        async for part in resp.aiter_bytes():  # 압축 해제 후 크기 기준
            buf.extend(part)
            if len(buf) > self.max_response_bytes:
                raise FetchError(f"응답이 상한을 넘습니다: {strip_secrets(str(target))}")
        return bytes(buf)

    async def _throttle(self) -> None:
        if self.min_interval and self._last_request is not None:
            wait = self._last_request + self.min_interval - self._clock()
            if wait > 0:
                await self._sleep(wait)
        self._last_request = self._clock()

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), self.max_backoff_sec)
        return min(self.backoff_sec * (2**attempt), self.max_backoff_sec)
