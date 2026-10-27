"""보안 G — REST 진입점 앞단 ASGI 미들웨어 (프레임워크 비의존, Starlette 응답만 사용).

- TokenAuthMiddleware: RRA_API_TOKEN 헤더 또는 세션 쿠키(SessionStore). 쿠키 인증의 상태 변경 요청은
  X-RRA-CSRF 필수. /healthz 와 정적 파일은 예외, POST /v1/session 은 로그인이라 라우트가 토큰 검사.
- BodyLimitMiddleware: 본문 크기 상한 (Content-Length 없는 본문은 411, 초과는 413).
- SecurityHeadersMiddleware: CSP(API 는 default-src 'none', SPA 는 'self' 만·인라인 없음)·
  X-Frame-Options·Referrer-Policy·nosniff·no-store.
- 오류 응답은 전부 application/problem+json (problem()).
- client_ip / access_user_hash: 역프록시(Cloudflare Tunnel) 뒤 접속자 IP(CF-Connecting-IP 는
  trust_cf 이고 peer 가 127.0.0.1 일 때만)·Access 사용자 이메일 해시(앞 12자, 원문 없음).
CORS 미들웨어는 아예 넣지 않는다 (동일 출처만. 역프록시 공개 주소는 public_origin 으로 Origin
검사에만 허용). 파일 업로드 엔드포인트는 없다.
"""

from rra.adapters.security.client_ip import access_user_hash, client_ip
from rra.adapters.security.middleware import (
    API_CSP,
    AUTH_HEADER,
    PROBLEM_JSON,
    SECURITY_HEADERS,
    SPA_CSP,
    BodyLimitMiddleware,
    SecurityHeadersMiddleware,
    TokenAuthMiddleware,
    origin_allowed,
    problem,
)
from rra.adapters.security.sessions import COOKIE_NAME, CSRF_HEADER, Session, SessionStore

__all__ = [
    "API_CSP",
    "AUTH_HEADER",
    "COOKIE_NAME",
    "CSRF_HEADER",
    "PROBLEM_JSON",
    "SECURITY_HEADERS",
    "SPA_CSP",
    "BodyLimitMiddleware",
    "SecurityHeadersMiddleware",
    "Session",
    "SessionStore",
    "TokenAuthMiddleware",
    "access_user_hash",
    "client_ip",
    "origin_allowed",
    "problem",
]
