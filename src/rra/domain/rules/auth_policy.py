"""로그인 정책 — 순수 규칙 (레인 A, 2026-10-27).

- 가명 ID 형식: staff:<HMAC 앞 12자(hex)> / guest:<아이디> / admin:local. run 저장소 키(디렉터리
  이름)는 `run_user()` — `staff-…`, `guest-…`, 관리자는 `local`(기존 run 이 있는 곳).
- 잠금·지연 판정(`LoginGuard`): 계정별 연속 실패 N회 → 잠금, 접속자 IP 별 창 안 실패 M회 → 잠금,
  전체 실패가 창 안 K회를 넘으면 응답 지연. 시각은 호출자가 넣는다(테스트 가능).
- 일일 생성 상한(`daily_run_limit`, `daily_limit_reached`): 공용 계정·직원 1인 기준. 관리자는 없음.
- 사번·비밀번호 원문은 이 모듈에 들어오지 않는다 — 계정 키는 가명 ID 다.
"""

from __future__ import annotations

import ipaddress
import re
from collections import deque
from dataclasses import dataclass, field

from rra.domain.models.principal import Principal

LOGIN_FAILED_MESSAGE = "사번 또는 아이디·비밀번호를 확인하세요"
STAFF_PREFIX = "staff:"
GUEST_PREFIX = "guest:"
ADMIN_ID = "admin:local"
ADMIN_RUN_USER = "local"
STAFF_PSEUDONYM_HEX = 12

_GUEST_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,19}$")
_STAFF_NO = re.compile(r"^[A-Za-z0-9-]{2,32}$")
_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def valid_guest_id(value: str) -> bool:
    """공용 아이디: 소문자·숫자·_·- 2~20자 (run 디렉터리 이름 규칙 안)."""
    return bool(_GUEST_ID.match(value or ""))


DEFAULT_MIN_PASSWORD_LENGTH = 8


def valid_password(value: str, min_length: int = DEFAULT_MIN_PASSWORD_LENGTH) -> bool:
    """공용 계정 비밀번호 — 비어 있지 않고 최소 길이 이상.
    최소 길이는 설정(auth.yaml guest.min_password_length)."""
    return bool(value) and len(value) >= max(1, int(min_length))


def valid_staff_no(value: str) -> bool:
    """사번 형식(영숫자·하이픈 2~32자). 값은 검사만 하고 어디에도 남기지 않는다."""
    return bool(_STAFF_NO.match(value or ""))


def lockout_ip(ip: str | None) -> str | None:
    """IP 별 잠금에 쓸 키. 접속자를 알 수 없는 주소(빈 값·루프백 — 역프록시 Funnel 뒤에서는
    모든 외부 접속이 127.0.0.1 로 보인다)는 None → IP 별 잠금을 걸지 않는다(계정별 잠금·전체
    지연은 그대로). 한 사람의 오타가 동료 전원을 잠그던 문제(2026-10-28)."""
    value = (ip or "").strip()
    if not value or value in ("unknown", "-"):
        return None
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    return None if addr.is_loopback or addr.is_unspecified else str(addr)


def staff_pseudonym(digest_hex: str) -> str:
    """HMAC-SHA256 hex → `staff:<앞 12자>`."""
    head = (digest_hex or "").lower()[:STAFF_PSEUDONYM_HEX]
    if not _HEX12.match(head):
        raise ValueError("HMAC 다이제스트 형식이 올바르지 않습니다.")
    return f"{STAFF_PREFIX}{head}"


def guest_principal(guest_id: str) -> Principal:
    if not valid_guest_id(guest_id):
        raise ValueError("공용 아이디 형식이 올바르지 않습니다.")
    return Principal(kind="guest", id=f"{GUEST_PREFIX}{guest_id}")


def staff_principal(digest_hex: str) -> Principal:
    return Principal(kind="staff", id=staff_pseudonym(digest_hex))


def admin_principal() -> Principal:
    return Principal(kind="admin", id=ADMIN_ID)


def run_user(principal: Principal) -> str:
    """run 저장소 키(`runs/<user>/`). 관리자는 기존 `local`, 그 외는 가명 ID 의 `:` 를 `-` 로."""
    if principal.kind == "admin":
        return ADMIN_RUN_USER
    return principal.id.replace(":", "-", 1)


def kind_label(kind: str) -> str:
    return {"admin": "관리자", "staff": "직원", "guest": "공용 계정"}.get(kind, kind)


# ── 일일 생성 상한 ───────────────────────────────────────
@dataclass(frozen=True)
class DailyLimits:
    guest_runs_per_day: int = 10
    staff_runs_per_day: int = 20


def daily_run_limit(principal: Principal, limits: DailyLimits | None = None) -> int | None:
    """None 이면 상한 없음(관리자)."""
    limits = limits or DailyLimits()
    if principal.kind == "guest":
        return limits.guest_runs_per_day
    if principal.kind == "staff":
        return limits.staff_runs_per_day
    return None


def daily_limit_reached(created_at: list[str], today: str, limit: int | None) -> bool:
    """created_at 은 ISO 시각 문자열, today 는 `YYYY-MM-DD`(같은 시간대 기준)."""
    if limit is None:
        return False
    return sum(1 for ts in created_at if (ts or "")[:10] == today) >= limit


# ── 무차별 대입 방지 ─────────────────────────────────────
@dataclass(frozen=True)
class LockoutPolicy:
    account_failures: int = 5  # 계정별 연속 실패 → 잠금
    account_lock_sec: int = 600
    ip_failures: int = 20  # 접속자 IP 별 창 안 실패 → 잠금
    ip_window_sec: int = 600
    global_failures: int = 50  # 전체 실패가 창 안에 이를 넘으면 응답 지연
    global_window_sec: int = 600
    global_delay_sec: float = 2.0


@dataclass
class LoginGuard:
    """실패 기록으로 잠금·지연을 판정한다. 메모리에만(프로세스 재시작이면 초기화). 키는 가명
    ID·IP 문자열 — 사번·비밀번호 원문은 받지 않는다."""

    policy: LockoutPolicy = field(default_factory=LockoutPolicy)
    _account: dict[str, tuple[int, float]] = field(default_factory=dict)  # 키 → (연속 실패, 마지막)
    _ip: dict[str, deque[float]] = field(default_factory=dict)
    _all: deque[float] = field(default_factory=deque)

    def locked(self, account: str | None, ip: str | None, now: float) -> bool:
        if account is not None:
            count, last = self._account.get(account, (0, 0.0))
            if count >= self.policy.account_failures and now - last < self.policy.account_lock_sec:
                return True
        if ip is not None:
            window = self._ip.get(ip)
            if window is not None:
                self._trim(window, now - self.policy.ip_window_sec)
                if len(window) >= self.policy.ip_failures:
                    return True
        return False

    def delay(self, now: float) -> float:
        """전체 실패가 창 안에 상한을 넘으면 지연 초, 아니면 0."""
        self._trim(self._all, now - self.policy.global_window_sec)
        return self.policy.global_delay_sec if len(self._all) > self.policy.global_failures else 0.0

    def failure(self, account: str | None, ip: str | None, now: float) -> None:
        if account is not None:
            count, last = self._account.get(account, (0, 0.0))
            if now - last >= self.policy.account_lock_sec:
                count = 0  # 잠금 시간이 지났으면 새로 센다
            self._account[account] = (count + 1, now)
        if ip is not None:
            window = self._ip.setdefault(ip, deque())
            window.append(now)
            self._trim(window, now - self.policy.ip_window_sec)
        self._all.append(now)
        self._trim(self._all, now - self.policy.global_window_sec)
        if len(self._ip) > 10_000:  # 메모리 상한 — 오래된 IP 부터 버린다
            self._ip.pop(next(iter(self._ip)))

    def success(self, account: str | None) -> None:
        if account is not None:
            self._account.pop(account, None)

    @staticmethod
    def _trim(window: deque[float], cutoff: float) -> None:
        while window and window[0] <= cutoff:
            window.popleft()
