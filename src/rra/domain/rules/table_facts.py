"""표 → 사실(TableFact) 규칙 — 순수 (P2-8).

입력은 어댑터가 넘긴 문자열 격자(`ParsedTable.rows`)다. 보수적으로 간다: 숫자가 아닌 칸은 건너뛰고,
머리글을 못 찾으면 사실을 내지 않는다. 틀린 사실 하나가 "지어낸 수치" 를 근거 있는 것으로
둔갑시키기 때문이다(수치 lint 가 이 사실을 허용 텍스트로 쓴다).

- 머리글 행: 앞쪽 `HEADER_SCAN` 행 안에서, 빈 칸 아닌 셀 ≥ 2 이고 그중 값 셀(연도 아닌 숫자)이
  40% 미만인 첫 행. 바로 아랫줄도 값 없는 글자 행이면 두 줄 머리글(병합 셀)로 보고 윗줄 라벨을
  앞으로 채워 합친다.
- 연도: 머리글 셀이 "2023"·"2023년"·"'23"·"FY2023"·"2023년 실적" 이면 연도 열. 머리글이
  연도·년도·구분 인 열의 데이터 칸에 연도가 있으면 행 연도 열.
- 단위: 셀 접미(1,234만명 → 만명) > 열 머리글 괄호 "(억원)" > 행 라벨 괄호 "직원수(명)" >
  표 제목·각주 "(단위: 억원)" > 어댑터 기본값.
- 항목: 행 라벨(숫자 아닌 앞쪽 셀들, 연번 열 제외). 열이 연도가 아니면 "행 라벨 열 라벨".
- 머리글이 없는 열·연번(번호·No) 열·비어 있는 행 라벨은 사실을 내지 않는다.
- 본문 줄 표(`facts_from_lines`): "라벨 숫자 숫자 …" 꼴 줄이 위쪽 8줄 안의 연도 줄(또는 같은
  개수의 글자 라벨 줄)과 개수가 맞을 때만. PDF 텍스트는 셀이 줄 단위로 흩어지므로 이 조건을
  못 맞추면 아무것도 내지 않는다.
- 이미지 판독 structure(`facts_from_structure`): {"cols": […], "rows": [[…]|{…}], "units": "…"}
  → 같은 규칙, basis=image_vision. 수치가 OCR 로 확인되지 않은 판독은 호출자가 걸러 넘긴다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from rra.domain.models.table_fact import (
    MAX_ITEM_CHARS,
    MAX_LABEL_CHARS,
    MAX_UNIT_CHARS,
    FactBasis,
    ParsedTable,
    TableFact,
)

HEADER_SCAN = 15
MAX_ROWS = 5000
MAX_COLS = 64
MAX_FACTS_PER_TABLE = 2000
YEAR_MIN, YEAR_MAX = 1990, 2060
NUMERIC_HEADER_RATIO = 0.4  # 머리글 행에서 허용하는 숫자 셀 비율 (미만)
LINE_HEADER_LOOKBACK = 8

# 셀 접미 단위 — numbers.py 가 아는 단위를 우선 (환산 비교가 되도록), 그 밖은 그대로 보관한다.
UNIT_SUFFIXES = (
    "%p|%|퍼센트|억원|천만원|백만원|만원|천원|원|천명|만명|명|건|회|개소|개|대|톤|t|km/h|㎞|km|㎡|㎢|m|kg|"
    "시간|개월|년|일|월|호|량|편|석|MWh|GWh|kWh|MW|kW|TEU|%"
)
_SIGN = r"[△▲▽▼\-−(]"
_NUM_CELL = re.compile(
    rf"^\s*(?P<sign>{_SIGN})?\s*(?P<int>\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.(?P<frac>\d+))?\s*\)?"
    rf"\s*(?P<unit>{UNIT_SUFFIXES})?\s*$"
)
_NUM_TOKEN = rf"(?:{_SIGN})?\s?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?\)?(?:{UNIT_SUFFIXES})?"
_YEAR4 = re.compile(r"^(?:FY\s?)?(?P<year>(?:19|20)\d{2})\s*(?:년도|년)?(?:\s*(?P<rest>\S{1,6}))?$")
_YEAR2 = re.compile(r"^'(?P<yy>\d{2})\s*년?$|^(?P<yy2>\d{2})년$")
_UNIT_NOTE = re.compile(r"단\s*위\s*[:：]\s*(?P<unit>[^\s)）,，/]{1,12})")
_LABEL_TOKEN = re.compile(r"^[^\W\d_][\w·.\-]*(?:\([^\s()]{1,12}\))?$")
_UNIT_PAREN = re.compile(rf"\(\s*(?P<unit>{UNIT_SUFFIXES})\s*\)")
_SERIAL = re.compile(r"^(연\s*번|번\s*호|순\s*번|no\.?|seq\.?|#)$", re.IGNORECASE)
_YEAR_COLUMN = re.compile(r"^(연\s*도|년\s*도|구\s*분|연|년|year|fy)$", re.IGNORECASE)
_WS = re.compile(r"\s+")
_LINE_ROW = re.compile(
    rf"^(?P<label>[^\d\s][^\d]{{0,{MAX_LABEL_CHARS}}}?)\s+(?P<nums>{_NUM_TOKEN}(?:\s+{_NUM_TOKEN})+)\s*$"
)
_LINE_YEAR_ROW = re.compile(
    rf"^(?P<year>(?:19|20)\d{{2}})\s*년?\s+(?P<nums>{_NUM_TOKEN}(?:\s+{_NUM_TOKEN})*)\s*$"
)
_LINE_NUM_SPLIT = re.compile(rf"{_NUM_TOKEN}")

Cell = str | None
Parsed = tuple[Decimal, str, str | None]  # (값, 적힌 그대로, 접미 단위)


# ── 셀 해석 ────────────────────────────────────────────────
def parse_number(cell: Cell) -> Parsed | None:
    """숫자 셀 → (값, 원문, 접미 단위). 글자가 섞이면(단위 제외) None. 괄호·△ 는 음수."""
    if cell is None:
        return None
    text = cell.strip()
    if not text:
        return None
    m = _NUM_CELL.match(text)
    if m is None:
        return None
    raw = m.group("int").replace(",", "")
    if m.group("frac"):
        raw += "." + m.group("frac")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if m.group("sign"):
        value = -value
    shown = text
    unit = m.group("unit") or None
    if unit:
        shown = text[: text.rfind(unit)].strip()
    return value, _WS.sub("", shown) or raw, unit


def year_of(cell: Cell) -> tuple[int, str | None] | None:
    """머리글 셀의 연도 → (연도, 남은 라벨). "2023년 실적" → (2023, "실적")."""
    if cell is None:
        return None
    text = cell.strip()
    m = _YEAR4.match(text)
    if m:
        year = int(m.group("year"))
        rest = m.group("rest")
        if rest and parse_number(rest) is not None:
            return None  # "2023 1,234" 같은 줄은 머리글이 아니다
        return (year, rest) if YEAR_MIN <= year <= YEAR_MAX else None
    m = _YEAR2.match(text)
    if m:
        yy = int(m.group("yy") or m.group("yy2"))
        return (2000 + yy if yy < 90 else 1900 + yy), None
    return None


def detect_unit(texts: Iterable[str | None]) -> str | None:
    """ "(단위: 억원)"·"단위 : 명" 에서 단위. 없으면 None."""
    for text in texts:
        if not text:
            continue
        m = _UNIT_NOTE.search(text)
        if m:
            unit = m.group("unit").strip("()（）")
            return unit[:MAX_UNIT_CHARS] if unit else None
    return None


def _column_unit(label: str | None) -> tuple[str | None, str | None]:
    """열 머리글 "매출액(억원)" → ("매출액", "억원")."""
    if not label:
        return None, None
    m = _UNIT_PAREN.search(label)
    if m is None:
        return label, None
    cleaned = (label[: m.start()] + label[m.end() :]).strip()
    return cleaned or None, m.group("unit")


def _label(cell: Cell) -> str | None:
    if cell is None:
        return None
    text = cell.strip()
    if not text:
        return None
    compact = _WS.sub("", text)
    out = compact if len(compact) <= 6 else _WS.sub(" ", text)
    return out[:MAX_LABEL_CHARS]


def _is_numeric_cell(cell: Cell) -> bool:
    return parse_number(cell) is not None


# ── 머리글 ────────────────────────────────────────────────
def header_index(rows: Sequence[Sequence[Cell]]) -> int | None:
    """머리글 행 위치. 없으면 None (사실 없음)."""
    for i, row in enumerate(rows[:HEADER_SCAN]):
        cells = [c for c in row if c is not None and str(c).strip()]
        if len(cells) < 2:
            continue
        numeric = sum(1 for c in cells if _is_value_cell(c))
        if numeric / len(cells) >= NUMERIC_HEADER_RATIO:
            continue
        if not any(_has_numeric(r) for r in rows[i + 1 : i + 1 + HEADER_SCAN]):
            continue
        return i
    return None


def _is_value_cell(cell: Cell) -> bool:
    """숫자 셀이되 연도 표기("2023"·"2023년")는 아닌 것 — 머리글 판정용."""
    return _is_numeric_cell(cell) and year_of(cell) is None


def _has_numeric(row: Sequence[Cell]) -> bool:
    return any(_is_numeric_cell(c) for c in row)


def _has_value(row: Sequence[Cell]) -> bool:
    return any(_is_value_cell(c) for c in row)


def _merge_headers(upper: Sequence[Cell], lower: Sequence[Cell]) -> list[str | None]:
    width = max(len(upper), len(lower))
    out: list[str | None] = []
    carry: str | None = None
    for c in range(width):
        up = _label(upper[c]) if c < len(upper) else None
        if up is not None:
            carry = up
        low = _label(lower[c]) if c < len(lower) else None
        if low and carry and low != carry:
            out.append(f"{carry} {low}")
        else:
            out.append(low or carry)
    return out


def _header_labels(rows: Sequence[Sequence[Cell]], idx: int) -> tuple[list[str | None], int]:
    """머리글 라벨 목록과 데이터 시작 행. 병합 머리글은 두 줄까지."""
    head = [_label(c) for c in rows[idx]]
    start = idx + 1
    if start < len(rows):
        nxt = rows[start]
        cells = [c for c in nxt if c is not None and str(c).strip()]
        if cells and not _has_value(nxt) and len(cells) >= 2 and not _all_years(cells):
            head = _merge_headers(rows[idx], nxt)
            start += 1
    return head, start


def _all_years(cells: Sequence[Cell]) -> bool:
    return all(year_of(c) is not None for c in cells)


# ── 격자 → 사실 ───────────────────────────────────────────
def facts_of(table: ParsedTable) -> list[TableFact]:
    """ParsedTable 하나 → 사실. 격자(rows)면 table_to_facts, 본문 줄(lines)이면 facts_from_lines."""
    if table.rows:
        return table_to_facts(table)
    if table.lines:
        return facts_from_lines(
            table.lines, doc_id=table.doc_id, page=table.page, unit=table.unit, basis=table.basis
        )
    return []


def table_to_facts(table: ParsedTable) -> list[TableFact]:
    rows = [list(r[:MAX_COLS]) for r in table.rows[:MAX_ROWS]]
    idx = header_index(rows)
    if idx is None:
        return []
    labels, start = _header_labels(rows, idx)
    default_unit = (
        detect_unit([table.title, *table.notes, *(c for r in rows[: idx + 1] for c in r)])
        or table.unit
    )
    columns = _columns(labels)
    data_rows = [*rows[:idx], *rows[start:]]  # 머리글 위의 합계 행도 머리글 열에 맞춰 읽는다
    # "구분·연도" 열은 데이터 칸에 연도가 실제로 있을 때만 행 연도 열이다 (아니면 보통 라벨 열)
    year_col_idx = next(
        (
            c
            for c, col in enumerate(columns)
            if col["year_column"]
            and any(c < len(r) and year_of(r[c]) is not None for r in data_rows)
        ),
        None,
    )
    facts: list[TableFact] = []
    seen: set[tuple[str, int | None, str | None, Decimal]] = set()
    for row in data_rows:
        if not _has_numeric(row):
            continue
        row_label, row_year = _row_context(row, columns, year_col_idx)
        if row_label is None and row_year is None:
            continue
        row_label, row_unit = _column_unit(row_label)  # "직원수(명)" → 직원수 + 명
        if row_label is None and row_year is None:
            continue
        for c, cell in enumerate(row):
            if c >= len(columns):
                break
            col = columns[c]
            if col["skip"] or c == year_col_idx:
                continue
            parsed = parse_number(cell)
            if parsed is None:
                continue
            value, shown, suffix = parsed
            year = col["year"] if col["year"] is not None else row_year
            unit = suffix or col["unit"] or row_unit or default_unit
            item = _item(row_label, col, row_year)
            if not item:
                continue
            key = (item, year, unit, value)
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                TableFact(
                    item=item[:MAX_ITEM_CHARS],
                    value=value,
                    value_text=shown[:40],
                    doc_id=table.doc_id,
                    year=year,
                    unit=unit[:MAX_UNIT_CHARS] if unit else None,
                    page=table.page,
                    sheet=table.sheet,
                    row_label=row_label,
                    col_label=col["label"],
                    basis=table.basis,
                )
            )
            if len(facts) >= MAX_FACTS_PER_TABLE:
                return facts
    return facts


def _columns(labels: Sequence[str | None]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label in labels:
        info: dict[str, Any] = {
            "label": None,
            "unit": None,
            "year": None,
            "skip": True,
            "year_column": False,
            "serial": False,
        }
        if label:
            yr = year_of(label)
            if yr is not None:
                info.update(year=yr[0], label=yr[1], skip=False)
            elif _SERIAL.match(label):
                info["serial"] = True
            elif _YEAR_COLUMN.match(label):
                info.update(label=label, year_column=True, skip=True)
            else:
                name, unit = _column_unit(label)
                info.update(label=name, unit=unit, skip=name is None)
        out.append(info)
    return out


def _row_context(
    row: Sequence[Cell], columns: Sequence[dict[str, Any]], year_col_idx: int | None
) -> tuple[str | None, int | None]:
    """행 라벨(숫자 아닌 앞쪽 셀들)과 행 연도."""
    labels: list[str] = []
    row_year: int | None = None
    for c, cell in enumerate(row):
        if c >= len(columns):
            break
        if year_col_idx is not None and c == year_col_idx:
            yr = year_of(cell)
            if yr is not None:
                row_year = yr[0]
                continue
        if parse_number(cell) is not None:
            if labels or row_year is not None:
                break  # 첫 숫자 셀부터는 값
            continue  # 연번 등 앞쪽 숫자는 라벨이 아니다
        lab = _label(cell)
        if lab is None:
            continue
        if columns[c]["year"] is not None:
            continue  # 연도 열의 글자("-"·"미정")는 라벨이 아니다
        if columns[c]["skip"] and not columns[c]["label"] and not columns[c]["serial"]:
            continue  # 머리글 없는 열의 글자는 라벨로 쓰지 않는다 (연번 열의 "합계" 는 라벨)
        if year_col_idx is None and year_of(cell) is not None and not labels:
            row_year = year_of(cell)[0]  # type: ignore[index]
            continue
        labels.append(lab)
    return (" ".join(labels) if labels else None), row_year


def _item(row_label: str | None, col: dict[str, Any], row_year: int | None) -> str:
    col_label = col["label"]
    if col["year"] is not None:
        return row_label or col_label or ""
    if row_year is not None and not row_label:
        return col_label or ""
    if row_label and col_label:
        return f"{row_label} {col_label}"
    return row_label or col_label or ""


# ── 본문 줄 표 (PDF 텍스트) ───────────────────────────────
def facts_from_lines(
    lines: Sequence[str],
    *,
    doc_id: str,
    page: int | None = None,
    unit: str | None = None,
    basis: FactBasis = "text",
) -> list[TableFact]:
    """정렬된 숫자 줄만 사실로. 머리글(연도 줄 또는 라벨 줄)이 위쪽에 있어야 한다."""
    default_unit = detect_unit(lines) or unit
    facts: list[TableFact] = []
    seen: set[tuple[str, int | None, str | None, Decimal]] = set()
    for i, line in enumerate(lines):
        text = line.strip()
        row_year: int | None = None
        m = _LINE_ROW.match(text)
        if m:
            label = _label(m.group("label"))
        else:
            m = _LINE_YEAR_ROW.match(text)
            if m is None:
                continue
            row_year, label = int(m.group("year")), None
            if not YEAR_MIN <= row_year <= YEAR_MAX:
                continue
        nums = [n.strip() for n in _LINE_NUM_SPLIT.findall(m.group("nums"))]
        header = _line_header(lines, i, len(nums))
        if header is None:
            continue
        for n, col in zip(nums, header, strict=True):
            parsed = parse_number(n)
            if parsed is None:
                continue
            value, shown, suffix = parsed
            year = col[0] if col[0] is not None else row_year
            col_label = col[1]
            item = (
                label
                if (col[0] is not None or not col_label)
                else (f"{label} {col_label}" if label else col_label)
            )
            if not item:
                continue
            unit_ = suffix or default_unit
            key = (item, year, unit_, value)
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                TableFact(
                    item=item[:MAX_ITEM_CHARS],
                    value=value,
                    value_text=shown[:40],
                    doc_id=doc_id,
                    year=year,
                    unit=unit_,
                    page=page,
                    row_label=label,
                    col_label=col_label,
                    basis=basis,
                )
            )
            if len(facts) >= MAX_FACTS_PER_TABLE:
                return facts
    return facts


def _line_header(
    lines: Sequence[str], at: int, count: int
) -> list[tuple[int | None, str | None]] | None:
    """위쪽 8줄 안, 같은 블록(데이터 줄만 사이에 둔)의 첫 비데이터 줄이 숫자 개수와 맞는 연도 줄
    (또는 글자 라벨 줄)일 때만. 그 줄이 다른 모양이면 머리글 없음."""
    for j in range(at - 1, max(-1, at - 1 - LINE_HEADER_LOOKBACK), -1):
        text = lines[j].strip()
        if not text:
            continue
        tokens = text.split()
        if len(tokens) == count + 1 and _YEAR_COLUMN.match(tokens[0]):
            tokens = tokens[1:]
        years = [year_of(t) for t in tokens]
        if len(tokens) == count and all(y is not None for y in years):
            return [(y[0], y[1]) for y in years]  # type: ignore[index]
        if _LINE_ROW.match(text) or _LINE_YEAR_ROW.match(text):
            continue  # 같은 표의 다른 데이터 줄 — 더 위를 본다
        if len(tokens) != count:
            return None
        if all(_LABEL_TOKEN.match(t) and year_of(t) is None for t in tokens):
            return [(None, _label(t)) for t in tokens]
        return None
    return None


# ── 이미지 판독 structure ─────────────────────────────────
def facts_from_structure(
    structure: dict[str, Any], *, doc_id: str, basis: FactBasis = "image_vision"
) -> list[TableFact]:
    """VisionReading.structure(표) → 사실. cols/rows 가 없거나 모양이 다르면 빈 목록."""
    cols = structure.get("cols")
    rows = structure.get("rows")
    if not isinstance(rows, list) or not rows:
        return []
    grid: list[list[str | None]] = []
    if isinstance(cols, list) and cols:
        grid.append([_cell(c) for c in cols])
    for row in rows[:MAX_ROWS]:
        if isinstance(row, list):
            grid.append([_cell(c) for c in row])
        elif isinstance(row, dict):
            if not grid:
                grid.append([_cell(k) for k in row])
            grid.append([_cell(v) for v in row.values()])
    units = structure.get("units")
    unit = _cell(units) if isinstance(units, str | int | float) else None
    if unit:
        unit = detect_unit([f"단위: {unit}"]) or unit[:MAX_UNIT_CHARS]
    table = ParsedTable(doc_id=doc_id, rows=grid, unit=unit or None, basis=basis)
    return table_to_facts(table)


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[: MAX_LABEL_CHARS * 4] or None
