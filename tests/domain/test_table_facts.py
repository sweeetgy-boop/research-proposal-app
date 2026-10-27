"""표 → 사실 규칙 (P2-8). 합성 격자·줄 표·판독 structure 만 쓴다 (실물 문서 없음)."""

from decimal import Decimal

import pytest

from rra.domain.models import ParsedTable, TableFact
from rra.domain.rules.table_facts import (
    detect_unit,
    facts_from_lines,
    facts_from_structure,
    header_index,
    parse_number,
    table_to_facts,
    year_of,
)

STATION_ROWS = [  # 실물 "역별 승강설비 현황" 꼴: 제목 → 합계 → 머리글 → 데이터
    ["역별 승강설비 현황"],
    ["합  계", None, "649", "1512", "2948", "82"],
    ["연 번", "노선명", "역 명", "엘리베이터", "에스컬레이터", "휠체어리프트", "비 고"],
    ["1", "경부선", "서울역사", "18", "23", "1"],
    ["2", "경부선", "남영역사", "0", "0", "1", "리프트만"],
]
YEAR_COLS = [
    ["(단위: 억원)"],
    ["구분", "2022", "2023년", "2024년 계획"],
    ["매출액", "5,100", "5,300", "5,500"],
    ["영업이익", "△120", "80", "150"],
    ["직원수(명)", "3,000", "3,100", "3,200"],
    ["비고", "-", "n/a", ""],
]


def by_item(facts: list[TableFact]) -> dict[tuple[str, int | None], TableFact]:
    return {(f.item, f.year): f for f in facts}


# ── 셀 해석 ───────────────────────────────────────────────
@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1,512", (Decimal("1512"), "1,512", None)),
        ("12.5%", (Decimal("12.5"), "12.5", "%")),
        ("1,234만명", (Decimal("1234"), "1,234", "만명")),
        ("△3.2", (Decimal("-3.2"), "△3.2", None)),
        ("(120)", (Decimal("-120"), "(120)", None)),
        ("1.서울", None),
        ("2024-05-01T00:00:00", None),
        ("-", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_number(cell, expected):
    assert parse_number(cell) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("2023", (2023, None)),
        ("2023년", (2023, None)),
        ("2023년도", (2023, None)),
        ("'23", (2023, None)),
        ("23년", (2023, None)),
        ("FY2024", (2024, None)),
        ("2024년 계획", (2024, "계획")),
        ("1850", None),  # 범위 밖
        ("2023 1,234", None),  # 데이터 줄
        ("매출액", None),
    ],
)
def test_year_of(cell, expected):
    assert year_of(cell) == expected


def test_detect_unit_from_title_or_note():
    assert detect_unit(["수송 실적", "(단위: 억원)"]) == "억원"
    assert detect_unit(["단위 : 명"]) == "명"
    assert detect_unit(["아무 단위 표기 없음"]) is None


# ── 격자 → 사실 ───────────────────────────────────────────
def test_header_is_found_below_title_and_total_rows():
    assert header_index(STATION_ROWS) == 2
    assert header_index([["제목"], ["a"]]) is None  # 숫자 행이 없으면 머리글 아님


def test_station_table_items_combine_row_and_column_labels():
    facts = by_item(table_to_facts(ParsedTable(doc_id="korail_web:x", rows=STATION_ROWS)))
    seoul = facts[("경부선 서울역사 엘리베이터", None)]
    assert seoul.value == 18 and seoul.row_label == "경부선 서울역사"
    assert seoul.col_label == "엘리베이터" and seoul.unit is None
    assert facts[("경부선 남영역사 휠체어리프트", None)].value == 1
    # 머리글 위의 합계 행도 머리글 열에 맞춰 읽는다. 연번 열의 숫자는 사실이 아니다
    assert facts[("합계 엘리베이터", None)].value == 1512
    assert not any(item.startswith("연번") or "비고" in item for item, _ in facts)
    assert all(f.basis == "text" and f.trust == "untrusted" for f in facts.values())


def test_year_columns_units_and_negative_values():
    facts = by_item(table_to_facts(ParsedTable(doc_id="d", rows=YEAR_COLS, page=3)))
    assert facts[("매출액", 2022)].value_text == "5,100" and facts[("매출액", 2022)].unit == "억원"
    assert facts[("매출액", 2024)].col_label == "계획" and facts[("매출액", 2024)].page == 3
    assert facts[("영업이익", 2022)].value == -120
    # 행 라벨의 괄호 단위가 표 단위보다 우선
    assert facts[("직원수", 2023)].unit == "명" and facts[("직원수", 2023)].value == 3100
    assert ("비고", 2022) not in facts  # 숫자 아닌 칸은 건너뛴다
    assert facts[("매출액", 2022)].as_text() == "2022년 5,100억원"


def test_row_year_column_and_column_unit():
    rows = [
        ["연도", "수송인원(만명)", "증감률(%)"],
        ["2023", "1,234", "3.5"],
        ["2024", "1,300", "5.3%"],
    ]
    facts = by_item(table_to_facts(ParsedTable(doc_id="d", rows=rows, sheet="실적")))
    assert facts[("수송인원", 2023)].unit == "만명" and facts[("수송인원", 2023)].sheet == "실적"
    assert facts[("증감률", 2024)].unit == "%" and facts[("증감률", 2024)].value == Decimal("5.3")


def test_two_row_merged_header_is_combined_conservatively():
    rows = [
        ["구분", "2023", None, "2024", None],
        [None, "계획", "실적", "계획", "실적"],
        ["궤도", "10", "12", "11", "13"],
    ]
    facts = table_to_facts(ParsedTable(doc_id="d", rows=rows))
    assert [(f.year, f.col_label, int(f.value)) for f in facts] == [
        (2023, "계획", 10),
        (2023, "실적", 12),
        (2024, "계획", 11),
        (2024, "실적", 13),
    ]


def test_tables_without_header_or_numbers_yield_nothing():
    assert table_to_facts(ParsedTable(doc_id="d", rows=[["문장만"], ["또 문장"]])) == []
    assert table_to_facts(ParsedTable(doc_id="d", rows=[["1", "2", "3"], ["4", "5", "6"]])) == []
    assert table_to_facts(ParsedTable(doc_id="d", rows=[])) == []


def test_duplicate_cells_are_emitted_once_and_adapter_unit_is_fallback():
    rows = [["구분", "값"], ["a", "1"], ["a", "1"]]
    facts = table_to_facts(ParsedTable(doc_id="d", rows=rows, unit="건"))
    assert len(facts) == 1 and facts[0].unit == "건" and facts[0].item == "a 값"


# ── 본문 줄 표 ────────────────────────────────────────────
def test_lines_with_year_header_become_facts_but_prose_does_not():
    lines = [
        "수송 실적",
        "(단위: 만명)",
        "구분 2022 2023 2024",
        "수송인원 1,234 1,300 1,420",
        "증가율 3.5% 5.3% 9.2%",
        "본문 문장은 2023년 1,000건 중 10% 를 설명한다.",
        "정렬 없는 숫자 12 34",  # 머리글과 개수가 안 맞는다 → 없음
    ]
    facts = by_item(facts_from_lines(lines, doc_id="korail_web:p", page=4))
    assert facts[("수송인원", 2023)].value == 1300 and facts[("수송인원", 2023)].unit == "만명"
    assert facts[("증가율", 2024)].unit == "%" and facts[("증가율", 2024)].page == 4
    assert len(facts) == 6


def test_lines_with_label_header_and_year_rows():
    lines = ["연도 매출액 영업이익", "2023 5,100 80", "2024 5,300 150"]
    facts = by_item(facts_from_lines(lines, doc_id="d", unit="억원"))
    assert facts[("영업이익", 2024)].value == 150 and facts[("영업이익", 2024)].unit == "억원"


def test_lines_without_a_header_yield_nothing():
    assert facts_from_lines(["서울 1,234 2,345", "부산 3,456 4,567"], doc_id="d") == []


# ── 이미지 판독 structure ─────────────────────────────────
def test_vision_structure_rows_lists_and_dicts():
    structure = {
        "cols": ["구분", "2023", "2024"],
        "rows": [["수송인원", "1,234만명", "1,300만명"], ["증가율", "3.5%", "5.3%"]],
        "units": "",
    }
    facts = by_item(facts_from_structure(structure, doc_id="korail_web:img:abc"))
    assert (
        facts[("수송인원", 2024)].value_text == "1,300" and facts[("수송인원", 2024)].unit == "만명"
    )
    assert all(f.basis == "image_vision" for f in facts.values())
    dict_rows = {"rows": [{"항목": "영업이익", "2023": "80", "2024": "150"}], "units": "억원"}
    facts = by_item(facts_from_structure(dict_rows, doc_id="d"))
    assert facts[("영업이익", 2023)].unit == "억원" and facts[("영업이익", 2024)].value == 150
    assert facts_from_structure({"비전": "국민과 함께"}, doc_id="d") == []
    assert facts_from_structure({"cols": [], "rows": "x"}, doc_id="d") == []
