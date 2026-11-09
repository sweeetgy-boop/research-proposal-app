"""평가 결과 표시 — `rra eval compare` 의 한국어 비교표(Markdown)와 한 줄 요약 (ADR 0058, 레인 D).

규칙은 domain/rules/eval_compare 에 있고 여기는 글자 배치만 한다. 수치만 다룬다(문제 본문 없음).
"""

from __future__ import annotations

from collections.abc import Sequence

from rra.domain.models.eval_result import CI95, EvalResult
from rra.domain.rules.eval_compare import CompareRow, column_labels, compare


def fmt_value(value: float | None, ci: CI95 | None = None) -> str:
    if value is None:
        return "—"
    text = f"{value:.3f}"
    if ci is not None and ci.low is not None and ci.high is not None:
        text += f" [{ci.low:.3f}, {ci.high:.3f}]"
    return text


def fmt_diff(diff: float | None) -> str:
    if diff is None:
        return "—"
    return f"{diff:+.3f}"


def compare_markdown(results: Sequence[EvalResult], *, date: str) -> str:
    """지표별 열 비교표 — 값 [ci95] · 기준 대비 차이 · 판정(구간 겹침이면 '차이 없음')."""
    labels = column_labels(results)
    rows = compare(results)
    head = ["지표", *labels]
    for lab in labels[1:]:
        head += [f"차이({lab})", f"판정({lab})"]
    lines = [
        f"# 평가 비교 — {date} (ADR 0058)",
        "",
        "기준 열은 첫 결과(" + labels[0] + "). 값 뒤 괄호는 95% 신뢰구간(반복 ≥ 2 일 때만). "
        "구간이 겹치면 '차이 없음', 구간이 없으면 차이 값만 본다.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    for row in rows:
        lines.append(_row_line(row))
    lines += [
        "",
        "## 실행 정보",
        "",
        "| 열 | suite | seed | n | repeats | 봉인 | 커밋 | LLM 호출 | 캐시 적중 | 초 | 스위치 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lab, r in zip(labels, results, strict=True):
        flags = ", ".join(f"{k}={v}" for k, v in sorted(r.config_flags.items()))
        lines.append(
            f"| {lab} | {r.suite} | {r.seed} | {r.n} | {r.repeats} | "
            f"{'예' if r.sealed else '아니오'} | "
            f"{r.commit or '—'} | {r.llm_calls} | {r.cache_hits} | {r.seconds:g} | {flags} |"
        )
    notes = [(lab, n) for lab, r in zip(labels, results, strict=True) for n in r.notes]
    if notes:
        lines += ["", "## 메모", ""]
        lines += [f"- {lab}: {n}" for lab, n in notes]
    return "\n".join(lines) + "\n"


def _row_line(row: CompareRow) -> str:
    cells = [row.label, *(fmt_value(v, c) for v, c in zip(row.values, row.cis, strict=True))]
    for d, v in zip(row.diffs[1:], row.verdicts[1:], strict=True):
        cells += [fmt_diff(d), v]
    return "| " + " | ".join(cells) + " |"


def summary_line(result: EvalResult) -> str:
    m = result.metrics
    parts = [
        f"[{result.suite}{' ' + result.label if result.label else ''}] "
        f"n={result.n} × {result.repeats}회"
    ]
    for key, name in (
        ("recall_at5", "recall@5"),
        ("false_block", "false_block"),
        ("novel_rate", "novel"),
        ("rec_zero_rate", "과제안 0건"),
    ):
        value = getattr(m, key)
        if value is not None:
            parts.append(f"{name} {fmt_value(value, result.ci95.get(key))}")
    if m.latency_p50 is not None:
        parts.append(f"지연 p50 {m.latency_p50:g}s · p90 {m.latency_p90:g}s")
    parts.append(f"LLM {result.llm_calls}회 · 캐시 {result.cache_hits} · {result.seconds:g}s")
    return " — ".join(parts[:1] + [" · ".join(parts[1:])])
