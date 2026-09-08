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
