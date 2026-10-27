"""config/strategy.yaml source 스위치 — draft 면 초안 파일(status draft), confirmed 면 확정 파일."""

from pathlib import Path

import pytest
import yaml

from rra.config_loader import strategy_catalog, strategy_source
from rra.settings import Settings


def _settings(tmp_path: Path, source: str | None) -> Settings:
    (tmp_path / "templates").mkdir()
    if source is not None:
        (tmp_path / "strategy.yaml").write_text(f"source: {source}\n", encoding="utf-8")
    (tmp_path / "templates" / "korail_strategy.draft.yaml").write_text(
        yaml.safe_dump(
            {
                "source": "초안",
                "directions": [
                    {"id": "D1", "name": "안전", "tasks": [{"id": "D1-1", "name": "AI"}]}
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (tmp_path / "templates" / "korail_strategy.yaml").write_text(
        "source: ''\ndirections: []\n", encoding="utf-8"
    )
    return Settings(config_dir=tmp_path)


def test_draft_source_uses_draft_file_with_label(tmp_path):
    s = _settings(tmp_path, "draft")
    assert strategy_source(s) == "draft"
    catalog = strategy_catalog(s)
    assert catalog.status == "draft" and catalog.label == "전략체계 초안(확인 전)"
    assert catalog.options() == {"D1-1": "안전 > AI"}


def test_confirmed_source_uses_confirmed_file_and_is_default(tmp_path):
    s = _settings(tmp_path, "confirmed")
    assert strategy_catalog(s).status == "confirmed" and strategy_catalog(s).label is None
    assert strategy_catalog(s).directions == []
    (tmp_path / "x").mkdir()
    assert strategy_source(_settings(tmp_path / "x", None)) == "confirmed"


def test_unknown_source_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        strategy_source(_settings(tmp_path, "image"))


def test_repo_config_points_at_draft_until_promoted():
    assert strategy_source(Settings()) == "draft"
    catalog = strategy_catalog(Settings())
    assert catalog.status == "draft"
