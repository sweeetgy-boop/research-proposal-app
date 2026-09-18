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


# ── sources ───────────────────────────────────────────────
def test_openalex_source_reads_allowlist_and_policy(tmp_path):
    from rra.composition import build_openalex_source

    (tmp_path / "security.yaml").write_text(
        "allowed_domains: [api.openalex.org]\ninput_limits: {query_max_chars: 42}\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.yaml").write_text(
        "openalex: {rate_limit: 5, per_page: 50, default_query: tram, lookback_days: 3,"
        " max_response_mb: 1, max_redirects: 2}\n",
        encoding="utf-8",
    )
    src = build_openalex_source(settings_for(tmp_path))
    assert src.client.allowed == {"api.openalex.org"}
    assert src.client.min_interval == pytest.approx(0.2)
    assert src.client.max_response_bytes == 1024 * 1024
    assert src.client.max_redirects == 2
    assert (src.per_page, src.default_query, src.lookback_days) == (50, "tram", 3)
    assert src.query_max_chars == 42
    assert src.mailto is None


def test_missing_security_yaml_means_nothing_is_allowed(tmp_path):
    from rra.composition import build_openalex_source

    assert build_openalex_source(settings_for(tmp_path)).client.allowed == set()


def test_unknown_source_is_rejected(tmp_path):
    from rra.composition import build_sources

    with pytest.raises(KeyError):
        build_sources(["dart"], settings_for(tmp_path))


def test_project_config_allows_openalex():
    from rra.composition import build_openalex_source

    src = build_openalex_source(Settings(_env_file=None))
    assert "api.openalex.org" in src.client.allowed
    assert src.base_url == "https://api.openalex.org"


# ── alio ──────────────────────────────────────────────────
ALIO_SOURCES = """
alio:
  institutions:
    - {{code: C0268, name: 한국철도공사, tag: korail}}
  inbox_dir: {inbox}
  catalog_dir: {catalog}
  catalog:
    fetch_url: https://www.data.go.kr/f.csv
    max_response_mb: 1
    columns: {{title: [보고서제목]}}
"""


@pytest.fixture
def alio_config(tmp_path):
    (tmp_path / "security.yaml").write_text(
        "allowed_domains: [www.data.go.kr]\n"
        "file_limits: {parse_timeout_sec: 7, parse_mem_mb: 512, max_file_mb: 3,"
        " max_output_mb: 4, max_zip_entries: 9}\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.yaml").write_text(
        ALIO_SOURCES.format(inbox=tmp_path / "inbox", catalog=tmp_path / "cat"),
        encoding="utf-8",
    )
    return tmp_path


def test_sandbox_limits_from_security_yaml(alio_config):
    from rra.composition import sandbox_limits

    lim = sandbox_limits(settings_for(alio_config))
    assert (lim.timeout_sec, lim.mem_mb, lim.max_input_mb) == (7, 512, 3)
    assert (lim.max_output_mb, lim.max_zip_entries, lim.test_mode) == (4, 9, False)


def test_alio_source_is_wired_with_inbox_catalog_and_limits(alio_config):
    from rra.composition import build_sources

    [src] = build_sources(["alio"], settings_for(alio_config))
    assert src.source == "alio" and src.inbox == alio_config / "inbox"
    assert src.limits.mem_mb == 512
    assert src.catalog.catalog_dir == alio_config / "cat"
    assert src.catalog.columns["title"] == ["보고서제목"]
    assert src.catalog.institutions[0]["tag"] == "korail"


async def test_fetch_alio_catalog_goes_through_guarded_client(alio_config):
    from rra.composition import fetch_alio_catalog

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"a,b\n", headers={"content-type": "text/csv"})

    path = await fetch_alio_catalog(
        settings_for(alio_config),
        transport=httpx.MockTransport(handler),
        resolver=lambda host: False,  # DNS 없이
    )
    assert seen == ["https://www.data.go.kr/f.csv"]
    assert path.parent == alio_config / "cat" and path.read_bytes() == b"a,b\n"


async def test_fetch_alio_catalog_requires_url(tmp_path):
    from rra.composition import fetch_alio_catalog

    with pytest.raises(ValueError, match="fetch_url"):
        await fetch_alio_catalog(settings_for(tmp_path))


def test_project_config_allows_data_go_kr_for_catalog():
    from rra.composition import read_config

    assert (
        "www.data.go.kr"
        in read_config("security.yaml", Settings(_env_file=None))["allowed_domains"]
    )
