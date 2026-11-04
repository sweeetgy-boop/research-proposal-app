"""차별화 과제안 측정 줄 (ADR 0055 덧붙임) — 유스케이스 + 가짜 기록기, 규칙, 조립.

한 번 = 한 줄·정확한 칸, '새 영역' 다시 받기(retry_used·calls), [더 만들기](mode=more),
건너뜀도 한 줄, 기록기 실패가 추천을 막지 않음, 칸 형식(문자열은 열거 칸 셋뿐),
조립(가짜 모드 None·데이터 폴더 경로).
"""

from __future__ import annotations

import logging

from pydantic import SecretStr

from rra.application.ports import RecommendMetricsPort
from rra.application.usecases.recommend_projects import SKIP_NO_INPUT
from rra.domain.models import ProposalRequest, RecommendationResult
from rra.domain.rules.recommend_metrics import (
    ENUM_FIELDS,
    FIELDS,
    ROW_FIELDS,
    enum_value,
    metrics_row,
)
from tests.application.test_recommend_projects import ALERTS, REQ, make, rec, reply

BOOL_FIELDS = {"fallback_local", "retry_used", "regenerated"}
INT_FIELDS = {"calls", "cards", "discarded", "references", "similar"}


class MemoryMetrics:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, row) -> None:
        self.rows.append(dict(row))


class BrokenMetrics:
    def record(self, row) -> None:
        raise OSError("disk full")


class ExplodingMetrics:
    def record(self, row) -> None:
        raise RuntimeError("unexpected")


def _assert_shape(row: dict) -> None:
    """칸 집합·값 형식 — 문자열은 열거 칸(provider·skipped_reason·mode)뿐."""
    assert tuple(row) == ROW_FIELDS
    for key, value in row.items():
        if key in BOOL_FIELDS:
            assert type(value) is bool, key
        elif key in INT_FIELDS:
            assert type(value) is int and value >= 0, key
        elif key == "seconds":
            assert type(value) is float and value >= 0, key
        else:
            assert key in ENUM_FIELDS, key
            assert value is None or (type(value) is str and enum_value(value) == value), key
    assert row["mode"] in ("initial", "more")


def test_port_is_runtime_checkable():
    assert isinstance(MemoryMetrics(), RecommendMetricsPort)
    assert not isinstance(object(), RecommendMetricsPort)


async def test_one_run_records_one_line_with_exact_keys():
    uc, _, _ = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])])
    uc.metrics = MemoryMetrics()
    out = await uc(REQ, ALERTS)
    assert len(out.recommendations) == 1
    (row,) = uc.metrics.rows
    _assert_shape(row)
    assert {k: v for k, v in row.items() if k != "seconds"} == {
        "provider": "gemini",
        "fallback_local": False,
        "calls": 1,
        "cards": 1,
        "discarded": 0,
        "retry_used": False,
        "regenerated": False,
        "skipped_reason": None,
        "references": 0,
        "similar": 0,
        "mode": "initial",
    }


async def test_new_area_retry_records_retry_used_and_both_calls():
    uc, _, _ = make([reply([], reason="이미 충분히 다름"), reply([rec("새 영역 과제 하나")])])
    uc.metrics = MemoryMetrics()
    out = await uc(REQ, ALERTS)
    assert out.retry_used is True
    (row,) = uc.metrics.rows
    _assert_shape(row)
    assert row["retry_used"] is True and row["calls"] == 2 and row["cards"] == 1
    assert row["regenerated"] is False  # 첫 응답에 제외가 없었다


async def test_similar_rows_count_comes_from_chosen_rows():
    judged = [ALERTS[0].model_copy(update={"judgment": "partial", "judged_by": "argon"}), ALERTS[1]]
    uc, _, _ = make([reply([], reason="이미 충분히 다름")])
    uc.metrics = MemoryMetrics()
    await uc(REQ, judged)
    (row,) = uc.metrics.rows
    assert row["similar"] == 1 and row["retry_used"] is False and row["calls"] == 1


async def test_more_mode_when_cards_were_already_shown():
    uc, _, _ = make(
        [
            reply([rec("운행 차량 가속도 기반 진행 속도 추정")]),
            reply([rec("분기기 구간 전용 감지", summary="분기기 구간만 봄")]),
        ]
    )
    uc.metrics = MemoryMetrics()
    first = await uc(REQ, ALERTS)
    await uc(REQ, ALERTS, similar_only=True, shown=first.recommendations)
    assert [r["mode"] for r in uc.metrics.rows] == ["initial", "more"]
    for row in uc.metrics.rows:
        _assert_shape(row)


async def test_skipped_run_also_records_a_line():
    uc, llm, _ = make([], chunks=[])
    uc.metrics = MemoryMetrics()
    out = await uc(REQ, [])
    assert out.skipped_reason == SKIP_NO_INPUT and llm.calls == []
    (row,) = uc.metrics.rows
    _assert_shape(row)
    assert row["skipped_reason"] == SKIP_NO_INPUT and row["calls"] == 0 and row["cards"] == 0


async def test_failing_writer_never_breaks_the_recommendation(caplog):
    caplog.set_level(logging.DEBUG, logger="rra.recommend")
    for writer in (BrokenMetrics(), ExplodingMetrics()):
        uc, _, _ = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])])
        uc.metrics = writer
        out = await uc(REQ, ALERTS)
        assert len(out.recommendations) == 1
    failed = [r for r in caplog.records if r.getMessage().startswith("recommend.metrics_failed")]
    assert [r.getMessage() for r in failed] == [
        "recommend.metrics_failed kind=OSError",
        "recommend.metrics_failed kind=RuntimeError",
    ]
    assert all(r.levelno == logging.DEBUG for r in failed)
    assert "disk full" not in caplog.text and "unexpected" not in caplog.text


async def test_no_metrics_is_a_no_op():
    uc, _, _ = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])])
    assert uc.metrics is None
    assert len((await uc(REQ, ALERTS)).recommendations) == 1


async def test_line_carries_no_titles_text_or_ids():
    """본문·가제·doc_id·입력 글이 어느 칸에도 없다 — 문자열은 열거 칸 셋뿐."""
    req = ProposalRequest(**{**REQ.model_dump(), "reference_ids": ["openalex:W1"]})
    uc, _, _ = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])])
    uc.metrics = MemoryMetrics()
    await uc(req, ALERTS)
    (row,) = uc.metrics.rows
    _assert_shape(row)
    assert row["references"] == 1
    text = repr(row)
    for needle in ("운행 차량", "경부선", "own:1", "openalex", "alio", "궤도"):
        assert needle not in text


def test_metrics_row_sanitizes_enums_and_clamps():
    result = RecommendationResult(provider="gemini 2 <x>", skipped_reason="한글", calls=3)
    row = metrics_row(result, mode="weird", similar=-1, seconds=-0.5)
    assert row["provider"] is None and row["skipped_reason"] is None
    assert row["mode"] == "initial" and row["similar"] == 0 and row["seconds"] == 0.0
    assert FIELDS == ("ts", *ROW_FIELDS)


# ── 조립 ─────────────────────────────────────────────
def test_build_recommender_wires_file_metrics_under_data_dir(tmp_path):
    from rra.adapters.logging.recommend_metrics import JsonlRecommendMetrics
    from rra.composition import build_recommend_metrics, build_recommender
    from tests.entrypoints.ui.fake_app import make_assistant
    from tests.test_composition import project_settings

    settings = project_settings(gemini_api_key=SecretStr("k"), data_dir=tmp_path / "data")
    uc = build_recommender(settings, repo=make_assistant().repo, llm=object())
    assert isinstance(uc.metrics, JsonlRecommendMetrics)
    assert uc.metrics.path == (tmp_path / "data" / "cache" / "recommend_metrics.jsonl").resolve()
    assert not uc.metrics.path.exists()  # 만들 때는 파일을 건드리지 않는다
    fake = project_settings(fake_llm=True, data_dir=tmp_path / "data")
    assert build_recommend_metrics(fake) is None
