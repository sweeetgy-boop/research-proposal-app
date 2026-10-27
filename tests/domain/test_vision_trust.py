"""P3 ⑤ 신뢰도 규칙 — JSON 만 파싱, OCR 에 없는 수치 거부, 미확인 문장 표식."""

import json

import pytest

from rra.domain.models.vision import OcrLine, OcrResult, VisionReading
from rra.domain.rules.vision_trust import (
    CHECK_MARK,
    VisionParseError,
    evidence_numbers,
    mark_unconfirmed,
    parse_reading,
    verify_numbers,
)


def ocr(*lines: str) -> OcrResult:
    return OcrResult(lines=[OcrLine(text=t, confidence=0.9) for t in lines])


def test_parse_accepts_object_and_strips_code_fence():
    data = {
        "image_type": "표",
        "title": "t",
        "text": "a\nb",
        "structure": {"rows": [["1"]]},
        "summary": "s",
    }
    r = parse_reading("```json\n" + json.dumps(data, ensure_ascii=False) + "\n```")
    assert r.image_type == "표" and r.structure == {"rows": [["1"]]} and r.text == "a\nb"
    assert r.uncertain is False and r.trust == "untrusted"


@pytest.mark.parametrize("text", ["표입니다: {}", "[]", "", "{'a': 1}", '설명 뒤 JSON {"a":1}'])
def test_parse_rejects_non_json_or_non_object(text):
    with pytest.raises(VisionParseError):
        parse_reading(text)


def test_unknown_image_type_becomes_other_and_aliases_map():
    assert parse_reading('{"image_type": "사진"}').image_type == "기타"
    assert parse_reading('{"image_type": "table"}').image_type == "표"
    assert parse_reading('{"image_type": "조직도"}').image_type == "체계도·조직도·흐름도"


def test_non_dict_structure_and_overlong_fields_are_normalized_not_rejected():
    r = parse_reading(json.dumps({"structure": ["x"], "title": "t" * 500, "text": 12}))
    assert r.structure == {} and len(r.title) == 300 and r.text == "12"


def test_numbers_not_in_ocr_are_unconfirmed_and_excluded_from_evidence():
    reading = VisionReading(
        image_type="표",
        text="수송인원 1,234만명, 증가율 3.5%",
        structure={"rows": [["매출", "5,600억원"]]},
        summary="2024년 실적",
    )
    confirmed, unconfirmed = verify_numbers(
        reading, ocr("수송인원 1234만명", "증가율 3.5%", "2024년")
    )
    assert confirmed == ["1,234", "3.5%", "2024년"]  # "만명" 은 numbers.py 단위가 아니다 → bare
    assert unconfirmed == ["5,600억원"]
    assert evidence_numbers(reading, ocr("1,234만명")) == ["1,234"]


def test_unit_conversion_counts_as_same_number():
    reading = VisionReading(text="사업기간 12개월")
    assert verify_numbers(reading, ocr("1년 이내")) == (["12개월"], [])


def test_without_ocr_every_number_is_unconfirmed():
    reading = VisionReading(text="2030년까지 30% 감축")
    assert verify_numbers(reading, None) == ([], ["2030년", "30%"])


def test_mark_unconfirmed_prefixes_only_sentences_with_those_numbers():
    text = "수송인원은 1,234만명이다.\n매출은 5,600억원이다.\n증가율은 3.5% 다."
    out = mark_unconfirmed(text, ["5,600억원"])
    assert out.splitlines() == [
        "수송인원은 1,234만명이다.",
        f"{CHECK_MARK} 매출은 5,600억원이다.",
        "증가율은 3.5% 다.",
    ]
    assert mark_unconfirmed(text, []) == text
