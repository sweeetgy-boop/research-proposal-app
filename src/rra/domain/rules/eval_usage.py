"""실사용 기록 지표 (ADR 0058, 계약 docs/contracts/eval-results.md §3, `rra eval usage`) — 순수
함수.

- 선택 기록(similar_choices.jsonl): `source == "user"` 이고 `test` 가 아닌 줄만. AI 판정(judgment)이
  있는 줄에서 제안자 선택이 AI 기본 선택(같다·일부 겹침 → 유사함, 다르다 → 관련 없음)과 같은
  비율 = `ai_agreement`.
- 과제안 측정(recommend_metrics.jsonl): `test` 가 아닌 줄만. 갈래(branch)별 건수·과제안 0건 비율·
  seconds 중앙값, 로컬 대체 비율. 옛 줄(branch 없음)은 differentiate 로 본다.
출력은 개수·비율·초뿐 — doc_id·아이디어 해시·시각은 담지 않는다(보안 D).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from rra.domain.rules.feedback_stats import is_test_line
from rra.domain.rules.recommend_metrics import BRANCH_DIFFERENTIATE, BRANCHES
from rra.domain.rules.similar_choice import SIMILAR, SOURCE_USER, UNRELATED

_DEFAULT_BY_VERDICT = {"same": SIMILAR, "partial": SIMILAR, "different": UNRELATED}


def _since_ok(row: Mapping[str, Any], since: date | None, key: str) -> bool:
    if since is None:
        return True
    raw = row.get(key)
    if not isinstance(raw, str) or len(raw) < 10:
        return False
    try:
        return date.fromisoformat(raw[:10]) >= since
    except ValueError:
        return False


def choice_usage(
    rows: Iterable[Mapping[str, Any]], *, since: date | None = None, include_test: bool = False
) -> dict[str, Any]:
    total = judged = agree = similar = 0
    for row in rows:
        if not include_test and is_test_line(row):
            continue
        if row.get("source") != SOURCE_USER or not _since_ok(row, since, "at"):
            continue
        total += 1
        choice = row.get("choice")
        if choice == SIMILAR:
            similar += 1
        default = _DEFAULT_BY_VERDICT.get(str(row.get("judgment") or ""))
        if default is not None and choice in (SIMILAR, UNRELATED):
            judged += 1
            agree += int(default == choice)
    return {
        "user_choices": total,
        "similar_rate": round(similar / total, 3) if total else None,
        "ai_judged": judged,
        "ai_agreement": round(agree / judged, 3) if judged else None,
    }


def recommend_usage(
    rows: Iterable[Mapping[str, Any]], *, since: date | None = None, include_test: bool = False
) -> dict[str, Any]:
    by_branch: dict[str, dict[str, Any]] = {
        b: {"calls": 0, "zero": 0, "seconds": [], "fallback_local": 0} for b in BRANCHES
    }
    for row in rows:
        if not include_test and is_test_line(row):
            continue
        if not _since_ok(row, since, "ts"):
            continue
        branch = row.get("branch")
        branch = branch if branch in BRANCHES else BRANCH_DIFFERENTIATE
        acc = by_branch[branch]
        acc["calls"] += 1
        cards = row.get("cards")
        if isinstance(cards, int) and not isinstance(cards, bool) and cards == 0:
            acc["zero"] += 1
        if row.get("fallback_local") is True:
            acc["fallback_local"] += 1
        sec = row.get("seconds")
        if isinstance(sec, int | float) and not isinstance(sec, bool) and sec >= 0:
            acc["seconds"].append(float(sec))
    out: dict[str, Any] = {"calls": sum(a["calls"] for a in by_branch.values()), "by_branch": {}}
    for branch, acc in by_branch.items():
        n = acc["calls"]
        out["by_branch"][branch] = {
            "calls": n,
            "zero_rate": round(acc["zero"] / n, 3) if n else None,
            "fallback_local_rate": round(acc["fallback_local"] / n, 3) if n else None,
            "seconds_p50": round(statistics.median(acc["seconds"]), 2) if acc["seconds"] else None,
        }
    return out
