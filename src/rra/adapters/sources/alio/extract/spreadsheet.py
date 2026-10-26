"""엑셀(xlsx·xls) 시트 → 문자열 표. 샌드박스 자식 프로세스에서만 import 된다.

- xlsx: zip 이므로 hwpx 와 같은 압축 검사(엔트리 수·경로·압축비) 뒤 openpyxl read_only 로 읽는다.
  수식은 계산값(data_only), 날짜는 ISO 문자열.
- xls: xlrd 2.x (xls 전용, 매크로·외부 링크 해석 없음).
행·열·셀 길이 상한은 limits 로 받는다. 열 이름 해석은 본체의 순수 함수가 한다.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from typing import Any

from rra.adapters.sources.alio.extract.hwpx import check_archive

MAX_SHEETS = 50
MAX_COLS = 64
MAX_CELL_CHARS = 2000


class TooManyRows(ValueError):
    pass


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    text = " ".join(str(value).split())
    return text[:MAX_CELL_CHARS] if text else None


def _trim(cells: list[str | None]) -> list[str | None]:
    """뒤쪽 빈 셀 제거 (read_only 는 max_col 까지 채운다). 전부 비면 []."""
    while cells and cells[-1] is None:
        cells.pop()
    return cells


def extract_xlsx(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import openpyxl

    cap = int(float(limits["max_input_mb"]) * 1024 * 1024)
    max_rows = int(limits["max_csv_rows"])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        check_archive(
            zf,
            cap=cap,
            ratio=int(limits["max_zip_ratio"]),
            max_entries=int(limits["max_zip_entries"]),
        )
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = []
    try:
        for ws in wb.worksheets[:MAX_SHEETS]:
            rows: list[list[str | None]] = []
            for row in ws.iter_rows(max_col=MAX_COLS, values_only=True):
                if len(rows) >= max_rows:
                    raise TooManyRows("rows")
                cells = _trim([_cell(v) for v in row])
                if cells:
                    rows.append(cells)
            sheets.append({"name": str(ws.title)[:100], "rows": rows})
    finally:
        wb.close()
    return {"sheets": sheets}


def extract_xls(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import xlrd

    max_rows = int(limits["max_csv_rows"])
    book = xlrd.open_workbook(file_contents=data, on_demand=False)
    sheets = []
    for sheet in book.sheets()[:MAX_SHEETS]:
        if sheet.nrows > max_rows:
            raise TooManyRows("rows")
        rows = []
        for r in range(sheet.nrows):
            cells = []
            for c in range(min(sheet.ncols, MAX_COLS)):
                cell = sheet.cell(r, c)
                value: Any = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        value = xlrd.xldate_as_datetime(value, book.datemode)
                    except (ValueError, OverflowError):
                        value = None
                elif cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_ERROR:
                    value = None
                elif cell.ctype == xlrd.XL_CELL_NUMBER and float(value).is_integer():
                    value = int(value)
                cells.append(_cell(value))
            cells = _trim(cells)
            if cells:
                rows.append(cells)
        sheets.append({"name": str(sheet.name)[:100], "rows": rows})
    return {"sheets": sheets}
