"""OCR 결과로 사진 거르기 — 순수 규칙 (2026-10-27)."""

from rra.domain.rules.photo_filter import PhotoRule, is_photo, ocr_signals, photo_meta


def _ocr(*lines: str, ok: bool = True) -> dict:
    return {"ok": ok, "result": {"lines": [{"text": t, "confidence": 0.9} for t in lines]}}


def test_signals_parse_store_format_and_failures():
    s = ocr_signals(_ocr("코레일 전경", "2024년 12월"))
    assert (s.ok, s.lines, s.digits > 0) == (True, 2, True)
    assert s.chars == len("코레일전경2024년12월")
    assert ocr_signals(None).ok is False
    assert ocr_signals(_ocr(ok=False)).ok is False
    assert ocr_signals({"lines": [{"text": "a"}]}).chars == 1  # result 없이 바로 lines


def test_photo_when_little_text_and_no_structure_signals():
    rule = PhotoRule()
    assert is_photo(ocr_signals(_ocr()), "press", rule) is True  # 글자 0
    assert is_photo(ocr_signals(_ocr("코레일")), "press", rule) is True
    assert is_photo(ocr_signals(_ocr("코레일", "KORAIL")), "other", rule) is True


def test_not_photo_with_numbers_structure_many_lines_or_exempt_group():
    rule = PhotoRule()
    assert is_photo(ocr_signals(_ocr("2024")), "press", rule) is False  # 숫자
    assert is_photo(ocr_signals(_ocr("매출 →")), "press", rule) is False  # 도형 기호
    assert (
        is_photo(ocr_signals(_ocr("가", "나", "다")), "press", rule) is False
    )  # 짧은 라벨 여러 줄
    assert is_photo(ocr_signals(_ocr("경영목표 " * 10)), "press", rule) is False  # 글자 많음
    assert is_photo(ocr_signals(_ocr()), "strategy", rule) is False  # 예외 그룹(체계도일 수 있음)
    assert is_photo(ocr_signals(None), "press", rule) is False  # OCR 없음 — 보수적
    assert is_photo(ocr_signals(_ocr()), "press", PhotoRule(enabled=False)) is False


def test_rule_from_config_and_meta_keeps_only_alt_caption_title():
    rule = PhotoRule.from_dict({"max_chars": 5, "exempt_groups": ["strategy"], "max_lines": 1})
    assert (rule.max_chars, rule.exempt_groups, rule.max_lines) == (5, ("strategy",), 1)

    class It:
        alt, caption, page_title = "사진 설명", None, "보도자료"

    meta = photo_meta(It(), ocr_signals(_ocr("코레일")))
    assert meta == {
        "alt": "사진 설명",
        "caption": "",
        "page_title": "보도자료",
        "ocr_chars": 3,
        "ocr_lines": 1,
    }
