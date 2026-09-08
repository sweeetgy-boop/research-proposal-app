"""조립 지점 검증. 임베딩·DB·네트워크를 만들지 않는다."""

import httpx
import pytest

from rra.adapters.llm.errors import InsecureLLMEndpoint
from rra.composition import build_llm, build_prompt_library, llm_config
from rra.settings import Settings

YAML = """
provider: mlx
base_url: http://127.0.0.1:8080/v1
json_mode: prompt
temperature: 0.1
timeout: {connect: 1, read: 2, write: 3, pool: 4}
retries: {attempts: 5, backoff_sec: 0.25, max_backoff_sec: 2}
limits: {max_tokens_cap: 1500, prompt_max_chars: 900}
stages:
  compose:  {model: local-14b, max_tokens: 2000}
  critique: {model: local-7b, max_tokens: 800}
"""


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "llm.yaml").write_text(YAML, encoding="utf-8")
    return tmp_path


def settings_for(config_dir, **kw):
    return Settings(_env_file=None, config_dir=config_dir, **kw)


def test_stage_table_drives_model_and_max_tokens(config_dir):
    s = settings_for(config_dir)
    assert llm_config(s, "compose")["model"] == "local-14b"
    assert llm_config(s, "compose")["max_tokens"] == 2000
    assert llm_config(s, "critique")["model"] == "local-7b"
    assert llm_config(s, "critique")["max_tokens"] == 800


def test_unknown_stage_is_an_error(config_dir):
    with pytest.raises(KeyError, match="expand"):
        llm_config(settings_for(config_dir), "expand")


def test_limits_and_policies_come_from_yaml(config_dir):
    cfg = llm_config(settings_for(config_dir))
    assert cfg["max_tokens_cap"] == 1500
    assert cfg["prompt_max_chars"] == 900
    assert cfg["json_mode"] == "prompt"
    assert cfg["retry"] == {"attempts": 5, "backoff_sec": 0.25, "max_backoff_sec": 2.0}
    assert cfg["timeout"]["read"] == 2.0


def test_env_overrides_yaml_only_when_set(config_dir, monkeypatch):
    assert llm_config(settings_for(config_dir))["base_url"] == "http://127.0.0.1:8080/v1"
    monkeypatch.setenv("RRA_LLM_BASE_URL", "http://localhost:9999/v1")
    assert llm_config(settings_for(config_dir))["base_url"] == "http://localhost:9999/v1"


def test_missing_llm_yaml_reports_the_stage(tmp_path):
    with pytest.raises(KeyError):
        llm_config(settings_for(tmp_path), "compose")


def test_build_llm_binds_stage_settings(config_dir):
    llm = build_llm(settings_for(config_dir), stage="critique")
    assert llm.model == "local-7b"
    assert llm.max_tokens == 800
    assert llm.max_tokens_cap == 1500
    assert llm.json_mode == "prompt"
    assert llm.retry.attempts == 5
    assert isinstance(llm._client.timeout, httpx.Timeout)


def test_build_llm_refuses_remote_base_url_for_local_provider(config_dir):
    (config_dir / "llm.yaml").write_text(
        YAML.replace("http://127.0.0.1:8080/v1", "http://gpu.example.com/v1"), encoding="utf-8"
    )
    with pytest.raises(InsecureLLMEndpoint):
        build_llm(settings_for(config_dir))


def test_api_key_is_read_from_settings_not_yaml(config_dir):
    llm = build_llm(settings_for(config_dir))
    assert "Authorization" not in llm._headers  # 기본 api_key 는 자리표시자 "none"


def test_prompt_library_prefers_config_override(config_dir):
    prompts_dir = config_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "system.md").write_text("현장 프롬프트", encoding="utf-8")
    assert build_prompt_library(settings_for(config_dir)).system() == "현장 프롬프트"


def test_prompt_library_falls_back_to_package(config_dir):
    assert "<doc" in build_prompt_library(settings_for(config_dir)).system()
