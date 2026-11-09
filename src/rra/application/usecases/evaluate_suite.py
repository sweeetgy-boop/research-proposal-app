"""suite 실행 (ADR 0058, 계약 docs/contracts/eval-results.md §4) — 문제 묶음 → EvalResult.

흐름(문제마다, repeats 회): ② `precheck.run(req, ai=True)`(검색 → 규칙 판정 → AI 같음 판정; 메모를
읽지 않으므로 반복마다 새로 판정 — AI 흔들림을 잰다) → 선택 없음 기준 `effective_blocking`·
`recommend_mode` → (L1) 과제안 `recommender(req, alerts)` → `ProblemOutcome`(숫자만). 지표·ci95 는
`domain/rules/eval_metrics.compute_metrics`.

LLM: 외부 호출 수는 판정(JudgmentInfo.calls) + 과제안(RecommendationResult.calls) 합에서 캐시 재생
적중(L0)을 뺀 값. 예산 초과·실패는 판정·과제안 유스케이스가 로컬·규칙으로 내려가므로 여기서는
세지만 않는다 — `notes` 에 캐시 미스·예산 소진을 적는다.

L2: 기존 `rra eval`(usecases/evaluate, 골든셋 + 초안)의 결과 dict 를 `l2_from_quality` 로
EvalResult 에
담고 사람 확인 표본(run id 만) 10% 를 뽑는다.
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from rra.application.ports.eval_store import ReplayCountsPort
from rra.application.usecases.similar_rows import recommend_mode
from rra.domain.models.eval_problem import EvalProblem
from rra.domain.models.eval_result import EvalMetrics, EvalResult, ProblemRecord
from rra.domain.models.novel import BASIS_ESTIMATED, MODE_NOVEL
from rra.domain.rules.eval_metrics import (
    ProblemOutcome,
    compute_metrics,
    count_kinds,
    percentile,
    problem_records,
)
from rra.domain.rules.eval_problems import answer_hit
from rra.domain.rules.similar_choice import effective_blocking

logger = logging.getLogger("rra.eval")
NO_CHOICES: dict[str, str] = {}
Progress = Callable[[str], None]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class EvaluateSuite:
    def __init__(
        self,
        precheck: Any,
        *,
        suite: str,
        seed: int,
        repeats: int = 1,
        label: str = "",
        commit: str = "",
        sealed: bool = False,
        config_flags: Mapping[str, bool | int | float | str] | None = None,
        recommender: Any | None = None,
        replay: ReplayCountsPort | None = None,
        budget_exhausted: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        progress: Progress | None = None,
    ):
        self.precheck = precheck
        self.suite, self.seed, self.repeats = suite, seed, max(1, int(repeats))
        self.label, self.commit, self.sealed = label, commit, sealed
        self.config_flags = dict(config_flags or {})
        self.recommender = recommender
        self.replay = replay
        self.budget_exhausted = budget_exhausted
        self._clock = clock
        self._progress = progress

    async def __call__(self, problems: Sequence[EvalProblem]) -> EvalResult:
        started_at = _now_iso()
        t0 = self._clock()
        outcomes: list[list[ProblemOutcome]] = []
        for i, problem in enumerate(problems):
            runs = [await self.one(problem) for _ in range(self.repeats)]
            outcomes.append(runs)
            if self._progress is not None:
                self._progress(f"{i + 1}/{len(problems)} {problem.kind}")
        metrics, ci, notes = compute_metrics(outcomes, repeats=self.repeats, seed=self.seed)
        calls = sum(r.llm_calls for runs in outcomes for r in runs)
        hits = self.replay.hits if self.replay is not None else 0
        # 캐시 미스 중 안쪽 LLM 을 실제로 부른 것(녹화)만 외부 호출 — 그냥 실패한 미스는 호출이
        # 아니다
        dry_misses = (
            max(0, self.replay.misses - self.replay.recorded) if self.replay is not None else 0
        )
        if self.replay is not None:
            notes.append(
                f"캐시 재생 적중 {self.replay.hits}건 · 미스 {self.replay.misses}건(규칙 판정)"
            )
        if self.budget_exhausted is not None and self.budget_exhausted():
            notes.append("평가용 Gemini 일일 상한 소진 — 이후 문제는 로컬·규칙 판정")
        kinds = count_kinds(outcomes)
        notes.append(
            "문제 종류: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
            if kinds
            else "문제 0건"
        )
        return EvalResult(
            suite=self.suite,  # type: ignore[arg-type]
            seed=self.seed,
            n=len(problems),
            repeats=self.repeats,
            metrics=metrics,
            ci95=ci,
            config_flags=self.config_flags,
            label=self.label,
            commit=self.commit,
            started_at=started_at,
            seconds=round(self._clock() - t0, 1),
            sealed=self.sealed,
            llm_calls=max(0, calls - hits - dry_misses),
            cache_hits=hits,
            notes=notes,
            # 문제별 요약(id 해시·종류·맞힘·반복) — 짝 비교(McNemar)·갈린 문제 재측정용
            problems=[
                ProblemRecord(**rec)  # type: ignore[arg-type]
                for rec in problem_records([p.id for p in problems], outcomes)
            ],
        )

    async def one(self, problem: EvalProblem) -> ProblemOutcome:
        req = problem.to_request()
        t0 = self._clock()
        result = await self.precheck.run(req, ai=True)
        alerts = list(result.alerts)
        calls = int(getattr(result.judgment, "calls", 0) or 0)
        blocked = effective_blocking(alerts, NO_CHOICES)
        mode = recommend_mode(alerts, NO_CHOICES)
        rec_zero: bool | None = None
        barriers = estimated = 0
        if self.recommender is not None:
            try:
                rec = await self.recommender(req, alerts)
            except Exception as exc:  # 과제안 실패는 측정을 멈추지 않는다 — 0건으로 센다
                logger.warning(
                    "eval.recommend_failed kind=%s err=%s", problem.kind, type(exc).__name__
                )
                rec_zero = True
            else:
                calls += int(rec.calls)
                if rec.mode == MODE_NOVEL:
                    rec_zero = not rec.novel
                    for item in rec.novel:
                        for b in item.barriers:
                            barriers += 1
                            estimated += int(b.basis.level == BASIS_ESTIMATED)
                else:
                    rec_zero = not rec.recommendations
        seconds = self._clock() - t0
        rows = [[a.doc_id, *a.merged_ids] for a in alerts]
        return ProblemOutcome(
            kind=problem.kind,
            seconds=round(seconds, 3),
            hit=answer_hit(problem.answers, rows) if problem.kind == "reverse" else None,
            blocked=blocked,
            novel=(mode == MODE_NOVEL) if problem.kind == "novel" else None,
            rec_zero=rec_zero,
            barriers_total=barriers,
            barriers_estimated=estimated,
            llm_calls=calls,
        )


def l2_from_quality(
    data: Mapping[str, Any],
    *,
    seed: int,
    sample_ratio: float = 0.1,
    label: str = "",
    commit: str = "",
    config_flags: Mapping[str, bool | int | float | str] | None = None,
) -> tuple[EvalResult, list[str]]:
    """기존 `rra eval` 결과(usecases/evaluate.EvalResult.to_dict()) → L2 EvalResult + 사람 확인
    표본 run id. recall_at5 = precheck 적중/정답 있는 아이디어, 지연 = ② precheck 초."""
    ideas = list(data.get("ideas") or [])
    known = [i for i in ideas if i.get("precheck_hit") is not None]
    hits = sum(1 for i in known if i.get("precheck_hit"))
    seconds = [float(i["precheck_seconds"]) for i in ideas if i.get("precheck_seconds") is not None]
    totals = data.get("totals") or {}
    metrics = EvalMetrics(
        recall_at5=round(hits / len(known), 4) if known else None,
        latency_p50=percentile(seconds, 50),
        latency_p90=percentile(seconds, 90),
    )
    notes = [
        f"골든셋 {len(ideas)}건 · 유효 초안 {totals.get('valid', 0)}/{len(ideas)} · "
        f"Gemini {data.get('gemini_calls', 0)}회",
        "L2 는 기존 rra eval 흐름(초안까지)을 감쌈 — 정답 있는 아이디어만 recall_at5 분모",
    ]
    rng = random.Random(seed)  # noqa: S311 — 표본 추출
    ids = [str(i.get("run_id") or "") for i in ideas if i.get("run_id")]
    size = min(len(ids), math.ceil(len(ids) * sample_ratio)) if ids else 0
    sample = sorted(rng.sample(ids, size)) if size else []
    result = EvalResult(
        suite="l2",
        seed=seed,
        n=len(ideas),
        repeats=1,
        metrics=metrics,
        ci95={},
        config_flags=dict(config_flags or {}),
        label=label or str(data.get("label") or ""),
        commit=commit,
        started_at=str(data.get("started_at") or ""),
        seconds=float(data.get("total_seconds") or 0.0),
        sealed=False,
        llm_calls=int(data.get("gemini_calls") or 0),
        cache_hits=0,
        notes=notes,
    )
    return result, sample


__all__ = ["EvaluateSuite", "l2_from_quality"]
