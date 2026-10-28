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
        ("policy", "policy_basis_needed", "warning"),
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


def test_policy_choice_fills_policy_and_its_verified_evidence_is_allowed(req):
    """고른 정책적 중요도 작성안(2026-10-28) — 빈칸 아님, 원문 대조 통과 구간(policy_ids)은 근거
    금지
    섹션에서도 허용, 그 밖의 근거는 여전히 오류. 채워진 섹션에는 빈칸 알림을 남기지 않는다."""
    from rra.domain.models import PolicyChoice, PolicySentence

    choice = PolicyChoice(
        mode="card", sentences=[PolicySentence(text="정책 방향과 이어짐.", evidence=["molit:p#0"])]
    )
    with_choice = req.model_copy(update={"policy_choice": choice})
    assert "policy" not in skipped_sections(with_choice, FORM, OPTIONS)
    none = req.model_copy(update={"policy_choice": PolicyChoice(mode="none")})
    assert skipped_sections(none, FORM, OPTIONS)["policy"] == "policy_basis_needed"
    kept = Sentence(text="정책 방향과 이어짐.", evidence=["molit:p#0"], origin="proposer_input")
    d = Draft(
        run_id="r",
        request=req,
        sections=[
            Section(
                key="policy", sentences=[kept, Sentence(text="다른 인용", evidence=["alio:1"])]
            ),
            Section(key="tech", sentences=[Sentence(text="앱 판정", origin="app")]),
            Section(key="task", sentences=[Sentence(text="사유")], choices=["basic"]),
        ],
    )
    problems = lint(d, FORM, choice_options=OPTIONS, policy_ids={"molit:p#0"})
    forbidden = [p for p in problems if p.code == "evidence_forbidden"]
    assert [p.sentence for p in forbidden] == [1]
    assert "policy_basis_needed" not in {p.code for p in problems}  # 채워진 섹션 — 지난 알림


def test_skipped_sections_is_shared_by_generation_and_lint(req):
    assert skipped_sections(req, FORM, OPTIONS) == {
        "policy": "policy_basis_needed",
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


def test_foreign_script_sentences_get_a_warning_but_are_kept():
    from rra.domain.models import Draft, ProposalRequest, Section, Sentence
    from rra.domain.rules.foreign_script import foreign_script_chars, has_foreign_script
    from rra.domain.rules.lint import FOREIGN_SCRIPT, LintRules, lint

    assert foreign_script_chars("사례 조사(文档ID: x)와 研究") == ["文", "档", "研", "究"]
    assert has_foreign_script("データ 분석") and not has_foreign_script(
        "ABC 123 궤도 ㄱㄴ ㅏ 15% (예)"
    )
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    draft = Draft(
        run_id="20260101000000-deadbeef",
        request=req,
        sections=[
            Section(
                key="method",
                sentences=[
                    Sentence(text="정상 문장임."),
                    Sentence(text="궤도 퀄리티를 개선하는 文档 분석임."),
                    Sentence(text="カタカナ 혼입", origin="app"),
                ],
            )
        ],
    )
    problems = lint(draft, LintRules(required_sections=["method"]))
    hits = [p for p in problems if p.code == FOREIGN_SCRIPT]
    assert [(p.sentence, p.severity) for p in hits] == [(1, "warning"), (2, "warning")]
    assert (
        "文档" in hits[0].message and len(draft.section("method").sentences) == 3
    )  # 버리지 않는다


# ── 관련도 하한 — 근거 청크가 없으면 근거 필수 섹션은 빈칸 + 경고 ─────────────
def test_evidence_skipped_sections_only_when_snapshot_has_no_chunks(req):
    from rra.domain.models import Chunk, RetrievalSnapshot
    from rra.domain.rules.lint import evidence_skipped_sections

    rules = LintRules(required_sections=["tech", "overlap"], evidence_required=["tech", "overlap"])
    empty = RetrievalSnapshot.of("q", [])
    assert evidence_skipped_sections(rules, empty) == {
        "tech": "no_relevant_evidence",
        "overlap": "no_relevant_evidence",
    }
    assert evidence_skipped_sections(rules, empty, exempt={"overlap"}) == {
        "tech": "no_relevant_evidence"
    }
    one = RetrievalSnapshot.of("q", [Chunk(chunk_id="a:1#0", doc_id="a:1", ordinal=0, text="t")])
    assert evidence_skipped_sections(rules, one) == {}


def test_lint_reports_no_relevant_evidence_as_a_warning_not_missing(req):
    rules = LintRules(required_sections=["tech"], evidence_required=["tech"])
    d = Draft(run_id="r", request=req, sections=[Section(key="tech", sentences=[])])
    assert [p.code for p in lint(d, rules)] == ["missing"]
    problems = lint(d, rules, evidence_skipped={"tech": "no_relevant_evidence"})
    assert [(p.code, p.severity) for p in problems] == [("no_relevant_evidence", "warning")]
    assert "관련도 하한" in problems[0].message


# ── 표 사실(P2-8) ─────────────────────────────────────────
def test_cited_table_facts_make_numbers_supported(req):
    from decimal import Decimal

    from rra.domain.models import TableFact

    rules = LintRules(sections=["effect"], required_sections=[], number_checked=["effect"])
    sentence = Sentence(text="엘리베이터는 1,512대로 집계됨", evidence=["korail_web:a#0"])
    d = Draft(run_id="r", request=req, sections=[Section(key="effect", sentences=[sentence])])
    fact = TableFact(
        item="합계 엘리베이터",
        value=Decimal("1512"),
        value_text="1,512",
        doc_id="korail_web:a",
        unit="대",
    )
    chunk_texts = {"korail_web:a#0": "역별 승강설비 현황 표 (수치는 셀에 흩어져 있음)"}
    assert [p.code for p in lint(d, rules, chunk_texts=chunk_texts)] == ["unsupported_number"]
    assert lint(d, rules, chunk_texts=chunk_texts, facts={"korail_web:a": [fact]}) == []
    # 인용하지 않은 문서의 사실은 근거가 아니다
    assert [p.code for p in lint(d, rules, chunk_texts=chunk_texts, facts={"alio:z": [fact]})] == [
        "unsupported_number"
    ]
