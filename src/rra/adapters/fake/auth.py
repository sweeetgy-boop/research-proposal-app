"""가짜 모드(RRA_FAKE_LLM=1) 로그인 저장소 — e2e 전용 고정 계정. 운영에서는 조립되지 않는다.

직원 사번 `E2E-0001`·`E2E-0002`, 공용 계정 `e2e` / `e2e-password-1`. 실제 data/auth 는 건드리지
않는다 (e2e 가 원 저장소 데이터를 쓰지 않게).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

FAKE_STAFF = ("E2E-0001", "E2E-0002")
FAKE_GUEST = ("e2e", "e2e-password-1")


class ScriptedAuthStore:
    def __init__(self) -> None:
        self._staff: set[str] = set(FAKE_STAFF)
        self._guest: tuple[str, str] | None = FAKE_GUEST

    def verify_staff(self, staff_no: str) -> str | None:
        if staff_no not in self._staff:
            return None
        return hashlib.sha256(f"fake:{staff_no}".encode()).hexdigest()

    def staff_enabled(self) -> bool:
        return bool(self._staff)

    def verify_guest(self, guest_id: str, password: str) -> bool:
        if self._guest is None:
            return False
        return secrets.compare_digest(guest_id, self._guest[0]) and secrets.compare_digest(
            password, self._guest[1]
        )

    def guest_id(self) -> str | None:
        return self._guest[0] if self._guest else None

    def add_staff(self, staff_no: str) -> bool:
        before = len(self._staff)
        self._staff.add(staff_no)
        return len(self._staff) > before

    def remove_staff(self, staff_no: str) -> bool:
        if staff_no not in self._staff:
            return False
        self._staff.discard(staff_no)
        return True

    def staff_count(self) -> int:
        return len(self._staff)

    def set_guest(self, guest_id: str, password: str) -> None:
        self._guest = (guest_id, password)

    def disable_guest(self) -> bool:
        had = self._guest is not None
        self._guest = None
        return had

    def status(self) -> dict[str, Any]:
        return {"staff_count": len(self._staff), "guest": self._guest is not None, "secret": True}
