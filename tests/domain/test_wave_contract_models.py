"""0단계 계약 모델 (2026-11-09, ADR 0058·0059) — facets·eval_result 는 순수 pydantic, 비신뢰 입력에
안전해야 한다."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rra.domain.models.eval_result import METRIC_KEYS, SUITES, EvalMetrics, EvalResult
from rra.domain.models.facets import FACET_KEYS, FacetOverlap, Facets


def test_facets_clean_one_line_and_cap() -> None:
    f = Facets(target="  철도역사\n승강장  캐노피 ", problem="가" * 200, method=None, place=123)  # type: ignore[arg-type]
    assert f.target == "철도역사 승강장 캐노피"
    assert len(f.problem) == 80
    assert f.method == "" and f.place == ""
    assert f.source == "none"
    assert not f.is_empty()
    assert tuple(f.as_dict()) == FACET_KEYS
    assert Facets().is_empty()


def test_facet_overlap_from_untrusted_mapping() -> None:
    o = FacetOverlap.from_mapping(
        {"target": 2, "problem": "2", "method": 7, "place": True, "extra": 2}
    )
    assert o.as_dict() == {"target": 2, "problem": 0, "method": 0, "place": 1}
    assert o.total() == 3
    assert not o.all_high()
    assert FacetOverlap.from_mapping("junk").total() == 0
    assert FacetOverlap(target=2, problem=2, method=2, place=2).all_high()
    with pytest.raises(ValidationError):
        FacetOverlap(target=3)  # type: ignore[arg-type]


def test_eval_result_shape_matches_contract() -> None:
    assert SUITES == ("l0", "l1", "l2")
    assert set(METRIC_KEYS) == set(EvalMetrics.model_fields)
    r = EvalResult(
        suite="l1",
        seed=20261109,
        n=120,
        repeats=3,
        metrics=EvalMetrics(recall_at5=0.87, false_block=0.05),
        ci95={"recall_at5": {"low": 0.81, "high": 0.92}},  # type: ignore[dict-item]
        config_flags={"facets.enabled": False, "rerank.threshold": 0.5},
        label="가-main",
    )
    dumped = r.model_dump()
    assert dumped["ci95"]["recall_at5"] == {"low": 0.81, "high": 0.92}
    assert dumped["metrics"]["novel_rate"] is None
    assert dumped["sealed"] is False
    with pytest.raises(ValidationError):
        EvalResult(suite="l9", seed=1, n=0)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EvalResult(suite="l0", seed=1, n=-1)
    with pytest.raises(ValidationError):  # 경로·본문이 들어갈 수 있는 복합값은 거부 — 스칼라만
        EvalResult(suite="l0", seed=1, n=1, config_flags={"x": ["a"]})  # type: ignore[dict-item]
