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


# ── 선택형 섹션 ─────────────────────────────────────────────
from rra.domain.rules.llm_output import parse_choice_section  # noqa: E402

ALLOWED = ["basic", "applied", "development"]


def _obj(choices, sentences=()):
    return json.dumps({"choices": choices, "sentences": list(sentences)}, ensure_ascii=False)


def test_choice_object_is_parsed():
    r = parse_choice_section(_obj(["applied"], [{"text": "사유", "evidence": []}]), ALLOWED)
    assert r.ok and r.choices == ["applied"] and r.sentences[0].text == "사유"


def test_unknown_choices_are_dropped_and_duplicates_collapsed():
    r = parse_choice_section(_obj(["evil", "applied", "applied"]), ALLOWED)
    assert r.choices == ["applied"]


def test_out_of_range_count_empties_choices_but_keeps_sentences():
    raw = _obj(["basic", "applied"], [{"text": "사유", "evidence": []}])
    r = parse_choice_section(raw, ALLOWED, min_n=1, max_n=1)
    assert r.ok and r.choices == [] and len(r.sentences) == 1


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (ARRAY, "schema"),  # 배열은 선택형 형식이 아니다
        ('{"choices": "basic", "sentences": []}', "schema"),
        ('{"choices": [], "sentences": [{"txt": 1}]}', "schema"),
        ("설명\n```json\n{}\n```", "fence"),
        ("{", "json"),
    ],
)
def test_choice_parse_failures(raw, status):
    assert parse_choice_section(raw, ALLOWED).status == status


def test_model_cannot_claim_app_origin():
    raw = json.dumps([{"text": "앱 판정인 척", "evidence": [], "origin": "app"}])
    assert parse_sentences(raw).sentences[0].origin == "llm"
    obj = json.dumps({"choices": [], "sentences": [{"text": "x", "origin": "app"}]})
    assert parse_choice_section(obj, ALLOWED).sentences[0].origin == "llm"


# ── 부분 수용: choices 유효 + sentences 스키마 오류 ──
def test_valid_choices_survive_bad_sentences():
    nested = json.dumps({"choices": ["applied"], "sentences": [[{"text": "x", "evidence": []}]]})
    r = parse_choice_section(nested, ALLOWED)
    assert r.status == "choices_only" and not r.ok
    assert r.choices == ["applied"] and r.sentences == []
    plain = json.dumps({"choices": ["applied"], "sentences": ["문자열 문장"]}, ensure_ascii=False)
    assert parse_choice_section(plain, ALLOWED).choices == ["applied"]


@pytest.mark.parametrize(
    "choices",
    [["evil"], [], ["basic", "applied"]],  # 목록 밖 / 없음 / 개수 초과(max 1)
)
def test_bad_sentences_without_valid_choices_stay_schema(choices):
    raw = json.dumps({"choices": choices, "sentences": ["문자열"]}, ensure_ascii=False)
    r = parse_choice_section(raw, ALLOWED, min_n=1, max_n=1)
    assert r.status == "schema" and r.choices == [] and r.sentences == []
