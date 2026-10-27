"""표 텍스트 만들기 (순수) — 샌드박스가 돌려준 줄 목록(CSV) 을 ' | ' 구분 표로, 앞 max_rows 행만."""

from __future__ import annotations

import csv
from collections.abc import Sequence


def csv_lines_to_table(
    lines: Sequence[str], *, max_rows: int = 400, max_cols: int = 40
) -> tuple[str, int]:
    """(표 텍스트, 전체 데이터 행 수). 첫 줄은 머리글. 빈 줄은 건너뛴다."""
    rows = [r for r in csv.reader([ln for ln in lines if ln.strip()])]
    if not rows:
        return "", 0
    header = [c.strip() for c in rows[0][:max_cols]]
    data = rows[1:]
    out = [" | ".join(header)]
    for r in data[:max_rows]:
        out.append(" | ".join(c.strip() for c in r[:max_cols]))
    if len(data) > max_rows:
        out.append(f"… (전체 {len(data)}행 중 {max_rows}행만 표시)")
    return "\n".join(out), len(data)
