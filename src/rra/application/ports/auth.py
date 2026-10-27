"""로그인 포트 (레인 A). 사번·비밀번호 원문은 어댑터 안에서 HMAC·scrypt 로만 다룬다."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthStorePort(Protocol):
    """직원 사번 목록(HMAC)·공용 계정(scrypt) 저장소. 원문은 어디에도 남기지 않는다."""

    def verify_staff(self, staff_no: str) -> str | None:
        """등록된 사번이면 HMAC hex 다이제스트, 아니면 None. 목록이 비면 항상 None."""
        ...

    def staff_enabled(self) -> bool:
        """등록된 사번이 1개 이상인가 (비면 직원 로그인 비활성)."""
        ...

    def verify_guest(self, guest_id: str, password: str) -> bool: ...

    def guest_id(self) -> str | None:
        """등록된 공용 아이디 (없거나 비활성이면 None)."""
        ...

    def add_staff(self, staff_no: str) -> bool:
        """추가. 이미 있으면 False."""
        ...

    def remove_staff(self, staff_no: str) -> bool: ...

    def staff_count(self) -> int: ...

    def set_guest(self, guest_id: str, password: str) -> None: ...

    def disable_guest(self) -> bool: ...

    def status(self) -> dict[str, Any]:
        """설정 여부만: {"staff_count": n, "guest": bool, "secret": bool}."""
        ...


class BudgetExhausted(RuntimeError):
    """외부 LLM 일일 전체 상한에 이르렀다 — 어댑터가 호출 대신 던진다."""


@runtime_checkable
class DailyBudgetPort(Protocol):
    """외부 LLM 호출 일일 전체 상한 카운터 (자정에 초기화)."""

    def try_spend(self, n: int = 1) -> bool:
        """n 만큼 쓸 수 있으면 더하고 True, 상한이면 False."""
        ...

    def exhausted(self) -> bool: ...

    def remaining(self) -> int: ...
