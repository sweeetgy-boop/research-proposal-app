"""로그인 포트 (레인 A). 사번·비밀번호 원문은 어댑터 안에서 HMAC·scrypt 로만 다룬다."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class RosterReadError(RuntimeError):
    """명부 파일 읽기 실패 — `code` 는 종류(식별자), 메시지는 안내 문구. 경로·사번 값은 싣지
    않는다."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or f"파일을 읽지 못했습니다 ({code}).")


@dataclass(frozen=True)
class RosterCells:
    """명부에서 읽은 사번 열 — (파일 행 번호, 셀 문자열|None). 다른 열은 없다. repr 에 값 없음."""

    sheet: str
    header_row: int
    cells: tuple[tuple[int, str | None], ...] = field(repr=False)

    def __repr__(self) -> str:
        return (
            f"RosterCells(sheet={self.sheet!r}, header_row={self.header_row}, n={len(self.cells)})"
        )


@runtime_checkable
class RosterReaderPort(Protocol):
    """xlsx·csv 명부에서 사번 열만 읽는다 (어댑터는 샌드박스). 실패는 RosterReadError."""

    async def read(
        self, path: Path, *, sheet: str | None = None, column: str | None = None
    ) -> RosterCells: ...


@dataclass(frozen=True)
class StaffImportResult:
    """일괄 등록 결과 — 개수만."""

    added: int = 0  # 새로 등록
    existing: int = 0  # 이미 있음
    removed: int = 0  # replace 로 빠진 기존 등록
    saved: bool = False  # False 면 dry_run


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

    def import_staff(
        self, staff_nos: Iterable[str], *, replace: bool = False, dry_run: bool = False
    ) -> StaffImportResult:
        """정규화된 사번 여러 개를 한 번에. replace 면 목록을 이 집합으로 바꾼다. dry_run 은
        저장 없이 집계만. 결과는 개수만 — 값·다이제스트 없음."""
        ...

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
