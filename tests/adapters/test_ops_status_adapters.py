"""운영 상태 어댑터 — 상태 파일(600)·Tailscale 점검(normalize 순수 함수 + 가짜 명령)·로컬 모델 점검.
fixture 는 합성이며 IP·호스트명·계정을 가린 자리표시자만 쓴다 (계약: 원문 저장·기록 금지)."""

import json
import os
import stat
from datetime import UTC, datetime

import httpx
import pytest

from rra.adapters.deploy.ops_status import FileOpsStatus
from rra.adapters.deploy.tunnel_status import (
    TailscaleProbe,
    normalize_funnel_text,
    normalize_status_json,
)
from rra.adapters.llm.local_status import LocalLlmProbe
from rra.application.ports.ops_status import OpsStatusPort, OpsStatusWriterPort, TunnelProbePort

# ── 합성 fixture (실제 출력 모양, 값은 가림) ──────────────────
STATUS_JSON = {
    "Version": "1.xx",
    "BackendState": "Running",
    "MagicDNSSuffix": "<tailnet>.ts.net",
    "Self": {"HostName": "<host>", "TailscaleIPs": ["<ip4>", "<ip6>"], "UserID": 0},
    "Peer": {},
    "CurrentTailnet": {"Name": "<account>"},
}
FUNNEL_ON_TEXT = (
    "\n# Funnel on:\n#     - https://<host>.<tailnet>.ts.net\n\n"
    "https://<host>.<tailnet>.ts.net (Funnel on)\n|-- / proxy http://127.0.0.1:8000\n"
)
FUNNEL_OFF_TEXT = "No serve config\n"


def test_normalize_status_json_returns_backend_state_only():
    assert normalize_status_json(json.dumps(STATUS_JSON)) == "Running"
    assert (
        normalize_status_json(json.dumps({**STATUS_JSON, "BackendState": "Stopped"})) == "Stopped"
    )
    assert normalize_status_json(json.dumps({**STATUS_JSON, "BackendState": "Surprise"})) is None
    assert normalize_status_json("not json") is None
    assert normalize_status_json("[]") is None and normalize_status_json("") is None
    assert normalize_status_json("{" + "x" * 1_000_001) is None


def test_normalize_funnel_text_finds_the_mark_only():
    assert normalize_funnel_text(FUNNEL_ON_TEXT) is True
    assert normalize_funnel_text(FUNNEL_OFF_TEXT) is False
    assert normalize_funnel_text("") is False
    assert normalize_funnel_text("(Funnel on)" + "x" * 1_000_001) is False


def _fake_tailscale(tmp_path, status_json, funnel_text, *, fail_funnel=False, fail_status=False):
    """가짜 tailscale 실행 파일 — 인자에 따라 합성 출력을 낸다."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    status_file = tmp_path / "status.json"
    status_file.write_text(json.dumps(status_json), encoding="utf-8")
    funnel_file = tmp_path / "funnel.txt"
    funnel_file.write_text(funnel_text, encoding="utf-8")
    script = tmp_path / "tailscale"
    script.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "status" ]; then {"exit 1" if fail_status else f"cat {status_file}"}; fi\n'
        f'if [ "$1" = "funnel" ]; then {"exit 1" if fail_funnel else f"cat {funnel_file}"}; fi\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_tailscale_probe_running_and_funnel_on(tmp_path):
    probe = TailscaleProbe(_fake_tailscale(tmp_path, STATUS_JSON, FUNNEL_ON_TEXT))
    assert isinstance(probe, TunnelProbePort) and probe.available
    result = probe.probe()
    assert (result.backend_state, result.funnel_on) == ("Running", True)
    assert "<host>" not in repr(probe) and "<ip4>" not in repr(
        result
    )  # 원문은 포트 밖으로 안 나간다


def test_tailscale_probe_funnel_off_or_failed_means_funnel_false(tmp_path):
    off = TailscaleProbe(_fake_tailscale(tmp_path / "a", STATUS_JSON, FUNNEL_OFF_TEXT)).probe()
    assert (off.backend_state, off.funnel_on) == ("Running", False)
    failed = TailscaleProbe(
        _fake_tailscale(tmp_path / "b", STATUS_JSON, FUNNEL_ON_TEXT, fail_funnel=True)
    ).probe()
    assert (failed.backend_state, failed.funnel_on) == ("Running", False)


def test_tailscale_probe_unknown_when_binary_missing_or_status_fails(tmp_path):
    missing = TailscaleProbe(tmp_path / "nope")
    assert not missing.available
    assert missing.probe().backend_state is None and missing.probe().funnel_on is None
    broken = TailscaleProbe(
        _fake_tailscale(tmp_path, STATUS_JSON, FUNNEL_ON_TEXT, fail_status=True)
    )
    assert broken.probe().backend_state is None


def test_tailscale_probe_never_logs_output(tmp_path, caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger="rra.ops")
    TailscaleProbe(_fake_tailscale(tmp_path, STATUS_JSON, FUNNEL_ON_TEXT, fail_funnel=True)).probe()
    text = caplog.text
    assert "<host>" not in text and "<ip4>" not in text and "<account>" not in text


# ── 상태 파일 ─────────────────────────────────────────────
def test_file_ops_status_writes_600_enums_only_and_keeps_since(tmp_path):
    ticks = iter(datetime(2026, 11, 9, 14, m, tzinfo=UTC) for m in range(0, 59))
    store = FileOpsStatus(tmp_path / "cache" / "ops_status.json", now=lambda: next(ticks))
    assert isinstance(store, OpsStatusPort) and isinstance(store, OpsStatusWriterPort)
    assert store.snapshot() is None
    store.record("tunnel", "ok")
    store.record("llm_local", "unavailable")
    store.record("tunnel", "ok")
    path = tmp_path / "cache" / "ops_status.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"tunnel", "llm_local"}
    assert data["tunnel"]["state"] == "ok" and data["tunnel"]["since"].endswith("14:00:00+00:00")
    assert data["tunnel"]["checked_at"].endswith("14:02:00+00:00")
    assert data["llm_local"] == {
        "state": "unavailable",
        "since": "2026-11-09T14:01:00+00:00",
        "checked_at": "2026-11-09T14:01:00+00:00",
    }
    assert store.snapshot() == data


def test_file_ops_status_ignores_unknown_kind_or_state_and_bad_file(tmp_path):
    path = tmp_path / "ops_status.json"
    store = FileOpsStatus(path)
    store.record("tunnel", "unknown")
    store.record("llm_local", "down")
    store.record("other", "ok")
    assert not path.exists()
    path.write_text("not json", encoding="utf-8")
    assert store.snapshot() is None
    store.record("tunnel", "down")  # 깨진 파일 위에 새로 쓴다
    assert store.snapshot()["tunnel"]["state"] == "down"


def test_file_ops_status_swallows_write_errors(tmp_path):
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x", encoding="utf-8")
    store = FileOpsStatus(blocked / "ops_status.json")
    store.record("tunnel", "ok")  # 부모가 파일이라 실패 — 예외 없이 넘어간다
    assert store.snapshot() is None


# ── 로컬 모델 점검 ─────────────────────────────────────────
def _probe(handler, **kw):
    return LocalLlmProbe("http://127.0.0.1:8080/v1", transport=httpx.MockTransport(handler), **kw)


def test_local_probe_true_on_2xx_models_listing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    assert _probe(handler).probe() is True
    assert seen[0].url.path == "/v1/models" and seen[0].method == "GET"
    assert "Authorization" not in seen[0].headers


@pytest.mark.parametrize("status", [404, 500, 503])
def test_local_probe_false_on_error_status(status):
    assert _probe(lambda r: httpx.Response(status)).probe() is False


def test_local_probe_false_on_timeout_or_connection_error():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    assert _probe(timeout).probe() is False and _probe(refused).probe() is False


def test_local_probe_refuses_non_loopback_base_url():
    from rra.adapters.llm.errors import InsecureLLMEndpoint

    with pytest.raises(InsecureLLMEndpoint):
        LocalLlmProbe("http://10.0.0.5:8080/v1")


def test_local_probe_timeout_is_short_by_default():
    probe = _probe(lambda r: httpx.Response(200, json={"data": []}))
    assert probe.timeout == 5.0
    assert LocalLlmProbe("http://localhost:8080/v1", timeout=0.1).timeout == 0.5  # 하한 0.5초
