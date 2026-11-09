"""짝 비교 (2026-11-09 사용자 보완) — 문제별 맞힘 요약·McNemar 정확 검정·갈린 문제 id. 순수 함수."""

from __future__ import annotations

from rra.domain.models.eval_result import EvalResult, ProblemRecord
from rra.domain.rules.eval_compare import VERDICT_BETTER, VERDICT_SAME, mcnemar_exact, paired
from rra.domain.rules.eval_metrics import (
    ProblemOutcome,
    outcome_correct,
    problem_records,
    record_id,
)


def _o(kind, **kw):
    return ProblemOutcome(kind=kind, seconds=1.0, **kw)


def test_outcome_correct_by_kind() -> None:
    assert outcome_correct(_o("reverse", hit=True)) is True
    assert outcome_correct(_o("reverse", hit=False)) is False
    assert outcome_correct(_o("trap", blocked=True)) is False
    assert outcome_correct(_o("trap", blocked=False)) is True
    assert outcome_correct(_o("novel", novel=True)) is True
    assert outcome_correct(_o("novel", novel=True, blocked=True)) is False
    assert outcome_correct(_o("novel")) is None


def test_problem_records_majority_over_repeats() -> None:
    recs = problem_records(
        ["p1", "p2"],
        [
            [_o("reverse", hit=True), _o("reverse", hit=False), _o("reverse", hit=True)],
            [_o("trap", blocked=True)],
        ],
    )
    assert recs[0]["id"] == record_id("p1") and len(recs[0]["id"]) == 16  # 원 id 그대로 적지 않는다
    assert recs[0]["correct"] is True and recs[0]["correct_runs"] == 2 and recs[0]["runs"] == 3
    assert recs[1]["correct"] is False and recs[1]["blocked"] is True
    for r in recs:  # 본문·doc_id 없음 — 숫자·참거짓·id 해시만
        assert set(r) == {"id", "kind", "correct", "runs", "correct_runs", "blocked", "seconds"}


def test_mcnemar_exact_two_sided() -> None:
    assert mcnemar_exact(0, 0) is None
    assert mcnemar_exact(3, 3) == 1.0
    assert mcnemar_exact(0, 6) == 0.0312  # 2 * (1/64)
    assert mcnemar_exact(1, 9) == 0.0215


def _result(label, records):
    return EvalResult(
        suite="l1",
        seed=7,
        n=len(records),
        label=label,
        problems=[ProblemRecord(**r) for r in records],
    )


def test_paired_counts_and_discordant_ids() -> None:
    a = _result(
        "가",
        [
            {"id": "p1", "kind": "reverse", "correct": True},
            {"id": "p2", "kind": "reverse", "correct": False},
            {"id": "p3", "kind": "trap", "correct": True},
            {"id": "p4", "kind": "novel", "correct": False},
            {"id": "p9", "kind": "reverse", "correct": True},  # 비교 쪽에 없음 — 제외
        ],
    )
    b = _result(
        "다",
        [
            {"id": "p1", "kind": "reverse", "correct": True},
            {"id": "p2", "kind": "reverse", "correct": True},
            {"id": "p3", "kind": "trap", "correct": False},
            {"id": "p4", "kind": "novel", "correct": True},
        ],
    )
    st = paired(a, b)
    assert st is not None
    assert (st.n_common, st.both_correct, st.a_only, st.b_only, st.both_wrong) == (4, 1, 1, 2, 0)
    assert st.discordant_ids == ("p2", "p3", "p4")
    assert st.by_kind["reverse"] == (1, 0, 1, 0) and st.by_kind["trap"] == (0, 1, 0, 0)
    assert st.mcnemar_p == 1.0 and st.verdict == VERDICT_SAME
    assert paired(a, _result("x", [{"id": "zz", "kind": "trap", "correct": True}])) is None


def test_paired_verdict_better_when_significant() -> None:
    recs_a = [{"id": f"p{i}", "kind": "trap", "correct": False} for i in range(8)]
    recs_b = [{"id": f"p{i}", "kind": "trap", "correct": True} for i in range(8)]
    st = paired(_result("가", recs_a), _result("다", recs_b))
    assert st is not None and st.b_only == 8 and st.mcnemar_p == 0.0078
    assert st.verdict == VERDICT_BETTER
