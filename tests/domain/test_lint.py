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


# ── 수치 검사 (number_checked) — 경고만, 폐기 없음 ────────────────
NUMBERS = LintRules(
    sections=["method", "effect"],
    required_sections=["method"],
    number_checked=["method", "effect"],
)


def _draft(req, *sentences):
    return Draft(
        run_id="r",
        request=req.model_copy(update={"constraints": "연구기간 1년 이내"}),
        sections=[
            Section(key="method", sentences=list(sentences)),
            Section(key="effect", sentences=[]),
        ],
    )


def test_unsupported_number_is_a_warning_with_the_numbers_named(req):
    d = _draft(req, Sentence(text="2년 동안 개발해 비용을 약 10% 절감함"))
    problems = lint(d, NUMBERS)
    [p] = [p for p in problems if p.code == "unsupported_number"]
    assert p.severity == "warning" and p.section == "method"
    assert "2년" in p.message and "10%" in p.message
    assert not has_errors(problems)


def test_converted_units_and_cited_chunk_numbers_pass(req):
    d = _draft(
        req,
        Sentence(text="12개월 안에 완료함"),  # 1년 이내 → 환산 통과
        Sentence(text="선행연구는 15% 개선을 보고함", evidence=["openalex:W1#0"]),
        Sentence(
            text="문서 단위 인용도 그 문서 청크 전부를 근거로 봄 24개월", evidence=["openalex:W1"]
        ),
    )
    chunks = {"openalex:W1#0": "RMSE decreased by 15% over 24 months", "alio:1#0": "서론"}
    assert [p.code for p in lint(d, NUMBERS, chunk_texts=chunks)] == []


def test_numbers_cited_from_an_uncited_chunk_are_not_support(req):
    d = _draft(req, Sentence(text="15% 개선", evidence=["alio:1#0"]))
    chunks = {"openalex:W1#0": "15% improvement", "alio:1#0": "서론"}
    assert [p.code for p in lint(d, NUMBERS, chunk_texts=chunks)] == ["unsupported_number"]


def test_app_and_input_sentences_are_not_number_checked(req):
    d = _draft(
        req,
        Sentence(text="유사도 0.80 기준", origin="app"),
        Sentence(text="예산 5억원", origin="input"),
    )
    assert lint(d, NUMBERS) == []


def test_sections_outside_number_checked_are_not_checked(req):
    rules = LintRules(sections=["method"], required_sections=["method"])
    d = Draft(
        run_id="r", request=req, sections=[Section(key="method", sentences=[Sentence(text="10%")])]
    )
    assert lint(d, rules) == []


def test_number_checked_must_name_known_sections():
    with pytest.raises(ValidationError):
        LintRules(sections=["a"], required_sections=["a"], number_checked=["zzz"])


def test_sentence_index_survives_run_state_round_trip(req):
    """state.json 의 problems(sentence 가 int|None)를 RunState 가 다시 읽을 수 있어야 한다."""
    from rra.domain.models import RunState

    d = _draft(req, Sentence(text="약 10% 절감"))
    problems = [p.model_dump() for p in lint(d, NUMBERS)]
    assert problems and problems[0]["sentence"] == 0
    state = RunState(
        run_id="20260101000000-00000001",
        user="local",
        steps=[],
        problems=problems,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    reloaded = RunState.model_validate(state.model_dump(mode="json"))
    assert reloaded.problems[0]["sentence"] == 0
