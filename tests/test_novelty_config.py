"""config/novelty.yaml 로더 (ADR 0057) — 저장소 설정·파일 없음(기본값)·모르는 키,
학술지 메타데이터."""

from __future__ import annotations

import pytest

from rra.adapters.sources.scienceon.normalize import normalize_record
from rra.config_loader import live_search_config, novelty_config
from rra.domain.rules.novelty import NoveltyConfig
from rra.settings import Settings


def test_repo_config_widens_live_search_without_touching_it():
    settings = Settings(_env_file=None)
    cfg = novelty_config(settings)
    base = live_search_config(settings)
    wide = cfg.novelty.live.live_config(base)
    assert base.max_queries == 3  # live_search.yaml 은 그대로
    assert wide.max_queries == 5 and wide.wait_seconds >= base.wait_seconds
    assert wide.per_source_timeout_seconds > base.per_source_timeout_seconds
    assert all(wide.source(n).top_n > base.source(n).top_n for n in base.enabled_sources())
    # 질의 5개를 다 보낼 만큼 요청 상한 (ScienceON target 3 × 5 + 토큰 1)
    assert wide.source("scienceon").max_requests >= 16
    assert cfg.analogy.max_results == 5 and cfg.analogy.axis.max_terms >= 3
    assert "own" in cfg.rail_field.sources and "korail" in cfg.rail_field.orgs
    assert "own" not in cfg.analogy.search_sources


def test_missing_file_is_defaults_and_unknown_key_rejected(tmp_path):
    settings = Settings(_env_file=None, config_dir=tmp_path, data_dir=tmp_path / "data")
    assert novelty_config(settings) == NoveltyConfig()
    (tmp_path / "novelty.yaml").write_text("bogus: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bogus"):
        novelty_config(settings)
    (tmp_path / "novelty.yaml").write_text("analogy:\n  bogus: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        novelty_config(settings)


def test_scienceon_journal_kept_for_domain_label():
    doc = normalize_record(
        {"target": "ARTI", "CN": "JAKO1", "Title": "조류 퇴치", "JournalName": "한국조류학회지"}
    )
    assert doc.raw["journal"] == "한국조류학회지"
    assert normalize_record({"target": "PATENT", "CN": "K1", "Title": "x"}).raw["journal"] is None
