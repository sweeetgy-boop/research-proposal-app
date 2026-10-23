"""설정 로더 검증 — yaml 읽기·병합·환경변수 우선순위·domain 값 객체 변환.

어댑터·모델·네트워크를 만들지 않는다.
"""

from pathlib import Path

import pytest

from rra.config_loader import credential_status, llm_config, own_unit, served_model_aliases
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


def project_settings(**kw):
    return Settings(_env_file=None, **kw)


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


def test_own_unit_absent_means_no_own_tier(tmp_path):

    (tmp_path / "sources.yaml").write_text("institutions: []\n", encoding="utf-8")
    assert own_unit(settings_for(tmp_path)) is None


def test_shipped_config_lists_own_departments():

    own = own_unit(settings_for(ROOT_CONFIG))
    assert {"경영연구처", "기술연구처"} <= own.departments


def test_project_config_allows_data_go_kr_for_catalog():
    from rra.config_loader import read_config

    assert (
        "www.data.go.kr"
        in read_config("security.yaml", Settings(_env_file=None))["allowed_domains"]
    )


def test_lint_rules_and_section_order_come_from_template():
    from rra.config_loader import lint_rules

    rules = lint_rules(Settings(_env_file=None))
    assert rules.template == "korail_rnd_proposal_v2024"
    assert rules.order[:3] == ["title", "task_type", "policy_importance"]
    assert rules.order[-1] == "overlap_review"
    assert set(rules.evidence_required) == {"tech_importance", "overlap_review"}
    assert rules.evidence_forbidden == ["policy_importance"]
    assert set(rules.choices) == {"task_type", "utilization", "strategy_alignment"}
    # 입력·목록이 비면 빈칸이 정상인 섹션은 필수가 아니다
    assert not {"policy_importance", "strategy_alignment"} & set(rules.required_sections)


def test_strategy_catalog_rejects_bad_or_duplicate_ids(tmp_path):
    from pydantic import ValidationError

    from rra.config_loader import strategy_catalog

    (tmp_path / "templates").mkdir()
    path = tmp_path / "templates" / "korail_strategy.yaml"
    settings = Settings(_env_file=None, config_dir=tmp_path)
    path.write_text(
        "directions:\n  - id: D1\n    name: 안전\n    tasks:\n"
        "      - {id: D1-1, name: 예방정비}\n      - {id: D1-1, name: 중복}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        strategy_catalog(settings)
    path.write_text(
        "directions:\n  - id: D1\n    name: 안전\n    tasks:\n      - {id: D1-1, name: 예방정비}\n",
        encoding="utf-8",
    )
    assert strategy_catalog(settings).options() == {"D1-1": "안전 > 예방정비"}


def test_blank_env_values_count_as_missing():
    from rra.config_loader import credential_status

    assert credential_status(project_settings(ntis_key="  "), "ntis") == {"RRA_NTIS_KEY": False}
    assert credential_status(project_settings(ntis_key="k"), "ntis") == {"RRA_NTIS_KEY": True}


def test_keyword_rule_from_overlap_yaml_reaches_precheck_and_generate(tmp_path):
    from rra.config_loader import keyword_rule
    from rra.domain.rules.keywords import DEFAULT_GENERIC_TERMS

    (tmp_path / "overlap.yaml").write_text(
        "keywords:\n  min_hits: 3\n  generic_terms: [안전성을, ' Data ']\n", encoding="utf-8"
    )
    rule = keyword_rule(settings_for(tmp_path))
    assert rule.min_hits == 3
    assert {"안전성", "data"} <= rule.generic_terms and DEFAULT_GENERIC_TERMS <= rule.generic_terms


def test_keyword_rule_defaults_without_overlap_yaml(tmp_path):
    from rra.config_loader import keyword_rule
    from rra.domain.rules.keywords import KeywordRule

    assert keyword_rule(settings_for(tmp_path)) == KeywordRule()


def test_shipped_overlap_yaml_loads():
    from rra.config_loader import keyword_rule
    from rra.settings import load_settings

    rule = keyword_rule(load_settings())
    assert rule.min_hits == 2 and "안전" in rule.generic_terms


def test_served_model_is_optional(config_dir):
    assert llm_config(settings_for(config_dir), "compose")["served_model"] is None


def test_served_model_aliases_add_the_resolved_local_path(tmp_path, monkeypatch):
    model_dir = tmp_path / "models" / "qwen"
    model_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert served_model_aliases("models/qwen") == {"models/qwen", str(model_dir.resolve())}
    assert served_model_aliases("mlx-community/x") == {"mlx-community/x"}
    assert served_model_aliases(None) == frozenset()


def test_credential_status_never_returns_values():
    status = credential_status(project_settings(ntis_key="NTIS-SECRET"), "ntis")
    assert status == {"RRA_NTIS_KEY": True} and "NTIS-SECRET" not in repr(status)
    assert credential_status(project_settings(), "openalex") == {}  # 키 없는 소스
