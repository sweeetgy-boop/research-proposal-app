"""로그인 유스케이스 (레인 A) — 직원(사번)·공용 계정(아이디·비밀번호).

- 실패 메시지는 하나(LOGIN_FAILED_MESSAGE)로 통일: 등록 여부·잠금 여부를 구분해 알리지 않는다.
- 잠금·지연은 domain/rules/auth_policy.LoginGuard. 지연은 돌려주기만 하고 잠은 진입점이 잔다.
- 사번·비밀번호 원문은 저장소 포트로 넘길 뿐 로그·예외 메시지·결과에 싣지 않는다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from rra.application.ports.auth import AuthStorePort
from rra.domain.models import Principal
from rra.domain.rules import auth_policy
from rra.domain.rules.auth_policy import LOGIN_FAILED_MESSAGE, LoginGuard
from rra.domain.rules.staff_roster import normalize_staff_no


class LoginFailed(ValueError):
    """사번·아이디·비밀번호 불일치 또는 잠금 — 메시지는 항상 같다."""

    def __init__(self, *, delay_sec: float = 0.0):
        super().__init__(LOGIN_FAILED_MESSAGE)
        self.delay_sec = delay_sec


@dataclass(frozen=True)
class LoginResult:
    principal: Principal
    delay_sec: float = 0.0  # 전체 실패 과다 때 응답을 늦추는 시간 (성공에도 적용)


class Login:
    def __init__(
        self,
        store: AuthStorePort,
        *,
        guard: LoginGuard | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.store = store
        self.guard = guard or LoginGuard()
        self._clock = clock

    def staff(self, staff_no: str, *, ip: str | None = None) -> LoginResult:
        """사번 로그인. 등록 목록이 비면 비활성(실패)."""
        now = self._clock()
        delay = self.guard.delay(now)
        staff_no = normalize_staff_no(staff_no)  # 일괄 등록과 같은 규칙(공백·하이픈 제거)
        digest = self.store.verify_staff(staff_no) if auth_policy.valid_staff_no(staff_no) else None
        # 계정 키는 가명 ID — 미등록 사번은 계정 키 없이 IP·전체만 센다
        account = auth_policy.staff_pseudonym(digest) if digest else None
        if self.guard.locked(account, ip, now) or digest is None:
            self.guard.failure(account, ip, now)
            raise LoginFailed(delay_sec=delay)
        self.guard.success(account)
        return LoginResult(auth_policy.staff_principal(digest), delay_sec=delay)

    def guest(self, guest_id: str, password: str, *, ip: str | None = None) -> LoginResult:
        now = self._clock()
        delay = self.guard.delay(now)
        guest_id = (guest_id or "").strip().lower()
        account = f"{auth_policy.GUEST_PREFIX}{guest_id}" if guest_id else None
        if self.guard.locked(account, ip, now):
            self.guard.failure(account, ip, now)
            raise LoginFailed(delay_sec=delay)
        ok = (
            auth_policy.valid_guest_id(guest_id)
            and bool(password)
            and self.store.verify_guest(guest_id, password)
        )
        if not ok:
            self.guard.failure(account, ip, now)
            raise LoginFailed(delay_sec=delay)
        self.guard.success(account)
        return LoginResult(auth_policy.guest_principal(guest_id), delay_sec=delay)

    def status(self) -> dict[str, bool]:
        """화면용: 어떤 로그인 방식이 열려 있는가 (값 없음)."""
        return {
            "staff_enabled": self.store.staff_enabled(),
            "guest_enabled": self.store.guest_id() is not None,
        }
