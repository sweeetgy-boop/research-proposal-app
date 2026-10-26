"""세션 쿠키 저장소 (프론트엔드용) — 메모리, TTL, CSRF 토큰. 프로세스 재시작이면 전부 만료.

- 세션 id·CSRF 토큰은 secrets.token_urlsafe(32). 비교는 상수 시간.
- 사용자는 단일 토큰 소유자(LOCAL_USER) 한 명. 세션은 "토큰을 아는 브라우저" 표시일 뿐이다.
- 쿠키: httpOnly, SameSite=Strict, Path=/, https 요청이면 Secure. 값은 세션 id 만.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

COOKIE_NAME = "rra_session"
CSRF_HEADER = "x-rra-csrf"
DEFAULT_TTL_SEC = 12 * 3600
MAX_SESSIONS = 100


@dataclass(frozen=True)
class Session:
    id: str
    csrf: str
    expires_at: float


class SessionStore:
    def __init__(self, *, ttl_sec: int = DEFAULT_TTL_SEC, clock: Callable[[], float] = time.time):
        self.ttl = int(ttl_sec)
        self._clock = clock
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        self._sweep()
        if len(self._sessions) >= MAX_SESSIONS:  # 가장 오래된 것부터 버린다
            oldest = min(self._sessions.values(), key=lambda s: s.expires_at)
            self._sessions.pop(oldest.id, None)
        session = Session(
            id=secrets.token_urlsafe(32),
            csrf=secrets.token_urlsafe(32),
            expires_at=self._clock() + self.ttl,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        self._sweep()
        for sid, session in self._sessions.items():  # 길이 노출 없는 상수 시간 비교
            if secrets.compare_digest(sid, session_id):
                return session
        return None

    def csrf_ok(self, session: Session, presented: str | None) -> bool:
        return bool(presented) and secrets.compare_digest(session.csrf, presented or "")

    def drop(self, session_id: str | None) -> None:
        if session_id:
            self._sessions.pop(session_id, None)

    def _sweep(self) -> None:
        now = self._clock()
        for sid in [s for s, v in self._sessions.items() if v.expires_at <= now]:
            self._sessions.pop(sid, None)

    def __len__(self) -> int:
        self._sweep()
        return len(self._sessions)
