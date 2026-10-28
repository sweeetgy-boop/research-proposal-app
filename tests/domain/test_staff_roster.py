"""사번 일괄 등록 규칙 (A2): 정규화(공백·하이픈·숫자 셀·0 채움), 머리글 찾기, 집계에 값 없음."""

import pytest

from rra.domain.rules.staff_roster import (
    RosterCounts,
    find_header,
    header_matches,
    normalize_staff_no,
    plan_import,
)


@pytest.mark.parametrize(
    ("raw", "pad", "expected"),
    [
        (" 0012345 ", 0, "0012345"),
        ("12-345", 0, "12345"),
        ("12‑345", 0, "12345"),  # 유니코드 하이픈
        ("12 345", 0, "12345"),
        (12345, 0, "12345"),  # 엑셀 숫자 셀
        (12345.0, 0, "12345"),
        ("12345.0", 0, "12345"),
        (12345, 7, "0012345"),  # 앞자리 0 복원
        ("12345", 3, "12345"),  # 이미 길면 그대로
        ("K-2026-0001", 7, "K20260001"),  # 영문 섞이면 pad 없음
        (None, 0, ""),
        ("", 0, ""),
        (True, 0, ""),
    ],
)
def test_normalize(raw, pad, expected):
    assert normalize_staff_no(raw, pad) == expected


def test_header_matching_ignores_spaces_and_case():
    assert header_matches(" 사 번 ", "사번")
    assert header_matches("Staff NO", "staffno")
    assert not header_matches("이름", "사번")
    rows = [["부서", "명단"], [None, None], ["이름", "사번", "부서"], ["홍", "1", "a"]]
    assert find_header(rows) == (3, 1)
    assert find_header(rows, "부서") == (1, 0)
    assert find_header([["이름"]]) is None


def test_plan_import_counts_without_values():
    cells = [
        (2, "0012345"),
        (3, 12345),  # 숫자 셀 → "12345" (0 빠짐)
        (4, " 0012345 "),  # 중복
        (5, ""),
        (6, None),
        (7, "a"),  # 형식 오류(1자)
        (8, "12-346"),
        (9, "홍길동"),  # 형식 오류
    ]
    plan = plan_import(cells)
    assert set(plan.values) == {"0012345", "12345", "12346"}
    counts = plan.counts
    assert counts == RosterCounts(
        rows_read=8,
        blank=2,
        invalid=2,
        duplicate=1,
        unique=3,
        invalid_rows=(7, 9),
        length_histogram={7: 1, 5: 2},
    )
    text = "\n".join(counts.as_lines()) + repr(plan) + repr(counts)
    for value in ("0012345", "12345", "12346", "홍길동"):
        assert value not in text
    assert "7자리 1건" in text and "5자리 2건" in text and "형식 오류 행 번호: 7, 9" in text


def test_plan_import_pad_merges_zero_lost_numbers():
    plan = plan_import([(2, "0012345"), (3, 12345)], pad=7)
    assert plan.values == ("0012345",)
    assert plan.counts.duplicate == 1 and plan.counts.length_histogram == {7: 1}
    with pytest.raises(ValueError):
        plan_import([], pad=40)
