"""보안 G — REST 진입점 앞단 ASGI 미들웨어 (프레임워크 비의존, Starlette 응답만 사용).

- TokenAuthMiddleware: RRA_API_TOKEN 헤더 필수 (secrets.compare_digest). /healthz 만 예외.
- BodyLimitMiddleware: 본문 크기 상한 (Content-Length 없는 본문은 411, 초과는 413).
- SecurityHeadersMiddleware: CSP·X-Frame-Options·Referrer-Policy·nosniff·no-store.
CORS 미들웨어는 아예 넣지 않는다 (동일 출처만). 파일 업로드 엔드포인트는 없다.
"""

from rra.adapters.security.middleware import (
    AUTH_HEADER,
    SECURITY_HEADERS,
    BodyLimitMiddleware,
    SecurityHeadersMiddleware,
    TokenAuthMiddleware,
)

__all__ = [
    "AUTH_HEADER",
    "SECURITY_HEADERS",
    "BodyLimitMiddleware",
    "SecurityHeadersMiddleware",
    "TokenAuthMiddleware",
]
