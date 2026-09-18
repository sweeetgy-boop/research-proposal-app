"""카탈로그 CSV → 행 dict 목록. 샌드박스 자식 프로세스에서만 import 된다.

인코딩은 utf-8-sig → cp949 순서로 시도한다 (공공데이터포털 파일은 대개 cp949).
해석(컬럼 매핑·기관 필터)은 본체의 순수 함수 `alio.catalog.normalize_catalog_row` 가 한다.
"""

from __future__ import annotations

import csv
import io
from typing import Any

MAX_FIELD_CHARS = 10_000
MAX_COLUMNS = 200


class UnknownEncoding(ValueError):
    pass


class TooManyRows(ValueError):
    pass


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnknownEncoding("encoding")


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    csv.field_size_limit(MAX_FIELD_CHARS)
    max_rows = int(limits["max_csv_rows"])
    reader = csv.reader(io.StringIO(decode(data), newline=""))
    header = [h.strip() for h in next(reader, [])][:MAX_COLUMNS]
    rows: list[dict[str, str]] = []
    for values in reader:
        if len(rows) >= max_rows:
            raise TooManyRows("rows")
        if not any(v.strip() for v in values):
            continue
        rows.append({h: v.strip() for h, v in zip(header, values, strict=False) if h})
    return {"header": header, "rows": rows}
