"""운영 상태 규칙(domain/rules/ops_status) — 순수 함수. 계약 healthz-status.md §1·§3."""

from datetime import UTC, datetime, timedelta

import pytest

from rra.domain.rules import ops_status as r

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("backend", "funnel", "expected"),
    [
        ("Running", True, "ok"),
        ("Running", False, "down"),
        ("Stopped", True, "down"),
        ("NeedsLogin", False, "down"),
        (None, True, "unknown"),
        ("Running", None, "unknown"),
        (None, None, "unknown"),
    ],
)
def test_tunnel_state_needs_running_and_funnel_on(backend, funnel, expected):
    assert r.tunnel_state(backend, funnel) == expected


@pytest.mark.parametrize(
    ("responded", "expected"), [(True, "ok"), (False, "unavailable"), (None, "unknown")]
)
def test_local_state(responded, expected):
    assert r.local_state(responded) == expected


def test_advance_keeps_since_while_state_continues_and_rejects_unknown():
    first = r.advance(None, "ok", "2026-11-09T14:00:00+09:00")
    assert first == {
        "state": "ok",
        "since": "2026-11-09T14:00:00+09:00",
        "checked_at": "2026-11-09T14:00:00+09:00",
    }
    same = r.advance(first, "ok", "2026-11-09T14:05:00+09:00")
    assert same["since"] == first["since"] and same["checked_at"] == "2026-11-09T14:05:00+09:00"
    changed = r.advance(same, "down", "2026-11-09T14:10:00+09:00")
    assert changed["since"] == "2026-11-09T14:10:00+09:00"
    with pytest.raises(ValueError):
        r.advance(None, "unknown", "2026-11-09T14:00:00+09:00")


def _rec(state, minutes_ago):
    stamp = (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    return {"state": state, "since": stamp, "checked_at": stamp}


def test_stale_records_become_unknown_after_fifteen_minutes():
    assert r.view_state("tunnel", _rec("ok", 1), NOW) == "ok"
    assert r.view_state("tunnel", _rec("down", 14), NOW) == "down"
    assert r.view_state("tunnel", _rec("ok", 16), NOW) == "unknown"
    assert r.view_state("llm_local", _rec("unavailable", 5), NOW) == "unavailable"
    assert r.view_state("llm_local", _rec("unavailable", 30), NOW) == "unknown"
    assert r.is_stale({"state": "ok", "checked_at": "not-a-time"}, NOW)
    assert r.is_stale({"state": "ok"}, NOW) and r.is_stale(None, NOW)
    # 미래 시각(시계 어긋남)도 모르는 것으로
    assert r.is_stale(_rec("ok", -10), NOW)


def test_public_view_emits_only_enums_and_treats_foreign_values_as_unknown():
    data = {
        "tunnel": _rec("down", 2),
        "llm_local": {"state": "weird", "checked_at": _rec("ok", 1)["checked_at"]},
        "extra": {"host": "should-not-leak"},
    }
    view = r.public_view(data, NOW)
    assert view == {"tunnel": "down", "llm_local": "unknown"}
    assert r.public_view(None, NOW) == {"tunnel": "unknown", "llm_local": "unknown"}
    assert r.public_view({"tunnel": "not-a-dict"}, NOW)["tunnel"] == "unknown"
    assert r.summary_line(view) == "tunnel=down llm_local=unknown"


def test_wrong_kind_in_llm_local_slot_is_unknown():
    """tunnel 열거값(down)이 llm_local 칸에 들어오면 모르는 값이다."""
    assert r.view_state("llm_local", _rec("down", 1), NOW) == "unknown"
    assert r.view_state("tunnel", _rec("unavailable", 1), NOW) == "unknown"
