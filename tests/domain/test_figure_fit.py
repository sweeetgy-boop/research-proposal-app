"""[23] 그림 모양 규칙 — 종류별 가로 비율, 본문 폭·높이 상한 → 넓은 비율, 글자 크기 계산,
OCR 어림. 칸 글자를 잘라 줄이는 길은 없다(2026-10-29, ADR 0044)."""

import pytest

from rra.domain.models.figure import display_name, parse_spec
from rra.domain.rules import figure_fit as fit
from rra.domain.rules import figures as rules
from tests.figure_v2_helpers import AS_IS

WIDE = {"16:9", "21:9"}
LONG = {"21:9", "4:1"}


def _schedule(n: int, name: str = "현황 분석") -> dict:
    return {
        "total_months": 24,
        "stages": [
            {"name": name, "start_month": 1 + i * 5, "end_month": 5 + i * 5} for i in range(n)
        ],
    }


# ── 비율 ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("kind", "data", "allowed"),
    [
        ("as_is_to_be", AS_IS, WIDE),
        ("schedule", _schedule(4), LONG),
        ("schedule", _schedule(7, "운영 지침화 및 결과 보고서 작성"), LONG),
        (
            "roadmap",
            {"metrics": [{"name": "정확도", "target": "90%"}], "stages": [{"name": "a"}] * 2},
            LONG,
        ),
        ("concept", {"boxes": [{"label": "현황", "lines": ["a"]}] * 4}, WIDE),
        ("process", {"stages": [{"name": "a", "outputs": ["x", "y"]}] * 3}, WIDE),
    ],
)
def test_every_kind_gets_a_wide_aspect(kind, data, allowed):
    aspect = rules.choose_aspect(parse_spec(kind, data))
    assert aspect in allowed and fit.ratio_value(aspect) >= 16 / 9 - 1e-6


def test_schedule_is_4_to_1_when_short_and_21_9_when_long():
    assert rules.choose_aspect(parse_spec("schedule", _schedule(4))) == "4:1"
    assert rules.choose_aspect(parse_spec("schedule", _schedule(5))) == "21:9"
    long = _schedule(3, "센서 체계 설계 및 시작품 제작")
    assert rules.choose_aspect(parse_spec("schedule", long)) == "21:9"


def test_api_aspect_maps_4_to_1_to_21_9_and_keeps_api_ratios():
    assert fit.api_aspect("4:1") == "21:9"
    assert fit.api_aspect("16:9") == "16:9" and fit.api_aspect("21:9") == "21:9"


def test_legacy_narrow_aspects_are_raised_to_wide():
    assert fit.wide_aspect("technique", "4:3") == "16:9"
    assert fit.wide_aspect("schedule", "16:9") == "21:9"
    assert fit.wide_aspect("as_is_to_be", "21:9") == "21:9"


def test_wider_and_narrower_walk_the_allowed_list():
    assert fit.wider("as_is_to_be", "16:9") == "21:9" and fit.wider("as_is_to_be", "21:9") is None
    assert fit.wider("schedule", "21:9") == "4:1"
    assert (
        fit.narrower("as_is_to_be", "21:9") == "16:9" and fit.narrower("schedule", "21:9") is None
    )


# ── 본문 폭·높이 상한 ─────────────────────────────────────
def test_default_frame_is_the_real_form_body():
    frame = fit.BodyFrame()
    assert round(frame.width_mm, 1) == 153.8 and round(frame.max_height_mm, 1) == 99.0
    assert fit.fits(frame, "16:9") and fit.fits(frame, "21:9")


def test_height_over_one_third_page_moves_to_a_wider_ratio():
    short_page = fit.BodyFrame(width_mm=153.8, page_height_mm=200.0)  # 상한 66.7mm
    assert not fit.fits(short_page, "16:9")
    aspect, widened = fit.fit_aspect_for_frame("as_is_to_be", "16:9", short_page)
    assert (aspect, widened) == ("21:9", True)
    tiny = fit.BodyFrame(width_mm=153.8, page_height_mm=90.0)  # 21:9 도 넘는다 → 가장 넓은 값
    assert fit.fit_aspect_for_frame("as_is_to_be", "16:9", tiny) == ("21:9", True)
    assert fit.fit_aspect_for_frame("schedule", "21:9", tiny) == ("4:1", True)


def test_make_fit_records_width_height_ratio_and_text_check():
    frame = fit.BodyFrame()
    f = fit.make_fit(frame, "21:9", min_pt=9.3)
    assert (f.width_mm, f.height_mm, f.ratio, f.fits, f.text_ok) == (
        153.8,
        65.9,
        "21:9",
        True,
        True,
    )
    assert fit.make_fit(frame, "16:9", min_pt=8.2).text_ok is False
    assert fit.make_fit(frame, "16:9", min_pt=8.99).text_ok is True  # 33.0 단위 반올림


# ── 글자 크기 ─────────────────────────────────────────────
def test_font_units_and_points_at_body_width():
    w = 153.8
    assert round(fit.font_pt(30, w), 1) == 8.2  # 예전 상자 글자 30 = 8.2pt (작다)
    assert round(fit.font_pt(37, w), 1) == 10.1
    assert round(fit.min_font_units(9.0, w), 1) == 33.0
    assert fit.min_font_units(9.0, 100.0) > fit.min_font_units(9.0, w)  # 좁은 칸이면 하한이 커진다


def test_svg_metrics_reads_smallest_font_and_overflow_flag():
    svg = (
        '<svg data-overflow="2"><text font-size="42.0">a</text>'
        '<text font-size="33.1">b</text></svg>'
    )
    m = fit.svg_metrics(svg)
    assert m.min_font == 33.1 and m.overflow == 2
    assert fit.svg_metrics("<svg></svg>") == fit.SvgMetrics(None, 0)


def test_ocr_estimate_uses_lines_that_match_spec_texts():
    texts = ["궤도 틀림을 주기 순회로 수작업 측정", "현황"]
    lines = [
        ("궤도 틀림을 주기 순회로", 0.05),  # 그림 높이의 5% → 65.9mm × 0.05 = 3.3mm
        ("현황", 0.06),
        ("¶", 0.001),  # 잡음 — 무시
        ("관계없는 글자", 0.01),  # 명세에 없는 글자 — 무시
    ]
    pt = fit.estimate_ocr_pt(lines, 65.9, texts, box_em=1.2)
    assert pt == round(0.05 * 65.9 * fit.PT_PER_MM / 1.2, 1)
    assert fit.estimate_ocr_pt([("관계없음", 0.1)], 65.9, texts, box_em=1.2) is None


# ── 글자 줄이기는 없다 (2026-10-29, ADR 0044) ─────────────────────
def test_truncating_helpers_are_retired():
    """칸 글자를 띄어쓰기 자리에서 잘라 줄이던 길(22 → 16자)은 없앴다 — 9pt 미달이면 유스케이스가
    칸 글자를 더 짧은 완결 구절로 다시 쓴다(rewrite_texts). 이름표 두 글자(정해진 낱말)만 남는다."""
    for name in ("shorten_spec", "clip_words", "SHORTEN_LEVELS", "MAX_SHORTEN"):
        assert not hasattr(fit, name), name
    assert not hasattr(rules, "clip_text")
    short, n = fit.shorten_tags(parse_spec("as_is_to_be", AS_IS))
    assert n == 2 and [it.tag for it in short.to_be] == ["목표", "방안", "효과"]
    assert [it.text for it in short.to_be] == [
        it["text"] for it in AS_IS["to_be"]
    ]  # 칸 글자 그대로


def test_display_name_is_korean_without_codes():
    assert display_name("as_is_to_be") == "현재·연구 후 비교 그림"
    assert display_name("technique", "SWOT 분석") == "분석 기법 그림 – SWOT 분석"
    assert display_name("schedule") == "추진 일정표"
    for kind in ("as_is_to_be", "technique", "concept", "process", "schedule", "roadmap"):
        assert "As-Is" not in display_name(kind) and "_" not in display_name(kind)


def test_relative_estimate_cancels_the_ocr_box_ratio():
    svg = (
        '<svg><text font-size="37.0">현황</text>'
        '<text font-size="34.0" aria-label="궤도 틀림을 주기 순회로 측정">'
        "<tspan>궤도 틀림을</tspan><tspan>주기 순회로 측정</tspan></text></svg>"
    )
    pts = fit.svg_text_pts(svg, 153.8)
    assert set(pts) == {"현황", "궤도 틀림을 주기 순회로 측정"}
    base = [("현황", 0.040), ("주기 순회로 측정", 0.035)]
    image = [("현황", 0.030), ("주기 순회로 측정", 0.035)]  # 현황만 0.75배로 작게 그렸다
    got = fit.estimate_relative_pt(
        base, image, base_height_mm=65.9, image_height_mm=65.9, text_pts=pts
    )
    assert got == round(fit.font_pt(37, 153.8) * 0.75, 1)
    assert (
        fit.estimate_relative_pt([], image, base_height_mm=1, image_height_mm=1, text_pts=pts)
        is None
    )


def test_pixel_ratio_label():
    assert fit.pixel_ratio_label("21:9", (2100, 900)) == "21:9"
    assert fit.pixel_ratio_label("4:1", (3200, 1000)) == "3.20:1"
