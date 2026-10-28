"""10. 규칙 엔진. 규칙 데이터는 rules.yaml 에서 주입."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from rra.domain.models import Draft, ProposalRequest, RetrievalSnapshot, Sentence
from rra.domain.models.selection import OPTION_SOURCES, STRATEGY_SOURCE
from rra.domain.models.table_fact import TableFact
from rra.domain.rules.foreign_script import foreign_script_chars
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.policy_cards import (
    POLICY_BASIS_NEEDED,
    POLICY_BASIS_NEEDED_MESSAGE,
    has_choice_text,
)

Severity = Literal["error", "warning"]

# 경고 코드 — run 을 invalid 로 만들지 않는다 (사용자가 채울 칸)
INPUT_MISSING = "input_missing"  # 입력에만 근거하는 섹션인데 입력이 비었다 → LLM 생략, 빈칸
CATALOG_EMPTY = "catalog_empty"  # 선택지 목록이 비었다 → LLM 생략, 빈칸
NO_CHOICE = "no_choice"  # 선택형 섹션인데 LLM 이 유효한 선택지를 내지 못했다 → 사용자가 고른다
STYLE_CODES = ("long_sentence", "mixed_style", "period_mismatch")  # Q6 규칙 검사 알림 (경고)
UNSUPPORTED_NUMBER = "unsupported_number"  # 입력·인용 근거에 없는 수치 → 담당자 확인
FOREIGN_SCRIPT = "foreign_script"  # 한국어 본문에 한자·가나 혼입 → 문장은 두고 알림만
NO_RELEVANT_EVIDENCE = "no_relevant_evidence"  # 관련도 하한 넘는 근거 없음 → LLM 생략, 빈칸


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
    # 문장의 수치가 입력·인용 근거에 없으면 경고(unsupported_number). 폐기하지 않는다
    number_checked: list[str] = Field(default_factory=list)
    choices: dict[str, ChoiceSpec] = Field(default_factory=dict)
    titles: dict[str, str] = Field(default_factory=dict)  # 섹션 → 양식 항목 이름 (표시용)

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
            "number_checked": set(self.number_checked),
            "choices": set(self.choices),
            "titles": set(self.titles),
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
    # 문장 단위 문제면 그 문장의 섹션 내 인덱스 (화면이 문장 옆에 붙인다)
    sentence: int | None = None


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
            if "policy_basis" in fields:
                # 고른 정책적 중요도 작성안이 있으면 앱이 그것으로 쓴다 — 빈칸 아님
                if not has_choice_text(req):
                    out[key] = POLICY_BASIS_NEEDED
                continue
            out[key] = INPUT_MISSING
            continue
        spec = rules.choices.get(key)
        if spec is not None and choice_options is not None and not choice_options.get(key):
            out[key] = CATALOG_EMPTY
    return out


def evidence_skipped_sections(
    rules: LintRules, snapshot: RetrievalSnapshot, exempt: Iterable[str] = ()
) -> dict[str, str]:
    """근거 필수 섹션인데 스냅샷에 (관련도 하한을 넘은) 청크가 하나도 없으면 빈칸 → 경고 코드.

    exempt: 자료 없이도 쓸 수 있는 섹션 (유사과제 판정으로 앱이 쓰는 특이사항 등).
    생성(usecase)과 lint 가 같은 판정을 쓴다. 스냅샷만 보므로 재개해도 결과가 같다.
    """
    if snapshot.chunks:
        return {}
    skip = set(exempt)
    return {k: NO_RELEVANT_EVIDENCE for k in rules.evidence_required if k not in skip}


def _filled(value: object) -> bool:
    return bool(value.strip()) if isinstance(value, str) else value is not None


_SKIP_MESSAGE = {
    INPUT_MISSING: "근거가 될 제안자 입력이 없어 비워 둠 (직접 작성 필요)",
    POLICY_BASIS_NEEDED: POLICY_BASIS_NEEDED_MESSAGE,
    CATALOG_EMPTY: "선택지 목록(config)이 비어 있어 비워 둠",
    NO_RELEVANT_EVIDENCE: "관련도 하한을 넘는 수집 자료가 없어 비워 둠 (자료 적재 또는 직접 작성)",
}


def _request_texts(req: ProposalRequest) -> list[str]:
    """수치 대조에 쓰는 제안자 입력 — 문자열 필드 전부 + 예산 금액."""
    texts = [v for v in req.model_dump().values() if isinstance(v, str)]
    if req.budget is not None and req.budget.amount_thousand_krw is not None:
        texts.append(f"{req.budget.amount_thousand_krw}천원")
    return texts


def _cited_texts(sentence: Sentence, chunk_texts: Mapping[str, str]) -> list[str]:
    """문장이 인용한 근거 청크의 본문. doc_id 로 인용했으면 그 문서의 청크 전부."""
    out: list[str] = []
    for ev in sentence.evidence:
        if ev in chunk_texts:
            out.append(chunk_texts[ev])
            continue
        out.extend(t for cid, t in chunk_texts.items() if cid.split("#")[0] == ev)
    return out


def _cited_facts(sentence: Sentence, facts: Mapping[str, Sequence[TableFact]]) -> list[TableFact]:
    """문장이 인용한 문서(chunk_id 의 doc 부분)의 표 사실."""
    out: list[TableFact] = []
    for ev in sentence.evidence:
        out.extend(facts.get(ev.split("#")[0], ()))
    return out


def lint(
    draft: Draft,
    rules: LintRules,
    *,
    choice_options: Mapping[str, Mapping[str, str]] | None = None,
    chunk_texts: Mapping[str, str] | None = None,
    evidence_skipped: Mapping[str, str] | None = None,
    facts: Mapping[str, Sequence[TableFact]] | None = None,
    policy_ids: set[str] | None = None,
) -> list[LintProblem]:
    """chunk_texts: 이번 run 스냅샷의 chunk_id → 본문. 수치 검사(number_checked)에만 쓴다.
    evidence_skipped: `evidence_skipped_sections` 결과 — 근거가 없어 빈칸으로 둔 섹션 (경고만).
    facts: doc_id → 표 사실(P2-8). 인용 문서의 표 칸 수치는 근거 있는 수치로 본다. 없으면 종전과
    같다.
    policy_ids: 고른 정책적 중요도 작성안의 원문 대조 통과 구간 — 근거 금지 섹션에서도 이 근거는
    허용한다(앱이 작성안을 그대로 옮긴 문장)."""
    problems: list[LintProblem] = []
    request_texts = _request_texts(draft.request)
    skipped = {**skipped_sections(draft.request, rules, choice_options), **(evidence_skipped or {})}
    # 빈칸으로 둔 섹션을 제안자가 나중에 채웠으면(직접 작성·작성안 고르기) 빈칸 알림은 지난 것이다
    skipped = {
        k: c
        for k, c in skipped.items()
        if not ((sec := draft.section(k)) is not None and sec.sentences)
    }
    allowed_policy = policy_ids or set()
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
            for i, s in enumerate(sec.sentences):
                if not s.evidence and s.origin != "app":
                    problems.append(
                        LintProblem(
                            section=sec.key,
                            code="no_evidence",
                            message=f"근거 없음: {s.text[:30]}",
                            sentence=i,
                        )
                    )
        if sec.key in rules.evidence_forbidden:
            for i, s in enumerate(sec.sentences):
                if s.evidence and not set(s.evidence) <= allowed_policy:
                    problems.append(
                        LintProblem(
                            section=sec.key,
                            code="evidence_forbidden",
                            message=f"입력만 근거로 써야 함: {s.text[:30]}",
                            sentence=i,
                        )
                    )
        for i, s in enumerate(sec.sentences):
            foreign = foreign_script_chars(s.text)
            if foreign:
                problems.append(
                    LintProblem(
                        section=sec.key,
                        code=FOREIGN_SCRIPT,
                        message=f"외국 문자 혼입 {''.join(foreign[:8])}: {s.text[:30]}",
                        severity="warning",
                        sentence=i,
                    )
                )
        if sec.key in rules.number_checked:
            for i, s in enumerate(sec.sentences):
                if s.origin in ("app", "input"):  # 앱 확정 문장·입력 그대로는 검사하지 않는다
                    continue
                cited = _cited_texts(s, chunk_texts or {})
                bad = unsupported_numbers(
                    s.text, [*request_texts, *cited], facts=_cited_facts(s, facts or {})
                )
                if bad:
                    problems.append(
                        LintProblem(
                            section=sec.key,
                            code=UNSUPPORTED_NUMBER,
                            message=f"입력·근거에 없는 수치 {', '.join(bad)}: {s.text[:30]}",
                            severity="warning",
                            sentence=i,
                        )
                    )
    return problems
