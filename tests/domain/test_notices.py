"""공고 규칙 — 중복 키(제목·기관·공고일), 접수기간 해석, 마감."""

from datetime import date

from rra.domain.rules.notices import days_left, is_open, notice_key, parse_period


def test_notice_key_ignores_notice_number_and_spacing_but_not_agency_or_date():
    a = notice_key(
        "(공고-국-제29호) 2026년 국토교통연구기획 사업 제2차 시행 공고",
        "국토교통과학기술진흥원",
        "2026-07-16",
    )
    b = notice_key(
        "2026년  국토교통연구기획 사업 제2차 시행 공고", "국토교통과학기술진흥원", date(2026, 7, 16)
    )
    assert a == b and len(a) == 16
    assert a != notice_key(
        "2026년 국토교통연구기획 사업 제2차 시행 공고", "한국연구재단", "2026-07-16"
    )
    assert a != notice_key(
        "2026년 국토교통연구기획 사업 제2차 시행 공고", "국토교통과학기술진흥원", "2026-08-20"
    )


def test_parse_period_and_deadline_rules():
    assert parse_period("2026-07-16 ~ 2026-08-18") == (date(2026, 7, 16), date(2026, 8, 18))
    assert parse_period("2026.10.16 ~ 2026.11.17") == (date(2026, 10, 16), date(2026, 11, 17))
    assert parse_period("2026-07-16") == (date(2026, 7, 16), None)
    assert parse_period(None) == (None, None)
    assert is_open(date(2026, 8, 18), date(2026, 8, 18)) and not is_open(
        date(2026, 8, 18), date(2026, 8, 19)
    )
    assert is_open(None, date(2026, 1, 1)) and days_left(date(2026, 8, 18), date(2026, 8, 1)) == 17
    assert days_left(None, date(2026, 1, 1)) is None
