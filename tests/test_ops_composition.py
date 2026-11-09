"""운영 점검 조립·설정 — config_loader(api.yaml ops, llm.yaml timeout.first_request, 데이터 위치)와
composition.build_ops_status / build_ops_check / build_tunnel_probe / build_llm_check(_client).
네트워크·명령 없음."""

from pathlib import Path

import pytest

from rra import config_loader as cl
from rra.settings import Settings

LLM_YAML = """
provider: mlx
providers:
  mlx: {base_url: http://127.0.0.1:8080/v1, model_profile: qwen}
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai/
    model: gemini-4-argon
model_profiles:
  qwen:
    served_model: mlx-community/Qwen2.5-7B-Instruct-4bit
    model: default_model
    json_mode: prompt
timeout: {connect: 5, read: 600, write: 10, pool: 5, first_request: 240}
retries: {attempts: 3, backoff_sec: 0.5, max_backoff_sec: 8}
stages:
  compose: {max_tokens: 2000}
  review: {provider: gemini, max_tokens: 6000}
"""
SECURITY_YAML = "allowed_domains: [generativelanguage.googleapis.com]\n"


@pytest.fixture
def cfg_dir(tmp_path):
    (tmp_path / "llm.yaml").write_text(LLM_YAML, encoding="utf-8")
    (tmp_path / "security.yaml").write_text(SECURITY_YAML, encoding="utf-8")
    return tmp_path


def settings_for(config_dir, **kw):
    return Settings(_env_file=None, config_dir=config_dir, **kw)


# ── 설정 ───────────────────────────────────────────────────
def test_api_config_ops_tailscale_bin_default_and_override(tmp_path):
    s = settings_for(tmp_path)
    assert cl.api_config(s)["ops"] == {"tailscale_bin": cl.OPS_TAILSCALE_BIN_DEFAULT}
    (tmp_path / "api.yaml").write_text(
        "ops:\n  tailscale_bin: /opt/bin/tailscale\n", encoding="utf-8"
    )
    assert cl.api_config(s)["ops"]["tailscale_bin"] == "/opt/bin/tailscale"
    (tmp_path / "api.yaml").write_text("ops:\n  something: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ops"):
        cl.api_config(s)
    (tmp_path / "api.yaml").write_text("ops: [a]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cl.api_config(s)


def test_llm_config_exposes_first_request_timeout_outside_httpx_timeout(cfg_dir):
    cfg = cl.llm_config(settings_for(cfg_dir), "compose")
    assert cfg["first_request_timeout"] == 240.0
    assert set(cfg["timeout"]) == {"connect", "read", "write", "pool"}  # httpx.Timeout(**…) 그대로
    (cfg_dir / "llm.yaml").write_text(
        LLM_YAML.replace(", first_request: 240", ""), encoding="utf-8"
    )
    assert cl.llm_config(settings_for(cfg_dir), "compose")["first_request_timeout"] == 300.0


def test_ops_status_is_in_the_data_location_table(tmp_path):
    s = settings_for(tmp_path, data_dir=tmp_path / "d")
    assert cl.data_location(s, "ops_status") == tmp_path / "d" / "cache" / "ops_status.json"
    assert "ops_status" in cl.DATA_LOCATION_KEYS


# ── 조립 ───────────────────────────────────────────────────
def test_build_ops_status_is_shared_per_path_and_lives_in_the_data_dir(cfg_dir, tmp_path):
    from rra.composition import build_ops_status

    s = settings_for(cfg_dir, data_dir=tmp_path / "d")
    store = build_ops_status(s)
    assert store.path == tmp_path / "d" / "cache" / "ops_status.json"
    assert build_ops_status(s) is store
    store.record("tunnel", "ok")
    assert store.snapshot()["tunnel"]["state"] == "ok"


def test_build_tunnel_probe_is_none_when_binary_missing_and_uses_configured_path(cfg_dir, tmp_path):
    from rra.composition import build_tunnel_probe

    (cfg_dir / "api.yaml").write_text(
        f"ops:\n  tailscale_bin: {tmp_path / 'missing'}\n", encoding="utf-8"
    )
    assert build_tunnel_probe(settings_for(cfg_dir)) is None
    fake = tmp_path / "tailscale"
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    (cfg_dir / "api.yaml").write_text(f"ops:\n  tailscale_bin: {fake}\n", encoding="utf-8")
    probe = build_tunnel_probe(settings_for(cfg_dir))
    assert probe is not None and probe.bin_path == fake


def test_build_ops_check_wires_local_probe_to_mlx_base_url(cfg_dir, tmp_path):
    from rra.composition import build_ops_check

    (cfg_dir / "api.yaml").write_text(
        f"ops:\n  tailscale_bin: {tmp_path / 'missing'}\n", encoding="utf-8"
    )
    check = build_ops_check(settings_for(cfg_dir, data_dir=tmp_path / "d"))
    assert check.tunnel is None
    assert check.local.base_url == "http://127.0.0.1:8080/v1" and check.local.timeout == 5.0
    assert check.status.path == tmp_path / "d" / "cache" / "ops_status.json"


async def test_build_llm_check_client_applies_timeout_and_single_attempt(cfg_dir):
    from rra.composition import build_llm_check_client

    llm = build_llm_check_client(
        settings_for(cfg_dir), stage="compose", read_timeout=120, attempts=1
    )
    try:
        assert llm.provider == "mlx" and llm.retry.attempts == 1
        assert llm._client.timeout.read == 120 and llm._client.timeout.connect == 5
        assert llm._first_request_timeout == 240.0  # llm.yaml timeout.first_request → 로컬 첫 요청
    finally:
        await llm.aclose()


async def test_build_llm_check_defaults_local_to_120s_and_remote_to_yaml_read(cfg_dir, tmp_path):
    from rra.composition import build_llm_check

    s = settings_for(cfg_dir, data_dir=tmp_path / "d", gemini_api_key="gk-test-not-real")
    local = build_llm_check(s, stage="compose", served_check=False)
    remote = build_llm_check(s, stage="review", served_check=False)
    try:
        assert local.local and local.llm._client.timeout.read == 120.0
        assert not remote.local
        inner = getattr(remote.llm, "inner", remote.llm)  # BudgetedLLM 가 감쌀 수 있다
        client = getattr(inner, "_client", None) or remote.llm._client
        assert client.timeout.read == 600.0
        assert local.status.path == tmp_path / "d" / "cache" / "ops_status.json"
    finally:
        await local.llm.aclose()
        await remote.llm.aclose()


def test_build_first_request_timeout_is_passed_to_regular_llm_too(cfg_dir):
    from rra.composition import build_llm

    llm = build_llm(settings_for(cfg_dir), stage="compose")
    assert llm._first_request_timeout == 240.0
    assert Path(llm.base_url).name == "v1"
