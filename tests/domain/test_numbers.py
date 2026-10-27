"""지어낸 수치 검사 — 입력·인용 근거에 없는 수치만 경고. 단위 환산은 통과."""

import pytest

from rra.domain.rules.numbers import numbers, unsupported_numbers

INPUT = (
    "기존 검측차 데이터만 사용, 추가 센서 설치 없음, 연구기간 1년 이내. 연 2회 검측. 예산 90000천원"
)


@pytest.mark.parametrize(
    "text",
    [
        "12개월 안에 보수 우선순위 산정 방법을 개발함",  # 1년 → 12개월 환산
        "1년 이내에 완료함",
        "연 2회 검측 결과를 활용함",
        "2회 검측 이력을 사용함",
        "총 9천만원 규모임",  # 90000천원 = 9천만원 (천만원 단위도 원으로 환산)
        "소요예산은 9,000만원임",
        "수치가 없는 문장임",
    ],
)
def test_supported_numbers_pass(text):
    assert unsupported_numbers(text, [INPUT]) == []


def test_only_the_unsupported_number_is_reported():
    # 1년은 입력에 있고 365일은 없다 (년→일 환산은 하지 않는다)
    assert unsupported_numbers("연구기간 365일이 아니라 1년으로 잡음", [INPUT]) == ["365일"]


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("유지보수 비용을 약 10% 절감할 것으로 기대됨", ["10%"]),
        ("2년 동안 보수 우선순위를 산정함", ["2년"]),  # 입력은 1년 이내
        ("1차년도에 분석하고 2차년도에 검증함", ["1차년도", "2차년도"]),
        ("보수 횟수를 30건 줄임", ["30건"]),
        ("약 5억원의 효과가 예상됨", ["5억원"]),
        ("2030년까지 적용함", ["2030년"]),
    ],
)
def test_invented_numbers_are_flagged(text, flagged):
    assert unsupported_numbers(text, [INPUT]) == flagged


def test_cited_chunk_supports_its_numbers():
    chunk = "The RMSE decreased by 15% over 24 months of monitoring."
    assert unsupported_numbers("24개월 관측에서 15% 개선됨", [INPUT, chunk]) == []
    assert unsupported_numbers("24개월 관측에서 15% 개선됨", [INPUT]) == ["24개월", "15%"]


def test_unit_mismatch_is_not_supported():
    # 2회(개수)가 입력에 있어도 2년(기간)·2%(비율)은 근거가 아니다
    assert unsupported_numbers("2년간 2% 개선", [INPUT]) == ["2년간", "2%"]


def test_bare_number_matches_any_allowed_value():
    assert unsupported_numbers("임계치 0.80 이상", ["own 0.80"]) == []
    assert unsupported_numbers("임계치 0.85 이상", ["own 0.80"]) == ["0.85"]
    assert unsupported_numbers("2 단계로 나눔", [INPUT]) == []  # 연 2회 의 2


def test_identifiers_are_not_numbers():
    assert numbers("openalex:W2908009528 과 alio:sum-8f69f1e778ff7e36#0 을 인용") == []
    assert numbers("2-가-(1) 항목") == [("2", ("bare", 2))] or numbers("2-가-(1) 항목")[0][0] == "2"


def test_numbers_extracts_value_and_unit():
    got = dict(numbers("1년 12개월 90,000천원 10% 2024년 3차"))
    assert got["1년"] == ("month", 12)
    assert got["12개월"] == ("month", 12)
    assert got["90,000천원"] == ("won", 90_000_000)
    assert got["10%"] == ("pct", 10)
    assert got["2024년"] == ("year", 2024)
    assert got["3차"] == ("ord", 3)


def test_no_allowed_text_flags_every_number():
    assert unsupported_numbers("3단계 10% 2년", []) == ["3", "10%", "2년"]


# ── 표 사실(P2-8) ─────────────────────────────────────────
def test_table_facts_count_as_supported_numbers_only_when_given():
    from decimal import Decimal

    from rra.domain.models import TableFact

    fact = TableFact(
        item="합계 엘리베이터",
        value=Decimal("1512"),
        value_text="1,512",
        doc_id="korail_web:a",
        year=2026,
        unit="대",
    )
    text = "2026년 기준 엘리베이터 1,512대가 설치되어 있음"
    assert unsupported_numbers(text, [INPUT]) == ["2026년", "1,512대"]  # 종전 동작 그대로
    assert unsupported_numbers(text, [INPUT], facts=[fact]) == []
    # 다른 값·다른 단위는 여전히 경고
    assert unsupported_numbers("엘리베이터 1,600대", [INPUT], facts=[fact]) == ["1,600대"]
    assert unsupported_numbers("엘리베이터 1,512건", [INPUT], facts=[fact]) == ["1,512건"]
