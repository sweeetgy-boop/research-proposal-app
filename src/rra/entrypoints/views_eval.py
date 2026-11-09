"""평가 결과 표시 — `rra eval compare` 의 한국어 비교표(Markdown)와 한 줄 요약 (ADR 0058, 레인 D).

규칙은 domain/rules/eval_compare 에 있고 여기는 글자 배치만 한다. 수치만 다룬다(문제 본문 없음).
"""

from __future__ import annotations

from collections.abc import Sequence

from rra.domain.models.eval_result import CI95, EvalResult
from rra.domain.rules.eval_compare import CompareRow, column_labels, compare, paired


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
    paired_lines = _paired_section(results, labels)
    if paired_lines:
        lines += ["", *paired_lines]
    notes = [(lab, n) for lab, r in zip(labels, results, strict=True) for n in r.notes]
    if notes:
        lines += ["", "## 메모", ""]
        lines += [f"- {lab}: {n}" for lab, n in notes]
    return "\n".join(lines) + "\n"


KIND_LABELS = {"reverse": "역방향", "trap": "함정", "novel": "새 영역"}


def _paired_section(results: Sequence[EvalResult], labels: Sequence[str]) -> list[str]:
    """같은 문제 묶음을 돌린 열끼리 문제별 맞힘 대조 + McNemar(정확 이항, 양측). 공통 문제가
    없으면 빈 목록(절을 내지 않는다). 2026-11-09 사용자 보완."""
    base = results[0]
    out: list[str] = []
    for lab, other in zip(labels[1:], results[1:], strict=True):
        st = paired(base, other)
        if st is None:
            continue
        if not out:
            out += [
                "## 짝 비교 (같은 문제, 문제별 맞힘 대조)",
                "",
                "기준 열과 같은 문제 id 를 가진 열만. '기준만'·'비교만' 은 두 구성의 결과가 갈린 "
                "문제 수, McNemar p 는 그 둘의 정확 이항 검정(양측). p < 0.05 면 갈린 쪽이 많은 "
                "구성을 개선/악화로, 아니면 '차이 없음'. 갈린 문제만 3회 반복해 다시 재는 것이 "
                "다음 단계다.",
                "",
            ]
        out += [
            f"### {labels[0]} vs {lab}",
            "",
            "| 종류 | 공통 | 둘 다 맞힘 | 기준만 | 비교만 | 둘 다 틀림 | McNemar p | 판정 |",
            "|---|---|---|---|---|---|---|---|",
            _paired_row(
                "전체",
                st.n_common,
                st.both_correct,
                st.a_only,
                st.b_only,
                st.both_wrong,
                st.mcnemar_p,
                st.verdict,
            ),
        ]
        for kind, (both, a_only, b_only, wrong) in st.by_kind.items():
            out.append(
                _paired_row(
                    KIND_LABELS.get(kind, kind),
                    both + a_only + b_only + wrong,
                    both,
                    a_only,
                    b_only,
                    wrong,
                    None,
                    "",
                )
            )
        out.append("")
        out.append(f"갈린 문제 {len(st.discordant_ids)}건 (id 는 `--discordant-out` 으로 저장)")
        out.append("")
    return out


def _paired_row(
    name: str, n: int, both: int, a: int, b: int, wrong: int, p: float | None, verdict: str
) -> str:
    p_txt = "—" if p is None else f"{p:.4f}"
    return f"| {name} | {n} | {both} | {a} | {b} | {wrong} | {p_txt} | {verdict} |"


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
