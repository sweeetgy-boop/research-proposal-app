from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from http.cookies import SimpleCookie

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rra.adapters.security.client_ip import access_user_hash, client_ip
from rra.adapters.security.sessions import COOKIE_NAME, CSRF_HEADER, SessionStore

log = logging.getLogger("rra.api.auth")

AUTH_HEADER = "x-rra-token"  # 또는 Authorization: Bearer <token>
# API 응답: 아무것도 싣지 않는다. SPA(web/dist) 응답: 같은 출처의 스크립트·스타일만, 인라인 없음.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
SPA_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self'"
)
SECURITY_HEADERS: dict[str, str] = {
    "content-security-policy": API_CSP,
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "cache-control": "no-store",
}
API_PREFIXES = ("/v1", "/healthz")
DEFAULT_MAX_BODY = 64 * 1024
PROBLEM_JSON = "application/problem+json"
STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ORIGIN_DETAIL = "허용되지 않은 출처(Origin)입니다."


def problem(status: int, detail: str, *, headers: dict[str, str] | None = None) -> JSONResponse:
    """RFC 9457 problem+json. 한국어 detail. 미들웨어·앱이 같은 모양을 쓴다."""
    return JSONResponse(
        {
            "type": "about:blank",
            "title": _TITLES.get(status, "오류"),
            "status": status,
            "detail": detail,
        },
        status_code=status,
        headers=headers,
        media_type=PROBLEM_JSON,
    )


_TITLES = {
    400: "잘못된 요청",
    401: "인증 필요",
    403: "권한 없음",
    404: "없음",
    409: "상태 충돌",
    411: "본문 길이 필요",
    413: "본문 너무 큼",
    422: "입력 오류",
    429: "요청 과다",
    503: "사용 불가",
}


def _cookie(scope: Scope, name: str) -> str | None:
    raw = _header(scope, "cookie")
    if not raw:
        return None
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:  # 깨진 쿠키 헤더 — 없는 것으로 본다
        return None
    morsel = jar.get(name)
    return morsel.value if morsel else None


def _header(scope: Scope, name: str) -> str | None:
    target = name.lower().encode("latin-1")
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode("latin-1")
    return None


def normalize_origin(value: str | None) -> str:
    """출처 비교용 정규화: 소문자, 양끝 공백·끝 슬래시 제거."""
    return (value or "").strip().lower().rstrip("/")


def origin_allowed(scope: Scope, public_origin: str = "") -> bool:
    """브라우저 Origin 헤더 검사 (쿠키 인증의 상태 변경 요청·로그인).

    Origin 이 없으면 통과(브라우저 밖 클라이언트·CSRF 토큰이 따로 막는다). 있으면 요청 Host 와 같은
    출처(http·https) 또는 설정의 public_origin(역프록시 공개 주소)만 허용한다. "null" 은 거부.
    """
    raw = _header(scope, "origin")
    if raw is None:
        return True
    origin = normalize_origin(raw)
    if not origin or origin == "null":
        return False
    allowed = {normalize_origin(public_origin)} if public_origin else set()
    host = normalize_origin(_header(scope, "host"))
    if host:
        allowed |= {f"http://{host}", f"https://{host}"}
    return origin in allowed


class SecurityHeadersMiddleware:
    """모든 HTTP 응답에 보안 헤더를 붙인다 (오류 응답 포함).

    CSP 는 경로별: /v1·/healthz 는 default-src 'none', 그 밖(정적 SPA)은 같은 출처만·인라인 없음.
    """

    def __init__(self, app: ASGIApp, headers: dict[str, str] | None = None, spa_csp: str = SPA_CSP):
        self.app = app
        self.headers = {k.lower(): v for k, v in (headers or SECURITY_HEADERS).items()}
        self.spa_csp = spa_csp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "") or ""
        headers = dict(self.headers)
        if not path.startswith(API_PREFIXES):
            headers["content-security-policy"] = self.spa_csp
            headers["cache-control"] = "no-cache"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = [(k, v) for k, v in message.get("headers", []) if k.lower() not in headers]
                raw.extend((k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items())
                message = {**message, "headers": raw}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class TokenAuthMiddleware:
    """단일 관리 토큰 — 헤더(X-RRA-Token / Bearer) 또는 세션 쿠키. 비교는 상수 시간.

    토큰이 비어 있으면 모든 요청을 거부한다 (조립이 토큰 없는 기동을 먼저 막는다 — 마지막 방어선).
    세션 쿠키로 인증된 상태 변경 요청(POST·PUT·PATCH·DELETE)은 CSRF 헤더(X-RRA-CSRF)가 세션의
    값과 같아야 하고, 브라우저가 보낸 Origin 은 같은 출처 또는 public_origin 이어야 한다.
    /v1/session 은 로그인 자체라 인증을 면제하되(Origin 은 검사) 본문의 토큰을 라우트가 검사한다.
    정적 파일(/v1·/healthz 밖)은 인증 없이 서빙한다 — SPA 가 로그인 화면을 보여야 하므로.
    접속자 IP(client_ip, trust_cf)·Access 사용자 해시는 scope state 에 두고 거부 로그에만 쓴다.
    """

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        exempt_paths: Iterable[str] = ("/healthz",),
        sessions: SessionStore | None = None,
        session_path: str = "/v1/session",
        protected_prefixes: Iterable[str] = API_PREFIXES,
        public_origin: str = "",
        trust_cf: bool = False,
    ):
        self.app = app
        self.token = token or ""
        self.exempt = frozenset(exempt_paths)
        self.sessions = sessions
        self.session_path = session_path
        self.protected = tuple(protected_prefixes)
        self.public_origin = normalize_origin(public_origin)
        self.trust_cf = bool(trust_cf)

    def _presented(self, scope: Scope) -> str:
        direct = _header(scope, AUTH_HEADER)
        if direct:
            return direct.strip()
        auth = _header(scope, "authorization") or ""
        scheme, _, value = auth.partition(" ")
        return value.strip() if scheme.lower() == "bearer" else ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "") or ""
        method = scope.get("method", "GET")
        if path in self.exempt or not path.startswith(self.protected):
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        state["rra_client_ip"] = client_ip(scope, self.trust_cf)
        state["rra_access_user"] = access_user_hash(scope)
        if path == self.session_path and method == "POST":  # 로그인 — 라우트가 토큰을 검사
            if not origin_allowed(scope, self.public_origin):
                await self._reject(scope, receive, send, 403, _ORIGIN_DETAIL)
                return
            await self.app(scope, receive, send)
            return
        presented = self._presented(scope)
        if bool(self.token) and bool(presented) and secrets.compare_digest(presented, self.token):
            state["rra_auth"] = "token"
            await self.app(scope, receive, send)
            return
        session = self.sessions.get(_cookie(scope, COOKIE_NAME)) if self.sessions else None
        if session is None or not self.token:
            await self._reject(
                scope,
                receive,
                send,
                401,
                "인증 토큰이 필요합니다.",
                headers={"www-authenticate": "Bearer"},
            )
            return
        if method in STATE_CHANGING:
            if not origin_allowed(scope, self.public_origin):
                await self._reject(scope, receive, send, 403, _ORIGIN_DETAIL)
                return
            if not self.sessions.csrf_ok(session, _header(scope, CSRF_HEADER)):
                await self._reject(
                    scope, receive, send, 403, "CSRF 토큰이 없거나 맞지 않습니다 (X-RRA-CSRF)."
                )
                return
        state["rra_auth"] = "session"
        state["rra_session_id"] = session.id
        await self.app(scope, receive, send)

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status: int,
        detail: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """거부 로그: 상태·메서드·경로·접속자 IP·Access 사용자 해시(이메일 원문 없음)."""
        state = scope.get("state") or {}
        log.info(
            "api.auth.reject status=%s method=%s path=%s ip=%s access_user=%s",
            status,
            scope.get("method", ""),
            scope.get("path", ""),
            state.get("rra_client_ip") or "-",
            state.get("rra_access_user") or "-",
        )
        await problem(status, detail, headers=headers)(scope, receive, send)


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
                await problem(411, "Content-Length 가 필요합니다.")(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        try:
            length = int(length_header)
        except ValueError:
            await problem(400, "Content-Length 형식 오류")(scope, receive, send)
            return
        if length > self.max_bytes:
            await problem(413, f"요청 본문이 상한 {self.max_bytes} bytes 를 넘습니다.")(
                scope, receive, send
            )
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
