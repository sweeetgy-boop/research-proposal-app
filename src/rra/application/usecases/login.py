"""로그인 유스케이스 (레인 A) — 직원(사번)·공용 계정(아이디·비밀번호).

- 실패 메시지는 하나(LOGIN_FAILED_MESSAGE)로 통일: 등록 여부·잠금 여부를 구분해 알리지 않는다.
- 잠금·지연은 domain/rules/auth_policy.LoginGuard. 지연은 돌려주기만 하고 잠은 진입점이 잔다.
- 관리 토큰(`token`)은 계정 키 없이 접속자 IP·전체 지연만 — 남이 관리자를 잠글 수 없다. 토큰 비교는
  진입점(SessionAuth)이 하고 결과(bool)만 받는다.
- 잠금 상태는 `LoginFailed.blocked`(잠긴 범위)·`log_lines`(종류·범위·IP 만) 로 알린다 —
  진입점은 찍기만 한다.
- 사번·비밀번호·토큰 원문은 저장소 포트로 넘길 뿐 로그·예외 메시지·결과에 싣지 않는다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from rra.application.ports.auth import AuthStorePort
from rra.domain.models import Principal
from rra.domain.rules import auth_policy
from rra.domain.rules.auth_policy import (
    LOGIN_FAILED_MESSAGE,
    FailureOutcome,
    LockScope,
    LoginGuard,
)
from rra.domain.rules.staff_roster import normalize_staff_no


class LoginFailed(ValueError):
    """사번·아이디·비밀번호 불일치 또는 잠금 — 메시지는 항상 같다."""

    def __init__(
        self,
        *,
        delay_sec: float = 0.0,
        blocked: LockScope | None = None,
        outcome: FailureOutcome | None = None,
        log_lines: tuple[str, ...] = (),
    ):
        super().__init__(LOGIN_FAILED_MESSAGE)
        self.delay_sec = delay_sec
        self.blocked = blocked  # 이 시도 전에 이미 잠겨 있던 범위 (없으면 None)
        self.outcome = outcome or FailureOutcome()  # 이 실패로 시작된 잠금·지연
        self.log_lines = log_lines  # 잠금 상태 로그 문장 (값 없음) — 진입점이 WARNING 으로 찍는다


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
        ip = auth_policy.lockout_ip(ip)  # 접속자를 모르면(루프백·빈 값) IP 별 잠금 없음
        staff_no = normalize_staff_no(staff_no)  # 일괄 등록과 같은 규칙(공백·하이픈 제거)
        digest = self.store.verify_staff(staff_no) if auth_policy.valid_staff_no(staff_no) else None
        # 계정 키는 가명 ID — 미등록 사번은 계정 키 없이 IP·전체만 센다
        account = auth_policy.staff_pseudonym(digest) if digest else None
        blocked = self.guard.lock_scope(account, ip, now)
        if blocked is not None or digest is None:
            raise self._fail("staff", account, ip, now, delay, blocked)
        self.guard.success(account)
        # 시험 계정(배포 확인용 임시 사번)이면 주체에 표시 — 선택 기록·측정 줄이 집계에서 빠진다
        test = bool(self.store.is_test_staff(digest))
        return LoginResult(auth_policy.staff_principal(digest, test=test), delay_sec=delay)

    def guest(self, guest_id: str, password: str, *, ip: str | None = None) -> LoginResult:
        now = self._clock()
        delay = self.guard.delay(now)
        ip = auth_policy.lockout_ip(ip)
        guest_id = (guest_id or "").strip().lower()
        account = f"{auth_policy.GUEST_PREFIX}{guest_id}" if guest_id else None
        blocked = self.guard.lock_scope(account, ip, now)
        if blocked is not None:
            raise self._fail("guest", account, ip, now, delay, blocked)
        ok = (
            auth_policy.valid_guest_id(guest_id)
            and bool(password)
            and self.store.verify_guest(guest_id, password)
        )
        if not ok:
            raise self._fail("guest", account, ip, now, delay, None)
        self.guard.success(account)
        return LoginResult(auth_policy.guest_principal(guest_id), delay_sec=delay)

    def token(self, ok: bool, *, ip: str | None = None) -> LoginResult:
        """관리 토큰 로그인. `ok` 는 진입점이 상수 시간 비교로 낸 결과. 계정 키로는 세지 않는다
        (IP 창·전체 지연만) — 접속자 IP 가 잠겨 있으면 맞는 토큰도 실패. IP 를 모르면(루프백)
        잠금 없음."""
        now = self._clock()
        delay = self.guard.delay(now)
        ip = auth_policy.lockout_ip(ip)
        blocked = self.guard.lock_scope(None, ip, now)
        if blocked is not None or not ok:
            raise self._fail("token", None, ip, now, delay, blocked)
        return LoginResult(auth_policy.admin_principal(), delay_sec=delay)

    def _fail(
        self,
        kind: str,
        account: str | None,
        ip: str | None,
        now: float,
        delay: float,
        blocked: LockScope | None,
    ) -> LoginFailed:
        outcome = self.guard.failure(account, ip, now)
        lines = auth_policy.lock_log_lines(
            kind, ip, blocked=blocked, outcome=outcome, policy=self.guard.policy
        )
        return LoginFailed(delay_sec=delay, blocked=blocked, outcome=outcome, log_lines=lines)

    def status(self) -> dict[str, bool]:
        """화면용: 어떤 로그인 방식이 열려 있는가 (값 없음)."""
        return {
            "staff_enabled": self.store.staff_enabled(),
            "guest_enabled": self.store.guest_id() is not None,
        }
