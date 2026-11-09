"""실사용 기록 지표 유스케이스 (ADR 0058, `rra eval usage`) — FeedbackReaderPort 로 읽기만.

선택 기록은 `source=user`·시험 줄 아님만, 과제안 측정은 시험 줄 아님만 센다(규칙은
`domain/rules/eval_usage`). 출력은 별도 JSON(`eval/results/<날짜>-usage.json`)에 쓸 dict —
개수·비율·
초만.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rra.application.ports.feedback_reader import FeedbackReaderPort
from rra.domain.rules.eval_usage import choice_usage, recommend_usage


class UsageMetrics:
    def __init__(self, reader: FeedbackReaderPort):
        self.reader = reader

    def __call__(self, *, since: date | None = None, include_test: bool = False) -> dict[str, Any]:
        choices = self.reader.choice_rows()
        metrics = self.reader.metrics_rows()
        return {
            "kind": "usage",
            "since": since.isoformat() if since else None,
            "include_test": include_test,
            "choices": {
                "found": choices.found,
                **choice_usage(choices.rows, since=since, include_test=include_test),
            },
            "recommend": {
                "found": metrics.found,
                **recommend_usage(metrics.rows, since=since, include_test=include_test),
            },
        }


def usage_lines(report: dict[str, Any]) -> list[str]:
    c, r = report["choices"], report["recommend"]
    lines = [
        "실사용 기록 지표 (시험 계정 줄 " + ("포함" if report["include_test"] else "제외") + ")"
    ]
    if report.get("since"):
        lines.append(f"  기간: {report['since']} 부터")
    lines.append("선택 기록 (source=user)")
    if not c["found"]:
        lines.append("  파일 없음")
    else:
        lines.append(
            f"  제안자 선택 {c['user_choices']}건, [유사함] 비율 {_pct(c['similar_rate'])}"
        )
        lines.append(
            f"  AI 판정 있는 선택 {c['ai_judged']}건, AI 기본 선택과 일치 {_pct(c['ai_agreement'])}"
        )
    lines.append("과제안 측정")
    if not r["found"]:
        lines.append("  파일 없음")
    else:
        lines.append(f"  호출 {r['calls']}건")
        for branch, row in r["by_branch"].items():
            lines.append(
                f"  {branch}: {row['calls']}건, 0건 비율 {_pct(row['zero_rate'])}, "
                f"로컬 대체 {_pct(row['fallback_local_rate'])}, 중앙값 {row['seconds_p50']}초"
            )
    return lines


def _pct(value: float | None) -> str:
    return "없음" if value is None else f"{value * 100:.1f}%"
