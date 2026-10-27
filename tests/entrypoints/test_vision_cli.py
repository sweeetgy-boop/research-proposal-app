"""`rra vision read|sample` 배선 — composition 을 monkeypatch, 페이크 유스케이스."""

import json

import pytest

from rra.adapters.vision.store import MemoryVisionStore
from rra.application.usecases.read_images import ReadImages
from rra.entrypoints.cli import EXIT_OK, main
from tests.vision_helpers import (
    TABLE_READING,
    FakeOcr,
    FakeReader,
    icon_image,
    item,
    sha,
    snapshot_of,
    table_image,
)


@pytest.fixture
def usecase():
    table, icon = table_image(), icon_image()
    snap = snapshot_of(
        (table, item(table, "stat/t.png", page_title="통계")), (icon, item(icon, "ico_x.png"))
    )
    return ReadImages(
        snap,
        MemoryVisionStore(),
        ocr=FakeOcr({sha(table): "수송인원 1,234만명"}),
        reader=FakeReader([TABLE_READING]),
        prompt="V",
        cap=2000,
    )


@pytest.fixture
def stub(monkeypatch, usecase):
    captured = {}

    def build(settings, **kw):
        captured.update(kw)
        return usecase

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_read_images", build)
    monkeypatch.setattr(
        "rra.composition.vision_config",
        lambda s: {"sample_dir": "docs/ocr-sample", "sample_per_type": 30},
    )
    return captured


def test_read_dry_run_prints_plan_and_makes_no_calls(stub, usecase, capsys):
    assert (
        main(["vision", "read", "--dry-run", "--snapshot", "2026-10-27", "--limit", "5"]) == EXIT_OK
    )
    out = capsys.readouterr().out
    assert "유지 1 / 제외 1" in out and "예상 호출 1건" in out and "dry-run" in out
    assert usecase.reader.calls == []
    assert stub == {"snapshot": "2026-10-27", "cap": None, "with_reader": True}


def test_read_json_reports_results_and_ocr_only_list(stub, usecase, capsys):
    assert main(["vision", "read", "--json", "--cap", "1"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == {"argon": 1} and payload["calls"] == 1
    assert payload["results"][0]["image_type"] == "표"
    assert payload["results"][0]["unconfirmed_numbers"] == ["2023", "2024", "1,300", "3.5%", "5.3%"]
    assert payload["ocr_only_hashes"] == []
    assert stub["cap"] == 1


def test_read_ocr_only_flag_skips_reader(stub, usecase, capsys):
    assert main(["vision", "read", "--ocr-only"]) == EXIT_OK
    assert stub["with_reader"] is False


def test_sample_writes_per_type_files_and_summary(stub, usecase, tmp_path, capsys):
    out = tmp_path / "ocr-sample"
    assert main(["vision", "sample", "--out", str(out), "--per-type", "5"]) == EXIT_OK
    names = sorted(p.name for p in out.iterdir())
    assert names == ["summary.json", "summary.md", "table.json"]
    rows = json.loads((out / "table.json").read_text(encoding="utf-8"))
    assert rows[0]["argon"]["image_type"] == "표" and rows[0]["ocr_text"] == "수송인원 1,234만명"
    printed = capsys.readouterr().out
    assert "| 표 | 1 |" in printed and "실제 호출 1건" in printed
