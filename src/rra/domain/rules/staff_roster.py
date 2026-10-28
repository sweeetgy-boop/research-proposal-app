"""사번 일괄 등록 규칙 — 순수 함수 (A2, 2026-10-28).

- `normalize_staff_no`: 앞뒤 공백·하이픈 제거, 문자열로 처리. 엑셀이 숫자로 저장한 값(`12345.0`)은
  정수 문자열로, `pad` 를 주면 숫자만인 값을 그 자릿수까지 앞에 0 을 채운다(엑셀에서 앞자리 0 이
  빠진 경우). 로그인 입력도 같은 함수로 정규화한다(pad 는 등록 때만).
- `find_header`: 머리글 행·열 위치. 열 제목은 기본 "사번"(공백 무시 비교). 다른 열은 위치만 알 뿐
  값은 이 모듈에 들어오지 않는다.
- `plan_import`: (행 번호, 셀 값) 목록 → 등록할 값 집합 + 집계. 집계(`RosterCounts`)에는 사번 값이
  없다. 오류·빈칸은 행 번호만 남긴다. 값 집합은 저장소로 넘긴 뒤 버린다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rra.domain.rules.auth_policy import valid_staff_no

STAFF_COLUMN = "사번"
MAX_HEADER_SCAN = 8  # 머리글을 찾기 위해 보는 앞쪽 행 수
MAX_ROWS = 50_000
MAX_PAD = 32

_FLOAT_INTEGER = re.compile(r"^-?\d+\.0+$")
_DIGITS = re.compile(r"^\d+$")
_HYPHENS = "-‐‑‒–—−"  # ASCII 하이픈 + 유니코드 대시 (엑셀에서 섞여 들어온다)


def normalize_staff_no(value: object, pad: int = 0) -> str:
    """앞뒤 공백·하이픈 제거, 문자열로. 숫자(`12345.0`)는 정수 문자열. pad 는 숫자만인 값에
    앞 0 채움."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = str(int(value)) if value.is_integer() else str(value)
    else:
        text = str(value)
    text = text.strip()
    if _FLOAT_INTEGER.match(text):
        text = text.split(".", 1)[0]
    for ch in _HYPHENS:
        text = text.replace(ch, "")
    text = "".join(text.split())  # 가운데 공백도 제거 (복사·붙여넣기 잔재)
    if pad and _DIGITS.match(text) and len(text) < pad:
        text = text.zfill(pad)
    return text


def header_matches(cell: object, column: str) -> bool:
    """열 제목 비교 — 앞뒤·가운데 공백 무시, 대소문자 무시."""
    if cell is None:
        return False
    return "".join(str(cell).split()).casefold() == "".join(column.split()).casefold()


def find_header(
    rows: Sequence[Sequence[object]], column: str = STAFF_COLUMN
) -> tuple[int, int] | None:
    """앞쪽 MAX_HEADER_SCAN 행에서 열 제목을 찾아 (행 번호 1-based, 열 번호 0-based). 없으면
    None."""
    for row_index, row in enumerate(rows[:MAX_HEADER_SCAN], start=1):
        for col_index, cell in enumerate(row):
            if header_matches(cell, column):
                return row_index, col_index
    return None


@dataclass(frozen=True)
class RosterCounts:
    """집계 — 사번 값 없음. 오류·빈칸은 행 번호만."""

    rows_read: int = 0  # 머리글 아래 행 수 (빈 행 포함)
    blank: int = 0
    invalid: int = 0
    duplicate: int = 0  # 파일 안 중복(하나로 합친 뒤 남은 수)
    unique: int = 0  # 등록 대상
    invalid_rows: tuple[int, ...] = ()  # 형식 오류 행 번호 (파일 기준, 머리글 포함 1-based)
    length_histogram: dict[int, int] = field(default_factory=dict)  # 사번 길이 → 개수

    def as_lines(self) -> list[str]:
        lines = [
            f"읽은 행: {self.rows_read}",
            f"빈칸: {self.blank}, 형식 오류: {self.invalid}, 파일 안 중복(합침): {self.duplicate}",
            f"등록 대상(고유): {self.unique}",
        ]
        if self.invalid_rows:
            shown = ", ".join(str(r) for r in self.invalid_rows[:20])
            more = f" 외 {len(self.invalid_rows) - 20}건" if len(self.invalid_rows) > 20 else ""
            lines.append(f"형식 오류 행 번호: {shown}{more}")
        if self.length_histogram:
            dist = ", ".join(f"{n}자리 {c}건" for n, c in sorted(self.length_histogram.items()))
            lines.append(f"길이별 분포: {dist}")
        return lines


@dataclass(frozen=True)
class RosterPlan:
    """등록할 정규화 사번 집합 + 집계. `values` 는 저장소로 넘긴 뒤 버린다 — repr 에 싣지 않는다."""

    values: tuple[str, ...] = field(repr=False)
    counts: RosterCounts

    def __repr__(self) -> str:
        return f"RosterPlan(counts={self.counts!r})"


def plan_import(cells: Iterable[tuple[int, object]], *, pad: int = 0) -> RosterPlan:
    """(파일 행 번호, 셀 값) → 정규화·검증·중복 제거. 값은 `RosterPlan.values` 에만."""
    if pad < 0 or pad > MAX_PAD:
        raise ValueError(f"--pad 는 0~{MAX_PAD} 사이여야 합니다.")
    rows_read = blank = invalid = 0
    invalid_rows: list[int] = []
    seen: dict[str, None] = {}
    duplicates = 0
    histogram: dict[int, int] = {}
    for row_no, raw in cells:
        rows_read += 1
        if rows_read > MAX_ROWS:
            raise ValueError(f"행이 {MAX_ROWS}개를 넘습니다.")
        value = normalize_staff_no(raw, pad)
        if not value:
            blank += 1
            continue
        if not valid_staff_no(value):
            invalid += 1
            invalid_rows.append(int(row_no))
            continue
        if value in seen:
            duplicates += 1
            continue
        seen[value] = None
        histogram[len(value)] = histogram.get(len(value), 0) + 1
    counts = RosterCounts(
        rows_read=rows_read,
        blank=blank,
        invalid=invalid,
        duplicate=duplicates,
        unique=len(seen),
        invalid_rows=tuple(invalid_rows),
        length_histogram=histogram,
    )
    return RosterPlan(values=tuple(seen), counts=counts)
