"""차별화 과제안 측정 파일(JsonlRecommendMetrics).

한 줄 모양·권한 700/600·5 MB 넘으면 .1·쓰기 실패 삼킴·심볼릭 링크 따라가지 않음·허용 칸 밖 거절.
"""

from __future__ import annotations

import json
import logging
import stat
from datetime import datetime

import pytest

from rra.adapters.logging.recommend_metrics import MAX_BYTES, JsonlRecommendMetrics
from rra.application.ports import RecommendMetricsPort
from rra.domain.models import RecommendationResult
from rra.domain.rules.recommend_metrics import FIELDS, metrics_row


def _row(**kw):
    result = RecommendationResult(provider="gemini", calls=2, retry_used=True, **kw)
    return metrics_row(result, mode="more", similar=1, seconds=3.456)


def test_appends_one_json_line_per_record_with_ts_first(tmp_path):
    path = tmp_path / "data" / "cache" / "recommend_metrics.jsonl"
    sink = JsonlRecommendMetrics(path)
    assert isinstance(sink, RecommendMetricsPort)
    sink.record(_row())
    sink.record(_row(skipped_reason="parse_failed"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert tuple(first) == FIELDS
    assert first["provider"] == "gemini" and first["calls"] == 2 and first["retry_used"] is True
    assert first["mode"] == "more" and first["seconds"] == 3.46 and first["skipped_reason"] is None
    # 응답 시간 파일과 같은 모양 — 지역 시각 + 오프셋, 초 단위
    ts = datetime.fromisoformat(first["ts"])
    assert ts.utcoffset() is not None and ts.microsecond == 0
    assert json.loads(lines[1])["skipped_reason"] == "parse_failed"


def test_file_is_600_and_folder_is_700(tmp_path):
    path = tmp_path / "cache" / "recommend_metrics.jsonl"
    JsonlRecommendMetrics(path).record(_row())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_rotates_to_dot_one_when_over_the_size_cap(tmp_path):
    path = tmp_path / "recommend_metrics.jsonl"
    sink = JsonlRecommendMetrics(path, max_bytes=360)  # 한 줄 약 300바이트(2026-11-05 갈래 칸 추가)
    sink.record(_row())
    sink.record(_row())  # 첫 줄만으로는 360 미만 → 같은 파일
    assert len(path.read_text().splitlines()) == 2
    sink.record(_row())  # 360 이상 → .1 로 옮기고 새 파일
    old = path.with_name("recommend_metrics.jsonl.1")
    assert len(old.read_text().splitlines()) == 2 and len(path.read_text().splitlines()) == 1
    sink.record(_row())
    sink.record(_row())  # 다시 넘으면 옛 .1 을 덮는다 — 파일은 많아야 둘
    assert len(old.read_text().splitlines()) == 2 and len(path.read_text().splitlines()) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "recommend_metrics.jsonl",
        "recommend_metrics.jsonl.1",
    ]
    assert MAX_BYTES == 5 * 1024 * 1024


def test_write_failure_is_swallowed_with_a_debug_line(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="rra.recommend")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    JsonlRecommendMetrics(blocker / "recommend_metrics.jsonl").record(_row())  # 폴더 자리에 파일
    (rec,) = [r for r in caplog.records if r.getMessage().startswith("recommend.metrics_failed")]
    assert rec.levelno == logging.DEBUG and str(tmp_path) not in rec.getMessage()


def test_symlinked_file_is_not_followed(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="rra.recommend")
    target = tmp_path / "elsewhere.txt"
    target.write_text("")
    path = tmp_path / "recommend_metrics.jsonl"
    path.symlink_to(target)
    JsonlRecommendMetrics(path).record(_row())
    assert target.read_text() == ""


def test_unknown_keys_are_refused(tmp_path):
    sink = JsonlRecommendMetrics(tmp_path / "m.jsonl")
    with pytest.raises(ValueError, match="title"):
        sink.record({**_row(), "title": "가제"})
    assert not (tmp_path / "m.jsonl").exists()
