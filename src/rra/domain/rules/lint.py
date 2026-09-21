"""10. 규칙 엔진. 규칙 데이터는 rules.yaml 에서 주입."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from rra.domain.models import Draft, ProposalRequest
from rra.domain.models.selection import OPTION_SOURCES, STRATEGY_SOURCE

Severity = Literal["error", "warning"]

# 경고 코드 — run 을 invalid 로 만들지 않는다 (사용자가 채울 칸)
INPUT_MISSING = "input_missing"  # 입력에만 근거하는 섹션인데 입력이 비었다 → LLM 생략, 빈칸
CATALOG_EMPTY = "catalog_empty"  # 선택지 목록이 비었다 → LLM 생략, 빈칸
NO_CHOICE = "no_choice"  # 선택형 섹션인데 LLM 이 유효한 선택지를 내지 못했다 → 사용자가 고른다


class ChoiceSpec(BaseModel):
    options: str  # 선택지 출처: task_types | utilization | strategy_catalog
    min: int = Field(default=1, ge=0)
    max: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check(self) -> ChoiceSpec:
        if self.options not in OPTION_SOURCES:
            raise ValueError(f"알 수 없는 선택지 출처: {self.options!r}")
        if self.min > self.max:
            raise ValueError("choices.min > choices.max")
        return self


class LintRules(BaseModel):
    template: str | None = None  # 양식 id. run 에 기록해 양식 개정 전 run 을 구분한다
    form: str | None = None  # 양식 이름 (표시용)
    sections: list[str] = Field(default_factory=list)  # 생성 순서. 비면 required_sections
    required_sections: list[str]
    max_chars: dict[str, int] = Field(default_factory=dict)
    evidence_required: list[str] = Field(default_factory=list)
    evidence_forbidden: list[str] = Field(default_factory=list)  # 제안자 입력만 근거로 쓰는 섹션
    # 섹션 → 요청 필드. 모두 비면 LLM 을 부르지 않고 빈칸 + 경고
    requires_input: dict[str, list[str]] = Field(default_factory=dict)
    # 섹션 → 고유명(정책·계획명 등)이 반드시 등장해야 하는 출처 (요청 필드명 또는 strategy_catalog)
    input_grounded: dict[str, list[str]] = Field(default_factory=dict)
    choices: dict[str, ChoiceSpec] = Field(default_factory=dict)

    @property
    def order(self) -> list[str]:
        return list(self.sections or self.required_sections)

    @model_validator(mode="after")
    def _consistent(self) -> LintRules:
        known = set(self.order)
        referenced = {
            "required_sections": set(self.required_sections),
            "evidence_required": set(self.evidence_required),
            "evidence_forbidden": set(self.evidence_forbidden),
            "requires_input": set(self.requires_input),
            "input_grounded": set(self.input_grounded),
            "choices": set(self.choices),
        }
        for name, keys in referenced.items():
            unknown = keys - known
            if unknown:
                raise ValueError(f"{name} 에 sections 에 없는 키: {sorted(unknown)}")
        both = set(self.evidence_required) & set(self.evidence_forbidden)
        if both:
            raise ValueError(f"근거 필수이면서 금지인 섹션: {sorted(both)}")
        fields = set(ProposalRequest.model_fields)
        for key, names in self.requires_input.items():
            bad = set(names) - fields
            if bad:
                raise ValueError(f"requires_input.{key}: 요청 필드가 아님 {sorted(bad)}")
        for key, names in self.input_grounded.items():
            bad = set(names) - fields - {STRATEGY_SOURCE}
            if bad:
                raise ValueError(f"input_grounded.{key}: 알 수 없는 출처 {sorted(bad)}")
        return self


class LintProblem(BaseModel):
    section: str
    code: str
    message: str
    severity: Severity = "error"


def has_errors(problems: list[LintProblem]) -> bool:
    return any(p.severity == "error" for p in problems)


def skipped_sections(
    req: ProposalRequest,
    rules: LintRules,
    choice_options: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, str]:
    """LLM 을 부르지 않고 빈칸으로 두는 섹션 → 경고 코드.

    생성(usecase)과 lint 가 같은 판정을 쓴다. 입력·설정만 보므로 재개해도 결과가 같다.
    """
    out: dict[str, str] = {}
    for key in rules.order:
        fields = rules.requires_input.get(key)
        if fields and not any(_filled(getattr(req, f, None)) for f in fields):
            out[key] = INPUT_MISSING
            continue
        spec = rules.choices.get(key)
        if spec is not None and choice_options is not None and not choice_options.get(key):
            out[key] = CATALOG_EMPTY
    return out


def _filled(value: object) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None


_SKIP_MESSAGE = {
    INPUT_MISSING: "근거가 될 제안자 입력이 없어 비워 둠 (직접 작성 필요)",
    CATALOG_EMPTY: "선택지 목록(config)이 비어 있어 비워 둠",
}


def lint(
    draft: Draft,
    rules: LintRules,
    *,
    choice_options: Mapping[str, Mapping[str, str]] | None = None,
) -> list[LintProblem]:
    problems: list[LintProblem] = []
    skipped = skipped_sections(draft.request, rules, choice_options)
    for key, code in skipped.items():
        problems.append(
            LintProblem(section=key, code=code, message=_SKIP_MESSAGE[code], severity="warning")
        )
    keys = {s.key for s in draft.sections}
    for k in rules.required_sections:
        if k in skipped:
            continue
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
        if sec.key in rules.choices and sec.key not in skipped and not sec.choices:
            problems.append(
                LintProblem(
                    section=sec.key,
                    code=NO_CHOICE,
                    message="제안된 선택지 없음 — 확정 단계에서 직접 선택",
                    severity="warning",
                )
            )
        if sec.key in rules.evidence_required:
            for s in sec.sentences:
                if not s.evidence and s.origin != "app":
                    problems.append(
                        LintProblem(
                            section=sec.key, code="no_evidence", message=f"근거 없음: {s.text[:30]}"
                        )
                    )
        if sec.key in rules.evidence_forbidden:
            for s in sec.sentences:
                if s.evidence:
                    problems.append(
                        LintProblem(
                            section=sec.key,
                            code="evidence_forbidden",
                            message=f"입력만 근거로 써야 함: {s.text[:30]}",
                        )
                    )
    return problems
