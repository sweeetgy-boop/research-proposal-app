"""빈 초안 금지 — 일부 섹션의 로컬 작성이 실패해도 run 을 invalid 로 끝내지 않는다.
(2026-10-28, ADR 0027)

실패 판정은 step 기록(StepRecord)만 본다 — 재개·재조회 때도 같은 답이 나오고, 원문은 필요 없다.
- parse 가 ok 가 아니면(fence·json·schema·choices_only) 실패. 사유 = parse 상태.
- 필수 섹션인데 parse ok 이고 문장이 0 이면 실패. 폐기가 있으면 `dropped`(검증에서 전부 버림),
  없으면 `empty`(모델이 빈 목록을 냈다).
- LLM 을 쓰지 않은 섹션(skipped·app)과 아직 돌지 않은 step 은 보지 않는다.

필수 섹션의 `missing` 오류는 실패 섹션에 한해 `generation_failed` 경고로 바꾼다(relax_failed) —
성공한 섹션은 초안으로 보여 주고 검토·편집으로 이어 가되, 실패 섹션은 빈칸 + 목록·사유를 남긴다.
전부 실패했을 때만(all_failed) invalid.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rra.domain.models.run import SECTION_PREFIX, FailedSection, StepRecord
from rra.domain.rules.lint import LintProblem

GENERATION_FAILED = "generation_failed"
NON_LLM_PARSE = frozenset({"skipped", "app"})
REASON_LABEL = {
    "fence": "출력 형식 오류(코드펜스)",
    "json": "JSON 문법 오류(잘린 응답 포함)",
    "schema": "출력 스키마 불일치",
    "choices_only": "선택지만 받고 문장은 형식 오류",
    "empty": "모델이 빈 문장 목록을 냄",
    "dropped": "검증(근거·고유명)에서 문장 전부 폐기",
}


def reason_label(reason: str) -> str:
    return REASON_LABEL.get(reason, reason)


def failed_sections(steps: Sequence[StepRecord], required: Iterable[str]) -> list[FailedSection]:
    """step 기록 → 실패 섹션 목록 (run 의 섹션 순서)."""
    need = set(required)
    out: list[FailedSection] = []
    for step in steps:
        if not step.name.startswith(SECTION_PREFIX) or step.status != "done":
            continue
        key = step.name[len(SECTION_PREFIX) :]
        parse = step.parse
        if parse is None or parse in NON_LLM_PARSE:
            continue
        if parse != "ok":
            out.append(FailedSection(key=key, reason=parse))
        elif key in need and step.sentences == 0:
            out.append(FailedSection(key=key, reason="dropped" if step.dropped else "empty"))
    return out


def attempted_sections(steps: Sequence[StepRecord]) -> list[str]:
    """LLM 이 실제로 쓴(쓰려 한) 섹션 — 전부 실패 판정의 분모."""
    return [
        s.name[len(SECTION_PREFIX) :]
        for s in steps
        if s.name.startswith(SECTION_PREFIX)
        and s.status == "done"
        and s.parse is not None
        and s.parse not in NON_LLM_PARSE
    ]


def all_failed(failed: Sequence[FailedSection], attempted: Sequence[str]) -> bool:
    """LLM 이 쓴 섹션이 하나라도 있고 그 전부가 실패했다 → 빈 초안 = invalid."""
    if not attempted:
        return False
    keys = {f.key for f in failed}
    return all(k in keys for k in attempted)


def relax_failed(
    problems: Sequence[LintProblem], failed: Sequence[FailedSection]
) -> list[LintProblem]:
    """실패 섹션의 `missing` 오류를 `generation_failed` 경고로 바꾼다. 나머지는 그대로."""
    reasons = {f.key: f for f in failed}
    out: list[LintProblem] = []
    for p in problems:
        f = reasons.get(p.section)
        if f is not None and p.code == "missing" and p.severity == "error":
            out.append(
                LintProblem(
                    section=p.section,
                    code=GENERATION_FAILED,
                    message=f"생성 실패({reason_label(f.reason)}) — 이 섹션을 다시 생성하십시오",
                    severity="warning",
                    sentence=None,
                )
            )
        else:
            out.append(p)
    return out


def still_failed(failed: Sequence[FailedSection], sections: Iterable[Any]) -> list[FailedSection]:
    """새 버전에서 문장이 채워진 섹션은 실패 목록에서 뺀다 (다시 생성·직접 수정 뒤)."""
    filled = {s.key for s in sections if getattr(s, "sentences", None)}
    return [f for f in failed if f.key not in filled]
