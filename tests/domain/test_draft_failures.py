"""빈 초안 금지(ADR 0027) — step 기록만으로 실패 섹션을 가리고, missing 오류를 경고로 바꾼다."""

from rra.domain.models.run import FailedSection, StepRecord
from rra.domain.rules import draft_failures as df
from rra.domain.rules.lint import LintProblem


def step(name, parse, sentences=1, dropped=0, status="done"):
    return StepRecord(name=name, status=status, parse=parse, sentences=sentences, dropped=dropped)


STEPS = [
    step("retrieve", None, 0),
    step("section:title", "ok", 1),
    step("section:task_type", "ok", 0),  # 선택지만, 문장 0 (필수) → empty
    step("section:policy_importance", "skipped", 0),
    step("section:tech_importance", "json", 0),
    step("section:strategy_alignment", "fence", 0),  # 필수 아님이어도 파싱 실패는 실패
    step("section:method", "ok", 0, dropped=3),  # 전부 폐기 → dropped
    step("section:utilization", "ok", 0),  # 필수 아님 + 문장 0 → 실패 아님
    step("section:overlap_review", "app", 3),
    step("section:expected", "ok", 2, status="pending"),  # 아직 안 돌았다
    step("finalize", None, 0),
]
REQUIRED = ["title", "task_type", "tech_importance", "method"]


def test_failed_sections_from_steps_only():
    got = df.failed_sections(STEPS, REQUIRED)
    assert [(f.key, f.reason) for f in got] == [
        ("task_type", "empty"),
        ("tech_importance", "json"),
        ("strategy_alignment", "fence"),
        ("method", "dropped"),
    ]
    assert df.attempted_sections(STEPS) == [
        "title",
        "task_type",
        "tech_importance",
        "strategy_alignment",
        "method",
        "utilization",
    ]


def test_all_failed_only_when_every_llm_section_failed():
    failed = df.failed_sections(STEPS, REQUIRED)
    assert not df.all_failed(failed, df.attempted_sections(STEPS))
    all_bad = [
        step("section:a", "json", 0),
        step("section:b", "schema", 0),
        step("section:c", "app", 1),
    ]
    assert df.all_failed(df.failed_sections(all_bad, ["a"]), df.attempted_sections(all_bad))
    assert not df.all_failed([], [])  # LLM 섹션이 없으면 판정 없음


def test_relax_turns_missing_into_warning_only_for_failed_sections():
    problems = [
        LintProblem(section="tech_importance", code="missing", message="필수 섹션 누락/비어있음"),
        LintProblem(section="objective", code="missing", message="필수 섹션 누락/비어있음"),
        LintProblem(section="tech_importance", code="too_long", message="x"),
    ]
    failed = [FailedSection(key="tech_importance", reason="json")]
    out = df.relax_failed(problems, failed)
    assert [(p.section, p.code, p.severity) for p in out] == [
        ("tech_importance", df.GENERATION_FAILED, "warning"),
        ("objective", "missing", "error"),
        ("tech_importance", "too_long", "error"),
    ]
    assert "JSON" in out[0].message and out[0].sentence is None


def test_still_failed_drops_sections_filled_later():
    from rra.domain.models import Section, Sentence

    failed = [FailedSection(key="a", reason="json"), FailedSection(key="b", reason="empty")]
    sections = [Section(key="a", sentences=[Sentence(text="채움")]), Section(key="b", sentences=[])]
    assert [f.key for f in df.still_failed(failed, sections)] == ["b"]
    assert df.reason_label("json").startswith("JSON") and df.reason_label("zzz") == "zzz"
