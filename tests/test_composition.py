"""조립 지점 검증. 임베딩·DB·네트워크를 만들지 않는다."""

from pathlib import Path

import httpx
import pytest

from rra.adapters.llm.errors import InsecureLLMEndpoint
from rra.composition import build_llm, build_prompt_library, llm_config
from rra.settings import Settings

ROOT_CONFIG = Path(__file__).parents[1] / "config"

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
  summary:
    inbox_dir: {summary}
    max_file_kb: 64
    default_org: korail
    labels: {{title: [과제명칭]}}
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
        ALIO_SOURCES.format(
            inbox=tmp_path / "inbox", catalog=tmp_path / "cat", summary=tmp_path / "summary"
        ),
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


def test_alio_summary_source_is_wired(alio_config):
    from rra.composition import build_sources

    [src] = build_sources(["alio_summary"], settings_for(alio_config))
    assert src.source == "alio_summary" and src.inbox == alio_config / "summary"
    assert src.max_bytes == 64 * 1024 and src.limits.mem_mb == 512
    assert src.labels["title"] == ["과제명칭"]
    assert src.labels["purpose"] == ["연구목적"]  # 나머지는 기본값
    assert src.institutions[0]["tag"] == "korail"
    assert src.catalog.catalog_dir == alio_config / "cat"
    assert src.default_org == "korail"


def test_own_unit_from_sources_yaml_reaches_precheck_and_ingest(tmp_path):
    from rra.composition import build_ingest, build_precheck, own_unit
    from tests.fakes import InMemoryRepository

    (tmp_path / "sources.yaml").write_text(
        "own_unit:\n  org: korail\n  departments: [경영연구처, ' 기술연구처 ', '']\n",
        encoding="utf-8",
    )
    settings = settings_for(tmp_path)
    own = own_unit(settings)
    assert own.org == "korail" and own.departments == {"경영연구처", "기술연구처"}
    repo = InMemoryRepository()
    assert build_precheck(settings, repo=repo).own == own
    assert build_ingest(settings, sources=[], repo=repo).own == own


def test_own_unit_absent_means_no_own_tier(tmp_path):
    from rra.composition import own_unit

    (tmp_path / "sources.yaml").write_text("institutions: []\n", encoding="utf-8")
    assert own_unit(settings_for(tmp_path)) is None


def test_shipped_config_lists_own_departments():
    from rra.composition import own_unit

    own = own_unit(settings_for(ROOT_CONFIG))
    assert {"경영연구처", "기술연구처"} <= own.departments


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


# ── generate · RunManager ─────────────────────────────────
def test_lint_rules_and_section_order_come_from_template():
    from rra.composition import lint_rules

    rules = lint_rules(Settings(_env_file=None))
    assert rules.required_sections[:2] == ["title", "background"]
    assert set(rules.evidence_required) == {"prior_work", "overlap_check", "differentiation"}


def test_every_section_has_a_prompt():
    from rra.composition import build_prompt_library, lint_rules

    settings = Settings(_env_file=None)
    prompts = build_prompt_library(settings)
    for key in lint_rules(settings).required_sections:
        assert prompts.section(key).strip(), key


def test_run_manager_wiring_is_lazy(tmp_path, monkeypatch):
    import rra.composition as comp

    def boom(*a, **k):
        raise AssertionError("상태 조회만 하는데 모델을 띄웠다")

    monkeypatch.setattr(comp, "build_embedding", boom)
    monkeypatch.setattr(comp, "build_llm", boom)
    settings = Settings(_env_file=None, runs_dir=tmp_path / "runs")
    mgr = comp.build_run_manager(settings)
    assert mgr.list_runs(comp.LOCAL_USER) == []
    assert mgr.max_queued == 3
    # manifest 에는 선언된 실제 모델명, 요청은 default_model
    assert mgr.model == "mlx-community/Qwen2.5-3B-Instruct-4bit"
    assert comp.llm_config(settings, "compose")["model"] == "default_model"
    assert mgr.store.root == tmp_path / "runs"
    assert mgr.slot.path == tmp_path / "runs" / ".generate.lock"
    assert mgr.generate.section_keys[0] == "title"


# ── served_model (manifest 표시용 모델명) ─────────────────
class ListingLLM:
    def __init__(self, listed=None, error=None):
        self.listed, self.error = listed or [], error

    async def list_models(self):
        if self.error:
            raise self.error
        return self.listed


def test_served_model_is_optional(config_dir):
    assert llm_config(settings_for(config_dir), "compose")["served_model"] is None


async def test_served_model_listed_means_no_warning():
    from rra.composition import check_served_model

    cfg = {"served_model": "mlx-community/Qwen2.5-3B-Instruct-4bit"}
    llm = ListingLLM(["mlx-community/Qwen2.5-3B-Instruct-4bit", "other/model"])
    assert await check_served_model(cfg, llm) is None


async def test_typo_in_served_model_warns_with_the_list():
    from rra.composition import check_served_model

    cfg = {"served_model": "mlx-community/Qwen2.5-3b-Instruct-4bit"}  # 대소문자 오타
    warning = await check_served_model(cfg, ListingLLM(["mlx-community/Qwen2.5-3B-Instruct-4bit"]))
    assert "목록에 없습니다" in warning and "Qwen2.5-3B" in warning


async def test_local_path_matches_the_resolved_path(tmp_path, monkeypatch):
    from rra.composition import check_served_model

    model_dir = tmp_path / "models" / "qwen"
    model_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    cfg = {"served_model": "models/qwen"}  # 상대경로로 선언, 서버는 절대경로로 싣는다
    assert await check_served_model(cfg, ListingLLM([str(model_dir.resolve())])) is None


async def test_listing_failure_and_missing_key_only_warn():
    from rra.adapters.llm import LLMError
    from rra.composition import check_served_model

    failed = await check_served_model({"served_model": "x"}, ListingLLM(error=LLMError("down")))
    assert "조회 실패 (LLMError)" in failed and "down" not in failed
    assert "served_model 이 없습니다" in await check_served_model({}, ListingLLM())
    assert await check_served_model({"served_model": "x"}, object()) is None  # 목록 기능 없는 LLM


# ── Step 7: 키 관리·ScienceON·NTIS 조립 ─────────────────
SCIENCEON_KEYS = {
    "scienceon_client_id": "CID-1",
    "scienceon_key": "0123456789abcdef0123456789abcdef",
    "scienceon_mac": "AA-BB-CC-DD-EE-FF",
}


def project_settings(**kw):
    return Settings(_env_file=None, **kw)


def test_missing_credentials_name_variables_not_values():
    from rra.composition import MissingCredential, build_sources

    with pytest.raises(MissingCredential) as info:
        build_sources(["ntis"], project_settings())
    assert "RRA_NTIS_KEY" in str(info.value)
    with pytest.raises(MissingCredential) as info:
        build_sources(
            ["scienceon"], project_settings(scienceon_key=SCIENCEON_KEYS["scienceon_key"])
        )
    msg = str(info.value)
    assert "RRA_SCIENCEON_CLIENT_ID" in msg and "RRA_SCIENCEON_MAC" in msg
    assert "RRA_SCIENCEON_KEY" not in msg and "0123456789abcdef" not in msg


def test_blank_env_values_count_as_missing():
    from rra.composition import credential_status

    assert credential_status(project_settings(ntis_key="  "), "ntis") == {"RRA_NTIS_KEY": False}
    assert credential_status(project_settings(ntis_key="k"), "ntis") == {"RRA_NTIS_KEY": True}


def test_scienceon_wiring_uses_rate_limit_policy():
    from rra.composition import build_scienceon_source

    src = build_scienceon_source(project_settings(**SCIENCEON_KEYS))
    assert src.client.min_interval == pytest.approx(1.0)  # 초당 1회
    assert src.client.max_requests == 40 and src.max_consecutive_429 == 2
    assert src.client.max_backoff_sec == 30
    assert "apigateway.kisti.re.kr" in src.client.allowed
    assert src.targets == ["ARTI", "REPORT"]
    assert "CID-1" not in repr(src) and "CID-1" not in repr(src.tokens)


def test_ntis_wiring_and_shared_institutions():
    from rra.composition import build_ntis_source, institutions

    settings = project_settings(ntis_key="NTIS-K")
    src = build_ntis_source(settings)
    assert src.url.startswith("https://www.ntis.go.kr/")
    assert src.client.max_requests == 60
    tags = {i["tag"]: i for i in institutions(settings)}
    assert "한국철도시설공단" in tags["kr"]["aliases"]
    assert src.institutions == institutions(settings)
    assert "NTIS-K" not in repr(src)


def test_alio_still_reads_institutions_after_move(tmp_path):
    from rra.composition import build_alio_catalog, institutions

    settings = project_settings()
    assert [i["tag"] for i in institutions(settings)] == ["korail", "krri", "kr"]
    assert build_alio_catalog(settings).institutions == institutions(settings)
    # 예전 위치(alio.institutions)만 있는 설정도 읽는다
    (tmp_path / "sources.yaml").write_text(
        "alio:\n  institutions:\n    - {code: C0268, name: 한국철도공사, tag: korail}\n",
        encoding="utf-8",
    )
    assert institutions(settings_for(tmp_path))[0]["tag"] == "korail"


async def test_check_sources_reports_without_values():
    from rra.composition import check_sources

    def handler(request):
        if request.url.path == "/tokenrequest.do":
            return httpx.Response(200, json={"access_token": "A", "refresh_token": "R"})
        return httpx.Response(
            200,
            content=b"<MetaData><resultSummary><TotalCount>7</TotalCount></resultSummary></MetaData>",
            headers={"content-type": "text/xml"},
        )

    settings = project_settings(**SCIENCEON_KEYS)
    rows = await check_sources(
        settings,
        ["scienceon", "ntis"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
    )
    sci, ntis = rows
    assert sci["roundtrip"] == "ok" and sci["result"] == {
        "auth": "ok",
        "totals": {"ARTI": 7, "REPORT": 7},
    }
    assert ntis["roundtrip"] == "skipped" and ntis["credentials"] == {"RRA_NTIS_KEY": False}
    import json as _json

    dumped = _json.dumps(rows, ensure_ascii=False)
    assert "CID-1" not in dumped and "0123456789abcdef" not in dumped and "AA-BB-CC" not in dumped
