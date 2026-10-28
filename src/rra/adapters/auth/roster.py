"""사번 명부 파일 읽기 (A2, `RosterReaderPort` 구현) — xlsx·csv 를 샌드박스(B)에서 열어 사번 열만
받는다.

- 경로는 검증(`open_validated`: 확장자·매직·크기·정규 파일)만 하고 fd 를 자식에 넘긴다. 복사하지
  않는다.
- 자식(`_roster_worker`)이 사번 열만 돌려준다. 다른 열은 부모에 오지 않는다.
- 실패는 `RosterReadError` 로만 — 메시지에 경로·값 없음(종류 코드만).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._inbox import error_name
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.application.ports.auth import RosterCells, RosterReadError
from rra.domain.rules.staff_roster import STAFF_COLUMN

FILE_FORMATS = frozenset({"xlsx", "csv"})
PARSER_FOR = {"xlsx": "staff_xlsx", "csv": "staff_csv"}
MAX_FILE_MB = 20.0
Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]

REASONS = {
    "HeaderNotFound": (
        "열 제목을 앞쪽 8행에서 찾지 못했습니다. --column <열 제목> 으로 지정하십시오."
    ),
    "SheetNotFound": "--sheet 로 지정한 시트가 없습니다.",
    "TooManyRows": "행이 상한을 넘습니다.",
    "UnknownEncoding": "CSV 인코딩을 읽지 못했습니다 (utf-8 또는 cp949 로 저장).",
    "BadExtension": "xlsx 또는 csv 파일만 받습니다.",
    "MagicMismatch": "파일 내용이 확장자와 다릅니다 (xls 는 xlsx 로 다시 저장).",
    "NotRegularFile": "파일을 열 수 없습니다 (링크·권한·없는 파일).",
    "EmptyFile": "파일이 비어 있습니다.",
    "TooLarge": f"파일이 {MAX_FILE_MB:g}MB 를 넘습니다.",
}


def _error(code: str) -> RosterReadError:
    return RosterReadError(code, REASONS.get(code))


class _Payload(BaseModel):
    """자식 출력 재검증 — 값은 문자열(64자 이내)·None 만."""

    model_config = ConfigDict(extra="ignore")
    sheet: str = ""
    header_row: int = Field(ge=1)
    cells: list[tuple[int, str | None]] = Field(default_factory=list)


class RosterReader:
    def __init__(self, limits: SandboxLimits, runner: Runner = run_parser):
        self.limits = replace(limits, max_input_mb=min(limits.max_input_mb, MAX_FILE_MB))
        self._runner = runner

    async def read(
        self, path: Path, *, sheet: str | None = None, column: str | None = None
    ) -> RosterCells:
        limits = replace(
            self.limits, extra={"sheet": sheet or None, "column": column or STAFF_COLUMN}
        )
        max_bytes = int(limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(Path(path), max_bytes=max_bytes, allowed=FILE_FORMATS)
        except FileRejected as exc:
            raise _error(error_name(exc)) from None
        with vf:
            try:
                raw = await self._runner(vf.fd, PARSER_FOR[vf.fmt], limits)
            except SandboxError as exc:
                raise _error(error_name(exc)) from None
        try:
            payload = _Payload.model_validate(raw)
        except ValidationError:
            raise _error("BadPayload") from None
        return RosterCells(
            sheet=payload.sheet,
            header_row=payload.header_row,
            cells=tuple((int(r), v) for r, v in payload.cells),
        )
