"""Q6 규칙 검사·자동 정리 — 어미 통일·완전 중복 제거·긴 문장·문체 혼용·연차 불일치."""

from rra.domain.models import Section, Sentence
from rra.domain.rules import style


def sec(*texts, key="method", origin="llm"):
    return Section(key=key, sentences=[Sentence(text=t, origin=origin) for t in texts])


def test_unify_ending_converts_prose_to_report_style_and_leaves_report_style():
    assert style.unify_ending("검측 이력을 분석한다.") == "검측 이력을 분석함."
    assert style.unify_ending("보수 비용이 절감됩니다") == "보수 비용이 절감됨."
    assert style.unify_ending("효과가 있다.") == "효과가 있음."
    assert style.unify_ending("본 과제는 응용연구이다.") == "본 과제는 응용연구임."
    assert style.unify_ending("이미 개조식임.") == "이미 개조식임."
    assert (
        style.unify_ending("궤도 틀림 열화 예측 연구") == "궤도 틀림 열화 예측 연구"
    )  # 제목형은 그대로
    assert style.is_prose("그렇게 할 것이다.") and not style.is_prose("그렇게 함.")


def test_check_sections_fixes_endings_and_exact_duplicates_and_reports_the_rest():
    sections = [
        sec("제목형", key="title"),
        sec(
            "첫 단계를 수행한다.",
            "첫 단계를 수행함.",
            "둘째 단계임.",
            "x" * 200 + "임.",
            "그렇게 하였다.",
        ),
        sec("앱 확정 문장이다.", key="overlap_review", origin="app"),
    ]
    out = style.check_sections(sections, max_chars=150)
    method = out.sections[1]
    assert [s.text for s in method.sentences] == [
        "첫 단계를 수행함.",
        "둘째 단계임.",
        "x" * 200 + "임.",
        "그렇게 하였다.",
    ]  # 어미 통일 뒤 완전 중복 하나 제거
    assert out.fixed == ["method:0 어미 통일", "method:1 완전 중복 제거"]
    codes = [(f.code, f.sentence) for f in out.findings]
    assert (style.LONG_SENTENCE, 2) in codes and (style.MIXED_STYLE, 3) in codes
    assert out.sections[0].sentences[0].text == "제목형"  # 제목은 건드리지 않는다
    assert out.sections[2].sentences[0].text == "앱 확정 문장이다."  # 앱 문장도 그대로
    assert out.sections[1].sentences[0].origin == "llm"  # 출처 유지


def test_period_mismatch_against_constraints():
    assert style.allowed_years("예산 2억 원 이내, 연구기간 1년 이내") == 1
    assert style.allowed_years("3년 이내 완료") == 3 and style.allowed_years("") is None
    out = style.check_sections(
        [sec("1차년도에 설치함.", "2차년도에 확대함.")], constraints="연구기간 1년 이내"
    )
    [f] = [f for f in out.findings if f.code == style.PERIOD_MISMATCH]
    assert f.sentence == 1 and "2차년도" in f.message
    assert not style.check_sections([sec("2차년도에 확대함.")], constraints="3년 이내").findings


def test_fix_false_only_reports():
    out = style.check_sections([sec("분석한다.", "분석한다.")], fix=False)
    assert [s.text for s in out.sections[0].sentences] == ["분석한다.", "분석한다."]
    assert out.fixed == [] and all(f.code == style.MIXED_STYLE for f in out.findings)


def test_trim_sections_cuts_trailing_sentences_to_the_limit_and_keeps_app_sentences():
    from rra.domain.models import Section, Sentence
    from rra.domain.rules.style import SECTION_TRIMMED, trim_sections

    long = Section(key="overlap_review", sentences=[Sentence(text="가" * 60) for _ in range(5)])
    short = Section(key="method", sentences=[Sentence(text="짧음.")])
    app = Section(
        key="utilization",
        sentences=[Sentence(text="나" * 60), Sentence(text="앱 확정", origin="app")],
    )
    out, findings = trim_sections([long, short, app], {"overlap_review": 150, "utilization": 50})
    assert len(out[0].sentences) == 2 and len(out[0].text) <= 150
    assert out[1] is short and out[2] is app  # 앱 문장은 자르지 않는다
    assert [(f.section, f.code) for f in findings] == [("overlap_review", SECTION_TRIMMED)]
    single = Section(key="overlap_review", sentences=[Sentence(text="다" * 300)])
    assert trim_sections([single], {"overlap_review": 150})[0][0] is single  # 문장 하나면 그대로
