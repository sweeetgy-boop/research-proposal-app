"""`/healthz` 운영 상태 칸(entrypoints/api/health_view) — 포트 스냅샷 → 열거값만. app.py 연결은
통합 때."""

from datetime import UTC, datetime, timedelta

from rra.application.ports.ops_status import OpsStatusPort
from rra.entrypoints.api.health_view import ops_fields, with_ops

NOW = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)


class Snap:
    def __init__(self, data):
        self.data = data

    def snapshot(self):
        return self.data


def _rec(state, minutes_ago=1):
    stamp = (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    return {"state": state, "since": stamp, "checked_at": stamp}


def test_ops_fields_reads_the_port_and_returns_enums_only():
    snap = Snap({"tunnel": _rec("down"), "llm_local": _rec("ok"), "host": "<must-not-leak>"})
    assert isinstance(snap, OpsStatusPort)
    assert ops_fields(snap, now=lambda: NOW) == {"tunnel": "down", "local": "ok"}
    assert ops_fields(Snap(None), now=lambda: NOW) == {"tunnel": "unknown", "local": "unknown"}
    stale = Snap({"tunnel": _rec("ok", 20), "llm_local": _rec("unavailable", 3)})
    assert ops_fields(stale, now=lambda: NOW) == {"tunnel": "unknown", "local": "unavailable"}


def test_with_ops_adds_tunnel_and_llm_local_keeping_existing_fields():
    out = {"status": "ok", "version": {"short": "abc"}, "llm": {"gemini": "ok", "since": None}}
    got = with_ops(
        out, Snap({"tunnel": _rec("ok"), "llm_local": _rec("unavailable")}), now=lambda: NOW
    )
    assert got is out
    assert got == {
        "status": "ok",
        "version": {"short": "abc"},
        "llm": {"gemini": "ok", "since": None, "local": "unavailable"},
        "tunnel": "ok",
    }


def test_with_ops_creates_llm_with_gemini_unknown_when_missing_and_skips_without_port():
    got = with_ops({"status": "ok"}, Snap({"tunnel": _rec("down")}), now=lambda: NOW)
    assert got == {
        "status": "ok",
        "tunnel": "down",
        "llm": {"gemini": "unknown", "since": None, "local": "unknown"},
    }
    assert with_ops({"status": "ok"}, None) == {"status": "ok"}


def test_with_ops_output_contains_only_enum_strings():
    got = with_ops(
        {"status": "ok"},
        Snap({"tunnel": {"state": "down", "checked_at": NOW.isoformat(), "note": "x"}}),
        now=lambda: NOW,
    )
    assert got["tunnel"] in {"ok", "down", "unknown"} and got["llm"]["local"] in {
        "ok",
        "unavailable",
        "unknown",
    }
    assert "note" not in str(got) and "checked_at" not in str(got)
