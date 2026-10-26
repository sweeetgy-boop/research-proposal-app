"""렌더 전 점검 — 미해결 알림(lint 경고) 과 칸 길이 초과 목록. 렌더를 막지 않는다.

- 미해결 알림: run 에 저장된 lint 문제 전부 (근거 없는 수치, 목록 비어 빈칸 등). 앱에는 '해결'
  처리가 없으므로 저장된 문제는 모두 미해결로 본다. 담당자가 양식에서 직접 확인한다.
- 칸 길이 초과: 본문 섹션은 rules.yaml max_chars, 한 줄 칸(연구과제명·예산·전략과제·제안부서·
  제안자 칸)은 slots.yaml line_limits. 넘어도 자르지 않는다 — 목록만 돌려준다.
- 전략체계 목록(korail_strategy.yaml)이 비어 있거나 전략이 확정되지 않았으면 2-가-(3) 두 줄이
  빈칸으로 나간다는 알림.

순수 함수. 렌더 결과(bytes)는 건드리지 않는다 — 진입점이 렌더 전에 출력한다 (CLI 는 stdout, UI 는
받기 버튼 위, REST 는 GET /v1/runs/{id}/render-check).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models import Confirmation, Draft, ProposerInfo
from rra.domain.rules.lint import LintProblem, LintRules

STRATEGY_KEY = "strategy_alignment"
STRATEGY_EMPTY = (
    "2-가-(3) 전략방향·전략과제: 전략체계 목록(korail_strategy.yaml)이 비어 있어 빈칸으로 나갑니다."
)
STRATEGY_UNCONFIRMED = "2-가-(3) 전략방향·전략과제: 전략이 확정되지 않아 빈칸으로 나갑니다."


@dataclass(frozen=True)
class Overflow:
    # 섹션 키(title, method…) 또는 입력 경로(budget.account, proposer.name, strategy_alignment:task)
    slot: str
    chars: int
    limit: int
    kind: str  # "line" = 한 줄 칸(slots.yaml line_limits) | "section" = 본문(rules.yaml max_chars)


@dataclass(frozen=True)
class RenderCheck:
    unresolved: list[LintProblem] = field(default_factory=list)
    overflow: list[Overflow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.unresolved) + len(self.overflow) + len(self.notes)


def render_check(
    draft: Draft,
    problems: Sequence[Mapping[str, Any]],
    rules: LintRules,
    *,
    confirmation: Confirmation | None,
    proposer: ProposerInfo | None,
    line_limits: Mapping[str, int],
    strategy_labels: Mapping[str, str],
) -> RenderCheck:
    """problems: RunState.problems (LintProblem.model_dump()). strategy_labels: 전략과제 id→이름"""
    unresolved = [LintProblem.model_validate(dict(p)) for p in problems]
    overflow: list[Overflow] = []

    for section in draft.sections:
        limit = rules.max_chars.get(section.key)
        if limit and len(section.text) > limit:
            overflow.append(Overflow(section.key, len(section.text), limit, "section"))

    confirmed = dict(confirmation.choices) if confirmation else {}
    req = draft.request
    budget = req.budget
    person = proposer or ProposerInfo()
    strategy_tasks = ", ".join(strategy_labels.get(i, i) for i in confirmed.get(STRATEGY_KEY, []))
    title_section = draft.section("title")
    inline: dict[str, str] = {
        "title": title_section.text if title_section else "",
        "budget.account": budget.account if budget else "",
        "budget.amount_thousand_krw": (
            f"{budget.amount_thousand_krw:,}"
            if budget and budget.amount_thousand_krw is not None
            else ""
        ),
        "department": req.department,
        f"{STRATEGY_KEY}:task": strategy_tasks,
        "proposed_on": person.proposed_on,
        "proposer.rank": person.proposer.rank,
        "proposer.name": person.proposer.name,
        "proposer.phone": person.proposer.phone,
        "head.rank": person.head.rank,
        "head.name": person.head.name,
        "head.phone": person.head.phone,
    }
    for slot, limit in line_limits.items():
        value = inline.get(slot)
        if value is not None and limit > 0 and len(value) > limit:
            overflow.append(Overflow(slot, len(value), limit, "line"))

    notes: list[str] = []
    if STRATEGY_KEY in rules.choices:
        if not strategy_labels:
            notes.append(STRATEGY_EMPTY)
        elif not confirmed.get(STRATEGY_KEY):
            notes.append(STRATEGY_UNCONFIRMED)
    return RenderCheck(unresolved=unresolved, overflow=overflow, notes=notes)
