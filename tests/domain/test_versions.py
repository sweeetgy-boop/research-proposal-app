"""④ 편집 규칙 — 문장 나누기·섹션 편집 근거 이어받기·순서·같은 내용·버전 비교·바뀐 문장 수."""

from rra.domain.models import Section, Sentence
from rra.domain.models.review import DraftVersion
from rra.domain.rules import versions as rule


def sec(*texts, key="method", evidence=None, origin="llm"):
    return Section(
        key=key,
        sentences=[Sentence(text=t, evidence=list(evidence or []), origin=origin) for t in texts],
    )


def test_split_sentences_handles_periods_report_style_endings_and_newlines():
    text = "검측 이력을 분석함. 구간별 속도를 추정함\n보수 우선순위를 정함. 결과를 공유함"
    assert rule.split_sentences(text) == [
        "검측 이력을 분석함.",
        "구간별 속도를 추정함.",
        "보수 우선순위를 정함.",
        "결과를 공유함.",
    ]
    assert rule.split_sentences("") == [] and rule.split_sentences("  \n ") == []
    assert rule.split_sentences("한 문장만.") == ["한 문장만."]


def test_section_from_texts_inherits_evidence_for_same_sentences_and_marks_new_ones():
    old = sec("첫째 문장임.", "둘째 문장임.", evidence=["openalex:W1#0"])
    new = rule.section_from_texts(old, ["둘째 문장임.", "새 문장임.", "첫째 문장임."])
    assert [s.text for s in new.sentences] == ["둘째 문장임.", "새 문장임.", "첫째 문장임."]
    assert new.sentences[0].evidence == ["openalex:W1#0"] and new.sentences[0].origin == "llm"
    assert new.sentences[2].evidence == ["openalex:W1#0"]
    assert new.sentences[1].evidence == [] and new.sentences[1].origin == "proposer_input"
    # 같은 문장이 두 번 나오면 한 번만 이어받는다
    twice = rule.section_from_texts(old, ["첫째 문장임.", "첫째 문장임."])
    assert twice.sentences[0].evidence == ["openalex:W1#0"] and twice.sentences[1].evidence == []


def test_reorder_by_sentence_ids_keeps_missing_ones_at_the_end():
    old = sec("a.", "b.", "c.")
    out = rule.reorder(old, ["s:method:2", "s:method:0"])
    assert [s.text for s in out.sentences] == ["c.", "a.", "b."]
    try:
        rule.reorder(old, ["s:method:9"])
    except ValueError as exc:
        assert "s:method:9" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("모르는 id 는 거부")


def test_same_content_and_changed_sections():
    a = [sec("a.", key="title"), sec("b.", key="method")]
    b = [sec("a.", key="title"), sec("b.", key="method")]
    assert rule.same_content(a, b) and rule.changed_sections(a, b) == []
    c = [sec("a.", key="title"), sec("B.", key="method")]
    assert not rule.same_content(a, c) and rule.changed_sections(a, c) == ["method"]
    d = [sec("a.", key="title")]
    assert rule.changed_sections(a, d) == ["method"]  # 사라진 섹션도 바뀐 것


def test_diff_versions_reports_added_removed_and_moved_sentences_per_changed_section():
    v1 = DraftVersion(version=1, sections=[sec("a.", "b.", "c."), sec("t.", key="title")])
    v2 = DraftVersion(version=2, sections=[sec("b.", "a.", "d."), sec("t.", key="title")])
    [d] = rule.diff_versions(v1, v2)
    assert d["section"] == "method" and d["sentences"] == [3, 3]
    assert [x["text"] for x in d["added"]] == ["d."]
    assert [x["text"] for x in d["removed"]] == ["c."]
    assert {(x["from"], x["to"]) for x in d["moved"]} == {("b.", "b."), ("a.", "a.")}
    assert d["choices_changed"] is False
    assert rule.diff_versions(v1, v1) == []


def test_count_changed_sentences_for_stale_marker():
    old = [sec("a.", "b.")]
    assert rule.count_changed_sentences(old, [sec("a.", "b.")]) == 0
    assert rule.count_changed_sentences(old, [sec("a.", "B.")]) == 2  # 삭제 1 + 추가 1
    assert rule.count_changed_sentences(old, [sec("a.", "b.", "c.")]) == 1
    assert rule.count_changed_sentences(old, [sec("a.")]) == 1
