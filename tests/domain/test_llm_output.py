"""A. LLM 출력 파서 — 허용하는 감싸기는 펜스 한 개뿐. 실패 사유를 구분한다."""

import json

import pytest

from rra.domain.models import Section, Sentence
from rra.domain.rules.llm_output import parse_sentences
from rra.domain.rules.trust import enforce_section_evidence, normalize_evidence_id

ARRAY = json.dumps([{"text": "문장", "evidence": ["a:1#0"]}], ensure_ascii=False)


@pytest.mark.parametrize(
    "raw",
    [
        ARRAY,
        f"  {ARRAY}\n",
        f"```json\n{ARRAY}\n```",
        f"```\n{ARRAY}\n```",  # 실제 Qwen2.5-3B 출력 형태 (언어 태그 없음)
        f"```JSON\n{ARRAY}\n```\n",
    ],
)
def test_accepted_shapes(raw):
    result = parse_sentences(raw)
    assert result.status == "ok" and result.ok
    assert result.sentences == [Sentence(text="문장", evidence=["a:1#0"])]
    assert result.raw_chars == len(raw)


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (f"```python\n{ARRAY}\n```", "fence"),  # 다른 언어 태그
        (f"다음은 결과입니다.\n```json\n{ARRAY}\n```", "fence"),  # 펜스 앞 설명문
        (f"```json\n{ARRAY}\n```\n이상입니다.", "fence"),  # 펜스 뒤 설명문
        (f"```json\n{ARRAY}\n```\n```json\n{ARRAY}\n```", "fence"),  # 펜스 두 개
        (f"```json {ARRAY}```", "fence"),  # 여는 펜스 뒤 줄바꿈 없음
        ('```\n[{"text": "기하학적 기하학적 기하', "json"),  # 잘린 응답 (닫는 펜스 없음)
        ('[{"text": "x", "evidence": []},]', "json"),
        ("자유 텍스트 응답", "json"),
        ("", "json"),
        ('{"text": "x", "evidence": []}', "schema"),  # 배열이 아님
        ('[{"evidence": []}]', "schema"),  # text 없음
        ('[{"text": "x", "evidence": "a:1"}]', "schema"),  # evidence 가 목록이 아님
        ('["문장"]', "schema"),
    ],
)
def test_rejections_are_classified(raw, status):
    result = parse_sentences(raw)
    assert result.status == status and result.sentences == []
    assert result.raw_chars == len(raw)


def test_empty_array_is_ok_with_no_sentences():
    assert parse_sentences("[]").status == "ok"


# ── 근거 id: <doc id="..."> 정확히 그 형태만 되돌린다 ────────
def test_exact_doc_tag_is_normalized():
    assert normalize_evidence_id('<doc id="openalex:W1#0">') == "openalex:W1#0"


@pytest.mark.parametrize(
    "ev",
    [
        "<doc id='openalex:W1#0'>",  # 작은따옴표
        '<doc id="openalex:W1#0"></doc>',  # 닫는 태그까지
        '<doc id="openalex:W1#0" >',  # 공백
        ' <doc id="openalex:W1#0">',  # 앞 공백
        '<ref id="openalex:W1#0">',  # 다른 태그
        '<DOC id="openalex:W1#0">',
        "[openalex:W1#0](https://openalex.org/W1)",  # 마크다운 링크
        'doc id="openalex:W1#0"',
        '<doc id="">',
    ],
)
def test_other_shapes_are_left_untouched(ev):
    assert normalize_evidence_id(ev) == ev


def test_enforce_keeps_normalized_tag_and_drops_other_shapes():
    allowed = {"openalex:W1#0", "openalex:W1"}
    section = Section(
        key="method",
        sentences=[
            Sentence(text="태그로 인용", evidence=['<doc id="openalex:W1#0">']),
            Sentence(text="링크로 인용", evidence=["[W1](https://openalex.org/W1)"]),
            Sentence(text="태그 안이 위조 id", evidence=['<doc id="evil:9">']),
            Sentence(text="중복", evidence=['<doc id="openalex:W1#0">', "openalex:W1#0"]),
        ],
    )
    kept, dropped = enforce_section_evidence(section, allowed, evidence_required=False)
    assert [(s.text, s.evidence) for s in kept.sentences] == [
        ("태그로 인용", ["openalex:W1#0"]),
        ("중복", ["openalex:W1#0"]),
    ]
    assert len(dropped) == 2
