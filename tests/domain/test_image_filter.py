"""P3 ① 장식 거르기 — 크기·이름·alt·반복·형식 규칙과 이유별 집계."""

from rra.domain.models.vision import ImageItem
from rra.domain.rules.image_filter import ImageFilterConfig, classify, filter_images


def it(**kw) -> ImageItem:
    base = {"sha256": "a" * 64, "path": "img/chart.png", "width": 800, "height": 500}
    base.update(kw)
    return ImageItem(**base)


def test_content_image_is_kept():
    assert classify(it()) is None


def test_tiny_icon_and_wide_banner_are_excluded_by_size():
    assert classify(it(width=32, height=32)) == "tiny"
    assert classify(it(width=1200, height=150)) == "aspect"
    assert classify(it(width=150, height=2000)) == "aspect"


def test_name_patterns_catch_logo_icon_button_banner_bg_sprite():
    for name in (
        "logo_korail.png",
        "ico_search.png",
        "btn_more.png",
        "main_banner.jpg",
        "bg_top.png",
        "sprite.png",
    ):
        assert classify(it(path=f"img/{name}")) == "name_pattern", name
    assert classify(it(path="img/data.png", url="https://x/common/logo.png?v=2")) == "name_pattern"


def test_alt_patterns_and_photo_alt_are_excluded():
    assert classify(it(alt="한국철도공사 로고")) == "alt_pattern"
    assert classify(it(alt="행사 사진")) == "alt_pattern"
    assert classify(it(alt="2024년 수송실적 표")) is None


def test_repeated_hash_across_pages_is_common_decoration():
    assert classify(it(repeat_pages=4)) == "repeated"
    assert classify(it(repeat_pages=3)) is None


def test_svg_gif_and_oversized_are_excluded():
    assert classify(it(mime="image/svg+xml")) == "format"
    assert classify(it(path="img/anim.gif")) == "format"
    assert classify(it(bytes=20 * 1024 * 1024)) == "too_large"


def test_unknown_size_skips_size_rules():
    assert classify(it(width=None, height=None)) is None


def test_filter_report_counts_reasons_and_counts_repeats_over_pages():
    same = "b" * 64
    items = [
        it(),
        it(sha256=same, path="img/footer.png", page_url="https://x/1"),
        it(sha256=same, path="img/footer.png", page_url="https://x/2"),
        it(sha256=same, path="img/footer.png", page_url="https://x/3"),
        it(sha256=same, path="img/footer.png", page_url="https://x/4"),
        it(sha256="c" * 64, path="img/ico_x.png"),
    ]
    report = filter_images(items, ImageFilterConfig(max_repeat_pages=3))
    assert [i.sha256 for i in report.kept] == ["a" * 64]
    assert report.counts == {
        "kept": 1,
        "excluded": 5,
        "repeated": 1,
        "duplicate": 3,
        "name_pattern": 1,
    }


def test_config_from_dict_overrides_and_lowercases_patterns():
    cfg = ImageFilterConfig.from_dict(
        {"min_width": 300, "name_patterns": ["LOGO"], "alt_patterns": []}
    )
    assert cfg.min_width == 300 and cfg.name_patterns == ("logo",)
    assert cfg.alt_patterns == ()  # 빈 목록은 "alt 규칙 없음"
    assert classify(it(width=200, height=200), cfg) == "tiny"
