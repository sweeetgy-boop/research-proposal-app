"""Argon 연결 상태 규칙 (ADR 0055) — 실패 종류 → 상태, since 유지, 공개 표시는 열거값·시각만."""

from __future__ import annotations

import pytest

from rra.domain.rules import llm_status as ls


@pytest.mark.parametrize(
    ("code", "state"),
    [
        ("auth", "key_invalid"),
        ("quota", "quota"),
        ("rate_limit", "quota"),
        ("timeout", "unavailable"),
        ("connection", "unavailable"),
        ("server", "unavailable"),
        ("http", "unavailable"),
        ("error", "unavailable"),
        ("something_new", "unavailable"),
        (None, "unavailable"),
        ("invalid", None),
        ("not_sent", None),
    ],
)
def test_status_for_code(code, state):
    assert ls.status_for_code(code) == state


def test_advance_keeps_since_only_while_the_status_holds():
    first = ls.advance(None, "key_invalid", "2026-11-03T16:14:49+09:00")
    assert first == {
        "status": "key_invalid",
        "since": "2026-11-03T16:14:49+09:00",
        "checked_at": "2026-11-03T16:14:49+09:00",
    }
    again = ls.advance(first, "key_invalid", "2026-11-03T17:00:00+09:00")
    assert again["since"] == "2026-11-03T16:14:49+09:00"
    assert again["checked_at"] == "2026-11-03T17:00:00+09:00"
    fixed = ls.advance(again, "ok", "2026-11-03T17:28:00+09:00")
    assert fixed["since"] == "2026-11-03T17:28:00+09:00"
    with pytest.raises(ValueError):
        ls.advance(None, "unknown", "2026-11-03T17:28:00+09:00")


def test_public_view_exposes_only_enum_and_timestamp():
    assert ls.public_view(None) == {"gemini": "unknown", "since": None}
    assert ls.public_view({"status": "weird", "since": "x"}) == {"gemini": "unknown", "since": None}
    view = ls.public_view(
        {
            "status": "quota",
            "since": "2026-11-03T16:14:49+09:00",
            "checked_at": "2026-11-03T16:20:00+09:00",
            "extra": "https://example.invalid/?key=abc",
        }
    )
    assert view == {"gemini": "quota", "since": "2026-11-03T16:14:49+09:00"}
    assert ls.public_view({"status": "ok", "since": "not a time"}) == {
        "gemini": "ok",
        "since": None,
    }


def test_failure_labels_cover_the_classified_codes_only():
    assert ls.failure_label("auth") == "인증 실패(API 키 무효)"
    assert ls.failure_label("quota") == "사용 한도 초과(할당량 소진)"
    assert ls.failure_label("http") is None and ls.failure_label(None) is None
