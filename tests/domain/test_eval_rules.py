"""평가 규칙(ADR 0058) — 문제 만들기·지표·ci95·비교·실사용 지표. 순수 함수만."""

from __future__ import annotations

from rra.domain.models import Document
from rra.domain.models.eval_problem import EvalProblem, NovelTopic, ProblemMix
from rra.domain.models.eval_result import CI95, EvalMetrics, EvalResult
from rra.domain.rules.eval_compare import (
    VERDICT_BETTER,
    VERDICT_NO_CI,
    VERDICT_SAME,
    VERDICT_WORSE,
    compare,
    gate,
)
from rra.domain.rules.eval_metrics import (
    ProblemOutcome,
    bootstrap_ci95,
    compute_metrics,
    percentile,
)
from rra.domain.rules.eval_problems import (
    answer_hit,
    novel_problem,
    reverse_problem,
    split_slots,
    strip_tokens,
    title_stems,
    trap_problem,
)
from rra.domain.rules.eval_usage import choice_usage, recommend_usage
from rra.domain.rules.keywords import KeywordRule

RULE = KeywordRule()
TEXT_A = (
    "일반철도 구간의 궤도틀림은 궤도검측차가 분기마다 측정한다. "
    "측정 주기 사이의 급격한 틀림 진행은 점검원이 도보로 확인해야 알 수 있다. "
    "영업 차량 대차에 가속도 센서를 달아 진동 신호에서 틀림 징후를 추출한다. "
    "진행 속도를 추정해 보수 우선순위 목록을 만든다."
)
TEXT_B = (
    "대형 역 주차장은 만차 여부를 입구 전광판으로만 안내한다. "
    "이용자가 빈자리를 찾아 주차장을 돌며 혼잡이 커진다. "
    "주차면 센서로 빈자리를 세어 앱으로 안내한다. 시간대별 혼잡을 예측해 요금 할인 시간을 정한다."
)


def doc(doc_id: str, title: str, text: str, source: str = "own") -> Document:
    return Document(
        doc_id=doc_id, source=source, doc_type="rnd_project", title=title, abstract=text
    )


# ── 문제 만들기 ─────────────────────────────────────────
def test_reverse_problem_removes_title_tokens_and_keeps_answer():
    d = doc("own:1", "차상 가속도 센서 기반 궤도틀림 상시 감지", TEXT_A)
    stems = title_stems(d.title, RULE)
    assert "가속" in stems and "궤도틀림" in stems and "기반" not in stems  # 조사 제거·일반어 제외
    p = reverse_problem(d, RULE, min_chars=50)
    assert p is not None and p.kind == "reverse" and p.answers == ["own:1"]
    body = " ".join(p.request.values())
    assert "가속도" not in body and "궤도틀림은" not in body and p.request["title_hint"] == ""
    assert all(p.request[k] for k in ("current_state", "root_cause", "limitation", "goal"))
    assert p.to_request().goal  # ProposalRequest 로 읽힌다


def test_reverse_problem_skips_short_text():
    assert reverse_problem(doc("own:2", "짧은 과제", "한 줄."), RULE, min_chars=50) is None


def test_strip_tokens_prefix_match_like_keyword_overlap():
    assert strip_tokens("자산개발을 위한 자산개발사업 추진", ["자산개발"]) == "위한 추진"


def test_split_slots_distributes_sentences_or_words():
    assert split_slots(["a", "b", "c", "d", "e"], 4) == ["a", "b", "c", "d e"]
    assert split_slots(["하나 둘 셋 넷 다섯 여섯"], 4) == ["하나", "둘 셋", "넷", "다섯 여섯"]
    assert split_slots([], 4) == ["", "", "", ""]


def test_trap_problem_mixes_a_target_with_b_method_and_rejects_same_topic():
    a = doc("own:a", "궤도틀림 상시 감지", TEXT_A)
    b = doc("alio:b", "역 주차장 혼잡 안내", TEXT_B, source="alio")
    p = trap_problem(a, b, RULE, min_chars=50)
    assert p is not None and p.kind == "trap" and p.answers == ["own:a", "alio:b"]
    assert "궤도검측차가" in p.request["current_state"]  # A 의 앞 절반
    assert "앱으로" in p.request["limitation"] or "앱으로" in p.request["goal"]  # B 의 뒤 절반
    assert (
        trap_problem(a, doc("ntis:a2", "궤도틀림 감지 2단계", TEXT_A, "ntis"), RULE, min_chars=50)
        is None
    )


def test_novel_problem_and_mix_counts():
    topic = NovelTopic(title_hint="t", current_state="c", root_cause="r", limitation="l", goal="g")
    p = novel_problem(topic)
    assert p.kind == "novel" and p.answers == [] and p.request["goal"] == "g"
    assert ProblemMix().counts(120) == {"reverse": 72, "trap": 30, "novel": 18}
    assert sum(ProblemMix().counts(7).values()) == 7


def test_answer_hit_counts_merged_rows_within_top5():
    rows = [["x"], ["y", "own:1"], ["z"], ["w"], ["v"], ["own:2"]]
    assert answer_hit(["own:1"], rows) and not answer_hit(["own:2"], rows)


# ── 지표·ci95 ──────────────────────────────────────────
def test_percentile_and_bootstrap_are_deterministic():
    assert percentile([1, 2, 3, 4], 50) == 2.5 and percentile([5], 90) == 5.0
    a = bootstrap_ci95([0.0, 1.0, 1.0, 0.5, 1.0], seed=7)
    b = bootstrap_ci95([0.0, 1.0, 1.0, 0.5, 1.0], seed=7)
    assert a == b and a.low is not None and a.low <= 0.7 <= a.high
    assert bootstrap_ci95([1.0], seed=1) == CI95()


def _o(kind, **kw):
    return ProblemOutcome(kind=kind, seconds=kw.pop("seconds", 1.0), **kw)


def test_compute_metrics_by_kind_with_repeats():
    outcomes = [
        [_o("reverse", hit=True), _o("reverse", hit=False)],  # 0.5
        [_o("reverse", hit=True), _o("reverse", hit=True)],  # 1.0
        [_o("trap", blocked=True), _o("trap", blocked=False)],  # 0.5
        [
            _o(
                "novel",
                novel=True,
                blocked=True,
                rec_zero=False,
                barriers_total=4,
                barriers_estimated=1,
            )
        ]
        * 2,
    ]
    m, ci, notes = compute_metrics(outcomes, repeats=2, seed=3)
    assert m.recall_at5 == 0.75 and m.false_block == 0.5 and m.novel_rate == 1.0
    assert m.reverse_block is not None  # 역방향 차단율 (2026-11-09, idf 켬 판단 기준)
    assert m.novel_estimated_barrier_ratio == 0.25 and m.rec_zero_rate == 0.0
    assert m.latency_p50 == 1.0 and m.latency_p90 == 1.0
    assert "recall_at5" in ci and "false_block" not in ci  # 문제 1개짜리 지표는 구간 없음
    assert any("새 영역 문제 차단 1/1건" in n for n in notes) and any(
        "부트스트랩" in n for n in notes
    )


def test_compute_metrics_without_repeats_has_no_ci():
    m, ci, _ = compute_metrics(
        [[_o("reverse", hit=True)], [_o("reverse", hit=False)]], repeats=1, seed=1
    )
    assert m.recall_at5 == 0.5 and ci == {} and m.novel_rate is None


# ── 비교·게이트 ────────────────────────────────────────
def result(label, **metrics):
    ci = metrics.pop("ci", {})
    return EvalResult(
        suite="l1", seed=1, n=10, repeats=3, metrics=EvalMetrics(**metrics), ci95=ci, label=label
    )


def test_compare_marks_overlap_as_no_difference_and_direction_otherwise():
    a = result(
        "가",
        recall_at5=0.8,
        false_block=0.1,
        ci={"recall_at5": CI95(low=0.7, high=0.9), "false_block": CI95(low=0.05, high=0.15)},
    )
    b = result(
        "나",
        recall_at5=0.85,
        false_block=0.3,
        ci={"recall_at5": CI95(low=0.75, high=0.95), "false_block": CI95(low=0.2, high=0.4)},
    )
    c = result(
        "다",
        recall_at5=0.99,
        false_block=0.0,
        ci={"recall_at5": CI95(low=0.95, high=1.0), "false_block": CI95(low=0.0, high=0.02)},
    )
    rows = {r.metric: r for r in compare([a, b, c])}
    assert rows["recall_at5"].verdicts == ["", VERDICT_SAME, VERDICT_BETTER]
    assert rows["false_block"].verdicts == ["", VERDICT_WORSE, VERDICT_BETTER]
    assert rows["recall_at5"].diffs[1] == 0.05 and rows["novel_rate"].verdicts[1] == "—"


def test_compare_without_ci_says_no_interval_and_gate_thresholds():
    a, b = (
        result("가", recall_at5=0.9, false_block=0.0),
        result("나", recall_at5=0.8, false_block=0.1),
    )
    assert compare([a, b])[0].verdicts[1] == VERDICT_NO_CI
    failures = gate(a, b)
    assert (
        len(failures) == 2 and failures[0].startswith("recall_at5") and "false_block" in failures[1]
    )
    assert gate(a, result("다", recall_at5=0.86, false_block=0.05)) == []


# ── 실사용 지표 ────────────────────────────────────────
def test_usage_counts_only_user_choices_and_skips_test_lines():
    rows = [
        {"source": "user", "choice": "similar", "judgment": "same", "at": "2026-11-05T10:00:00"},
        {"source": "user", "choice": "unrelated", "judgment": "same", "at": "2026-11-06T10:00:00"},
        {"source": "ai_prefill", "choice": "similar", "judgment": "same"},
        {"source": "user", "choice": "similar", "judgment": "same", "test": True},
        {"source": "user", "choice": "unrelated", "at": "2026-11-01T10:00:00"},  # 판정 없음
    ]
    u = choice_usage(rows)
    assert u == {"user_choices": 3, "similar_rate": 0.333, "ai_judged": 2, "ai_agreement": 0.5}
    assert choice_usage(rows, since=__import__("datetime").date(2026, 11, 6))["user_choices"] == 1
    assert choice_usage(rows, include_test=True)["user_choices"] == 4


def test_recommend_usage_by_branch_with_old_rows_as_differentiate():
    rows = [
        {"cards": 3, "seconds": 10.0, "ts": "2026-11-05T10:00:00"},
        {"cards": 0, "seconds": 5.0, "branch": "novel", "fallback_local": True},
        {"cards": 2, "seconds": 7.0, "branch": "novel", "test": True},
    ]
    r = recommend_usage(rows)
    assert r["calls"] == 2
    assert r["by_branch"]["differentiate"] == {
        "calls": 1,
        "zero_rate": 0.0,
        "fallback_local_rate": 0.0,
        "seconds_p50": 10.0,
    }
    assert (
        r["by_branch"]["novel"]["zero_rate"] == 1.0
        and r["by_branch"]["novel"]["fallback_local_rate"] == 1.0
    )


def test_eval_problem_round_trips_through_json():
    p = EvalProblem(id="x", kind="novel", request={"goal": "g", "current_state": "c"})
    assert EvalProblem.model_validate(p.model_dump()) == p
