from rra.domain.models import Draft, Section, Sentence
from rra.domain.rules.lint import LintRules, lint


def test_lint_missing_and_too_long(req):
    rules = LintRules(
        required_sections=["title", "goal"], max_chars={"title": 5}, evidence_required=["goal"]
    )
    d = Draft(
        run_id="r",
        request=req,
        sections=[
            Section(key="title", sentences=[Sentence(text="너무 긴 제목입니다")]),
            Section(key="goal", sentences=[Sentence(text="근거없음")]),
        ],
    )
    codes = {p.code for p in lint(d, rules)}
    assert codes == {"too_long", "no_evidence"}


# ── 양식 규칙 (선택형·입력 전용·경고) ─────────────────────────
import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from rra.domain.rules.lint import ChoiceSpec, has_errors, skipped_sections  # noqa: E402

FORM = LintRules(
    sections=["policy", "tech", "task", "strategy"],
    required_sections=["tech", "task"],
    evidence_required=["tech"],
    evidence_forbidden=["policy"],
    requires_input={"policy": ["policy_basis"]},
    choices={
        "task": ChoiceSpec(options="task_types"),
        "strategy": ChoiceSpec(options="strategy_catalog", max=2),
    },
)
OPTIONS = {"task": {"basic": "기초연구"}, "strategy": {}}


def test_empty_input_and_empty_catalog_are_warnings_not_errors(req):
    d = Draft(
        run_id="r",
        request=req,
        sections=[
            Section(key="policy", sentences=[]),
            Section(key="tech", sentences=[Sentence(text="앱 판정", origin="app")]),
            Section(key="task", sentences=[Sentence(text="사유")], choices=["basic"]),
            Section(key="strategy", sentences=[]),
        ],
    )
    problems = lint(d, FORM, choice_options=OPTIONS)
    assert {(p.section, p.code, p.severity) for p in problems} == {
        ("policy", "input_missing", "warning"),
        ("strategy", "catalog_empty", "warning"),
    }
    assert not has_errors(problems)  # app 문장은 근거 필수에서 제외


def test_missing_choice_is_a_warning_and_evidence_in_policy_is_an_error(req):
    with_basis = req.model_copy(update={"policy_basis": "국가철도망 구축계획"})
    d = Draft(
        run_id="r",
        request=with_basis,
        sections=[
            Section(key="policy", sentences=[Sentence(text="인용", evidence=["alio:1"])]),
            Section(key="tech", sentences=[Sentence(text="근거", evidence=["alio:1"])]),
            Section(key="task", sentences=[Sentence(text="사유")]),
        ],
    )
    problems = {(p.code, p.severity) for p in lint(d, FORM, choice_options=OPTIONS)}
    assert ("no_choice", "warning") in problems
    assert ("evidence_forbidden", "error") in problems


def test_skipped_sections_is_shared_by_generation_and_lint(req):
    assert skipped_sections(req, FORM, OPTIONS) == {
        "policy": "input_missing",
        "strategy": "catalog_empty",
    }
    filled = req.model_copy(update={"policy_basis": "x"})
    assert skipped_sections(filled, FORM, {"task": {"a": "b"}, "strategy": {"D1": "x"}}) == {}


@pytest.mark.parametrize(
    "bad",
    [
        {"sections": ["a"], "required_sections": ["b"]},
        {
            "sections": ["a"],
            "required_sections": [],
            "evidence_required": ["a"],
            "evidence_forbidden": ["a"],
        },
        {"sections": ["a"], "required_sections": [], "requires_input": {"a": ["no_such_field"]}},
        {"sections": ["a"], "required_sections": [], "input_grounded": {"a": ["nope"]}},
        {"sections": ["a"], "required_sections": [], "choices": {"a": {"options": "nope"}}},
        {
            "sections": ["a"],
            "required_sections": [],
            "choices": {"a": {"options": "utilization", "min": 3, "max": 2}},
        },
    ],
)
def test_inconsistent_rules_are_rejected(bad):
    with pytest.raises(ValidationError):
        LintRules.model_validate(bad)
