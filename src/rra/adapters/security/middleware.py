from __future__ import annotations

import secrets
from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

AUTH_HEADER = "x-rra-token"  # 또는 Authorization: Bearer <token>
SECURITY_HEADERS: dict[str, str] = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "cache-control": "no-store",
}
DEFAULT_MAX_BODY = 64 * 1024


def _header(scope: Scope, name: str) -> str | None:
    target = name.lower().encode("latin-1")
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode("latin-1")
    return None


class SecurityHeadersMiddleware:
    """모든 HTTP 응답에 보안 헤더를 붙인다 (오류 응답 포함)."""

    def __init__(self, app: ASGIApp, headers: dict[str, str] | None = None):
        self.app = app
        self.headers = {k.lower(): v for k, v in (headers or SECURITY_HEADERS).items()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() not in self.headers
                ]
                raw.extend(
                    (k.encode("latin-1"), v.encode("latin-1")) for k, v in self.headers.items()
                )
                message = {**message, "headers": raw}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class TokenAuthMiddleware:
    """단일 관리 토큰. 비교는 상수 시간. 토큰이 비어 있으면 모든 요청을 거부한다.

    (조립이 토큰 없는 기동을 먼저 막는다 — 여기는 마지막 방어선.)
    """

    def __init__(self, app: ASGIApp, token: str, exempt_paths: Iterable[str] = ("/healthz",)):
        self.app = app
        self.token = token or ""
        self.exempt = frozenset(exempt_paths)

    def _presented(self, scope: Scope) -> str:
        direct = _header(scope, AUTH_HEADER)
        if direct:
            return direct.strip()
        auth = _header(scope, "authorization") or ""
        scheme, _, value = auth.partition(" ")
        return value.strip() if scheme.lower() == "bearer" else ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.exempt:
            await self.app(scope, receive, send)
            return
        presented = self._presented(scope)
        ok = bool(self.token) and bool(presented) and secrets.compare_digest(presented, self.token)
        if not ok:
            response = JSONResponse(
                {"detail": "인증 토큰이 필요합니다."},
                status_code=401,
                headers={"www-authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """요청 본문 상한. Content-Length 가 없는 본문(chunked)은 받지 않는다."""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BODY):
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        length_header = _header(scope, "content-length")
        if length_header is None:
            if method in ("POST", "PUT", "PATCH") and _header(scope, "transfer-encoding"):
                await JSONResponse({"detail": "Content-Length 가 필요합니다."}, status_code=411)(
                    scope, receive, send
                )
                return
            await self.app(scope, receive, send)
            return
        try:
            length = int(length_header)
        except ValueError:
            await JSONResponse({"detail": "Content-Length 형식 오류"}, status_code=400)(
                scope, receive, send
            )
            return
        if length > self.max_bytes:
            await JSONResponse(
                {"detail": f"요청 본문이 상한 {self.max_bytes} bytes 를 넘습니다."}, status_code=413
            )(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:  # 선언보다 많이 보내는 경우
                    raise RuntimeError("request body exceeds declared length")
            return message

        await self.app(scope, limited_receive, send)
