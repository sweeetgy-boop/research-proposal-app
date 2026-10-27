from datetime import datetime
from pathlib import Path

import pytest
import yaml

from rra.application.usecases.strategy_catalog import promote_strategy

DRAFT = {
    "source": "코레일 중장기 경영목표",
    "status": "draft",
    "directions": [
        {"id": "D1", "name": "안전", "basis": "text", "tasks": [{"id": "D1-1", "name": "AI 안전"}]}
    ],
}


def test_promote_copies_draft_keeps_backup_and_flips_source(tmp_path: Path):
    draft = tmp_path / "korail_strategy.draft.yaml"
    draft.write_text(yaml.safe_dump(DRAFT, allow_unicode=True), encoding="utf-8")
    target = tmp_path / "korail_strategy.yaml"
    target.write_text("source: ''\ndirections: []\n", encoding="utf-8")
    cfg = tmp_path / "strategy.yaml"
    cfg.write_text("source: draft\n", encoding="utf-8")
    report = promote_strategy(draft, target, cfg, clock=lambda: datetime(2026, 10, 27, 15, 0, 0))
    assert report.directions == 1 and report.tasks == 1
    assert (
        report.backup is not None
        and report.backup.name == "korail_strategy.yaml.bak-20261027-150000"
    )
    assert report.backup.read_text(encoding="utf-8") == "source: ''\ndirections: []\n"
    assert yaml.safe_load(target.read_text(encoding="utf-8"))["directions"][0]["id"] == "D1"
    assert yaml.safe_load(cfg.read_text(encoding="utf-8")) == {"source": "confirmed"}


def test_promote_refuses_missing_or_empty_draft(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        promote_strategy(tmp_path / "none.yaml", tmp_path / "t.yaml", tmp_path / "s.yaml")
    draft = tmp_path / "d.yaml"
    draft.write_text("directions: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        promote_strategy(draft, tmp_path / "t.yaml", tmp_path / "s.yaml")
    assert not (tmp_path / "t.yaml").exists() and not (tmp_path / "s.yaml").exists()
