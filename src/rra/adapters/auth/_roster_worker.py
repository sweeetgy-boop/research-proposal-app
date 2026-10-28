"""사번 명부 파서 — 샌드박스 자식 프로세스(`_worker` PARSERS staff_xlsx·staff_csv)에서만
import 된다.

사번 열 하나만 밖으로 낸다. 다른 열(이름·부서 등)은 열 제목 비교에만 쓰고 값은 자식 프로세스에서
버린다.
출력: {"sheet": 시트 이름, "header_row": 머리글 행 번호(1-based), "cells": [[행 번호, 값|null], …]}.
옵션은 limits["extra"]: {"sheet": 시트 이름|null, "column": 열 제목}.
행 번호는 파일 기준(빈 행 포함)이라 운영자가 엑셀에서 그 행을 바로 찾을 수 있다.

xlsx 는 zip 검사(엔트리 수·경로·압축비) 뒤 openpyxl read_only, csv 는 utf-8-sig → cp949.
"""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

from rra.adapters.sources.alio.extract.csv_catalog import decode
from rra.adapters.sources.alio.extract.hwpx import check_archive
from rra.domain.rules.staff_roster import MAX_HEADER_SCAN, STAFF_COLUMN, header_matches

MAX_COLS = 64
MAX_CELL_CHARS = 64


class HeaderNotFound(ValueError):
    """열 제목을 앞쪽 행에서 찾지 못함."""


class SheetNotFound(ValueError):
    pass


class TooManyRows(ValueError):
    pass


def _text(value: Any) -> str | None:
    """셀 → 문자열. 숫자는 정규화 규칙(domain)에 맡기고 여기서는 문자열만 만든다."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text[:MAX_CELL_CHARS] if text else None


def _collect(rows: Any, column: str, max_rows: int) -> dict[str, Any]:
    """rows: (행 번호, [셀 …]) 반복. 머리글을 찾은 뒤 그 열만 모은다."""
    header_row = col_index = None
    cells: list[list[Any]] = []
    for row_no, row in rows:
        if header_row is None:
            if row_no > MAX_HEADER_SCAN:
                raise HeaderNotFound(column)
            for i, cell in enumerate(row[:MAX_COLS]):
                if header_matches(cell, column):
                    header_row, col_index = row_no, i
                    break
            continue
        if len(cells) >= max_rows:
            raise TooManyRows("rows")
        value = row[col_index] if col_index is not None and col_index < len(row) else None
        cells.append([row_no, _text(value)])
    if header_row is None:
        raise HeaderNotFound(column)
    return {"header_row": header_row, "cells": cells}


def extract_xlsx(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import openpyxl

    extra = limits.get("extra") or {}
    column = str(extra.get("column") or STAFF_COLUMN)
    wanted = extra.get("sheet")
    cap = int(float(limits["max_input_mb"]) * 1024 * 1024)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        check_archive(
            zf,
            cap=cap,
            ratio=int(limits["max_zip_ratio"]),
            max_entries=int(limits["max_zip_entries"]),
        )
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        if wanted:
            matches = [ws for ws in wb.worksheets if header_matches(ws.title, str(wanted))]
            if not matches:
                raise SheetNotFound("sheet")
            ws = matches[0]
        else:
            ws = wb.worksheets[0]
        rows = (
            (i, list(row))
            for i, row in enumerate(ws.iter_rows(max_col=MAX_COLS, values_only=True), start=1)
        )
        result = _collect(rows, column, int(limits["max_csv_rows"]))
        result["sheet"] = str(ws.title)[:100]
        return result
    finally:
        wb.close()


def extract_csv(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    extra = limits.get("extra") or {}
    column = str(extra.get("column") or STAFF_COLUMN)
    csv.field_size_limit(MAX_CELL_CHARS * 64)
    reader = csv.reader(io.StringIO(decode(data), newline=""))
    rows = ((i, [c for c in row[:MAX_COLS]]) for i, row in enumerate(reader, start=1))
    result = _collect(rows, column, int(limits["max_csv_rows"]))
    result["sheet"] = ""
    return result
