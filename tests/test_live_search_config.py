"""[4] config/live_search.yaml 로더 — 저장소 설정·파일 없음(꺼짐)·모르는 키·캐시 경로."""

from __future__ import annotations

import pytest

from rra.config_loader import data_location, live_search_config
from rra.settings import Settings


def test_repo_config_is_on_with_three_sources():
    cfg = live_search_config(Settings(_env_file=None))
    assert cfg.enabled is True and cfg.fake_mode is False
    assert cfg.enabled_sources() == ["scienceon", "ntis", "openalex"]
    assert cfg.per_source_timeout_seconds == 10 and cfg.overall_timeout_seconds == 15
    assert cfg.wait_seconds == 15 and cfg.cache_hours == 24
    assert all(cfg.source(n).top_n == 30 for n in cfg.enabled_sources())
    assert cfg.keywords.stage == "review"


def test_missing_file_is_off_and_unknown_key_rejected(tmp_path):
    settings = Settings(_env_file=None, config_dir=tmp_path, data_dir=tmp_path / "data")
    assert live_search_config(settings).enabled is False
    (tmp_path / "live_search.yaml").write_text("enabled: true\nbogus: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bogus"):
        live_search_config(settings)


def test_cache_dir_under_data_dir(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    assert data_location(settings, "live_search_cache") == tmp_path / "data/cache/live_search"
