"""10. 규칙 엔진. 규칙 데이터는 rules.yaml 에서 주입."""

from __future__ import annotations

from pydantic import BaseModel, Field

from rra.domain.models import Draft


class LintRules(BaseModel):
    required_sections: list[str]
    max_chars: dict[str, int] = Field(default_factory=dict)
    evidence_required: list[str] = Field(default_factory=list)


class LintProblem(BaseModel):
    section: str
    code: str
    message: str


def lint(draft: Draft, rules: LintRules) -> list[LintProblem]:
    problems: list[LintProblem] = []
    keys = {s.key for s in draft.sections}
    for k in rules.required_sections:
        if k not in keys or not draft.section(k).sentences:  # type: ignore[union-attr]
            problems.append(
                LintProblem(section=k, code="missing", message="필수 섹션 누락/비어있음")
            )
    for sec in draft.sections:
        limit = rules.max_chars.get(sec.key)
        if limit and len(sec.text) > limit:
            problems.append(
                LintProblem(
                    section=sec.key, code="too_long", message=f"{len(sec.text)}자 > {limit}자"
                )
            )
        if sec.key in rules.evidence_required:
            for s in sec.sentences:
                if not s.evidence:
                    problems.append(
                        LintProblem(
                            section=sec.key, code="no_evidence", message=f"근거 없음: {s.text[:30]}"
                        )
                    )
    return problems
