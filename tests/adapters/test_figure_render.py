"""그림 밑그림 렌더러(adapters/figures) — SVG 템플릿·줄바꿈·무늬·PNG 변환·이미지 축소."""

from __future__ import annotations

import importlib.util
import io
import re
import sys
from pathlib import Path
from xml.sax.saxutils import unescape

import pytest
import yaml
from defusedxml import ElementTree
from PIL import Image

from rra.adapters.figures import SvgFigureRenderer, image_size, render_svg, shrink_image, svg_to_png
from rra.adapters.figures.render import fit_text, text_width, wrap_text
from rra.domain.models.figure import FIGURE_KINDS, parse_spec
from rra.domain.rules.figures import NO_INFO, texts_of

ROOT = Path(__file__).resolve().parents[2]
FONTS = sorted((ROOT / "config/templates/figures/fonts").glob("Pretendard-*.otf"))
_TOOL = ROOT / "tools/figure_samples.py"


def _load_samples() -> dict:
    spec = importlib.util.spec_from_file_location("figure_samples_tool", _TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("figure_samples_tool", mod)
    spec.loader.exec_module(mod)
    return mod.SAMPLE_SPECS


SAMPLES = _load_samples()
CONFIG = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))
PALETTE = CONFIG["palette"]
ASPECTS = CONFIG["aspect"]
_ENT = {"&quot;": '"'}


def _plain(svg: str) -> str:
    return unescape(svg, _ENT)


def _svg_size(svg: str) -> tuple[int, int]:
    root = ElementTree.fromstring(svg)
    return int(root.get("width")), int(root.get("height"))


# ── SVG 공통 ──────────────────────────────────────────────
@pytest.mark.parametrize("kind", FIGURE_KINDS)
def test_render_every_kind(kind: str) -> None:
    spec = parse_spec(kind, SAMPLES[kind])
    svg = render_svg(spec, palette=PALETTE, aspect=ASPECTS[kind])
    root = ElementTree.fromstring(svg)  # 잘 짜인 XML
    assert root.tag.endswith("svg")
    plain = _plain(svg)
    for t in texts_of(spec):
        assert t in plain, (kind, t)
    assert "<script" not in svg and "<image" not in svg and "href=" not in svg
    assert "<style" not in svg
    assert 'font-family="Pretendard"' in svg
    w, h = _svg_size(svg)
    a, b = (int(x) for x in ASPECTS[kind].split(":"))
    assert w == 1600 and h == round(1600 * b / a)


def test_width_px_and_viewbox() -> None:
    spec = parse_spec("concept", SAMPLES["concept"])
    svg = render_svg(spec, palette=PALETTE, aspect="16:9", width_px=800)
    assert _svg_size(svg) == (800, 450)
    assert 'viewBox="0 0 1600 900"' in svg


def test_untrusted_text_is_escaped() -> None:
    data = {
        "boxes": [
            {"label": '<script>alert("x")</script>', "lines": ["a & b < c"]},
            {"label": "문제"},
            {"label": "해결 방안"},
            {"label": "기대효과"},
        ]
    }
    spec = parse_spec("concept", data)
    svg = render_svg(spec, palette=PALETTE)
    assert "<script" not in svg
    assert "&lt;script&gt;" in svg
    ElementTree.fromstring(svg)
    assert 'alert("x")' in _plain(svg)


def test_caption_not_drawn_in_body() -> None:
    spec = parse_spec("process", SAMPLES["process"])
    svg = render_svg(spec, palette=PALETTE, caption="그림 캡션 문구")
    assert svg.count("그림 캡션 문구") <= 2  # <title> 과 aria-label 뿐
    body = svg.split("</defs>", 1)[-1]
    assert "그림 캡션 문구" not in body


def test_renderer_class_uses_aspect_per_kind() -> None:
    r = SvgFigureRenderer(palette=PALETTE, aspects=ASPECTS, font_files=FONTS)
    svg = r.svg(parse_spec("schedule", SAMPLES["schedule"]))
    assert _svg_size(svg) == (1600, round(1600 * 9 / 21))


# ── 줄바꿈·크기 ──────────────────────────────────────────
def test_wrap_text_prefers_spaces_then_chars() -> None:
    assert wrap_text("궤도 틀림 점검을 주기 순회로 수작업 측정", 10) == [
        "궤도 틀림 점검을",
        "주기 순회로 수작업",
        "측정",
    ]
    assert wrap_text("가나다라마바사아자차카타파하", 5) == ["가나다라마", "바사아자차", "카타파하"]
    assert wrap_text("", 5) == [""]
    assert wrap_text("짧다", 40) == ["짧다"]


def test_fit_text_shrinks_and_keeps_within_box() -> None:
    long = (
        "영업열차 탑재 관성·가속도 센서 기반 궤도 상태 상시 감지 및 구간별 지수 산출 체계"  # 38자+
    )
    lines, fs = fit_text(long, 280, 120, 30)
    assert len(lines) >= 2
    assert fs <= 30
    assert all(text_width(ln, fs) <= 280 for ln in lines)


def test_long_label_wraps_into_tspans_within_box() -> None:
    long = "영업열차 탑재 관성·가속도 센서 기반 궤도 상태 상시 감지 및 지수 산출"
    assert len(long) >= 38
    data = {
        "stages": [{"name": long, "outputs": ["산출물 하나"]}]
        + [{"name": f"단계 {i}"} for i in range(2, 6)]
    }
    spec = parse_spec("process", data)
    svg = render_svg(spec, palette=PALETTE)
    assert long in _plain(svg)
    m = re.search(r'<text[^>]*aria-label="([^"]*)"[^>]*>(.*?)</text>', svg)
    assert m and unescape(m.group(1), _ENT) == long
    spans = re.findall(r"<tspan[^>]*>(.*?)</tspan>", m.group(2))
    assert len(spans) >= 2
    assert "".join(unescape(s) for s in spans).replace(" ", "") == long.replace(" ", "")
    # 상자 폭(5단계 → 상자 ≈ 258px, 안쪽 234px) 안에 모든 줄이 들어간다
    fs = float(re.search(r'font-size="([\d.]+)"', m.group(0)).group(1))
    assert all(text_width(unescape(s), fs) <= 258 for s in spans)


# ── 종류별 ──────────────────────────────────────────────
def test_stat_chart_patterns_and_value_texts() -> None:
    spec = parse_spec("stat_chart", SAMPLES["stat_chart"])
    svg = render_svg(spec, palette=PALETTE)
    assert len(re.findall(r"<pattern id=", svg)) >= 2  # 3 계열 → dots·hatch
    assert 'fill="url(#pat-dots' in svg and 'fill="url(#pat-hatch' in svg
    assert "1,512" in svg and "2,904" in svg
    assert "출처: 궤도 유지보수 통계, 2024년, 12쪽" in svg
    assert "(단위: 건)" in svg


def test_stat_chart_line_uses_dasharray_and_fallback_values() -> None:
    data = dict(SAMPLES["stat_chart"], chart="line", value_texts=[])
    spec = parse_spec("stat_chart", data)
    svg = render_svg(spec, palette=PALETTE)
    assert "<polyline" in svg
    assert 'stroke-dasharray="6 3"' in svg
    assert ">1512건<" in svg


def test_comparison_missing_cell_shows_no_info_and_accent() -> None:
    spec = parse_spec("comparison", SAMPLES["comparison"])
    svg = render_svg(spec, palette=PALETTE)
    assert NO_INFO in svg
    assert f'stroke="{PALETTE["accent"]}"' in svg
    assert "제안 과제" in svg and "기존 과제" in svg


def test_schedule_axis_ticks() -> None:
    spec = parse_spec("schedule", SAMPLES["schedule"])
    svg = render_svg(spec, palette=PALETTE, aspect="21:9")
    for mth in (1, 12, 24):
        assert f">{mth}<" in svg
    assert "1~4개월" in svg and "20~24개월" in svg
    long = parse_spec(
        "schedule",
        {
            "total_months": 60,
            "stages": [
                {"name": "가", "start_month": 1, "end_month": 30},
                {"name": "나", "start_month": 31, "end_month": 60},
            ],
        },
    )
    svg = render_svg(long, palette=PALETTE)
    assert ">60<" in svg and ">3<" in svg and ">4<" not in svg  # 24개월 초과는 3개월 눈금


def test_concept_and_roadmap_have_arrows() -> None:
    for kind in ("concept", "roadmap", "process"):
        svg = render_svg(parse_spec(kind, SAMPLES[kind]), palette=PALETTE)
        assert "<marker id=" in svg and "marker-end=" in svg


# ── PNG ─────────────────────────────────────────────────
@pytest.mark.skipif(not FONTS, reason="번들 폰트 없음")
def test_svg_to_png_pixel_width_and_limit() -> None:
    spec = parse_spec("concept", SAMPLES["concept"])
    svg = render_svg(spec, palette=PALETTE)
    png = svg_to_png(svg, font_files=FONTS, zoom=1.0)
    assert png[:4] == b"\x89PNG"
    assert len(png) <= 512_000
    assert image_size(png) == (1600, 900)
    assert Image.open(io.BytesIO(png)).size == (1600, 900)


@pytest.mark.skipif(not FONTS, reason="번들 폰트 없음")
def test_svg_to_png_huge_zoom_still_fits() -> None:
    spec = parse_spec("stat_chart", SAMPLES["stat_chart"])
    svg = render_svg(spec, palette=PALETTE)
    png = svg_to_png(svg, font_files=FONTS, zoom=6.0, max_bytes=250_000)
    assert png[:4] == b"\x89PNG"
    assert len(png) <= 250_000
    w, _ = image_size(png)
    assert w < 1600 * 6


@pytest.mark.skipif(not FONTS, reason="번들 폰트 없음")
def test_renderer_class_png() -> None:
    r = SvgFigureRenderer(palette=PALETTE, aspects=ASPECTS, font_files=FONTS, dpi=96)
    png = r.png(r.svg(parse_spec("roadmap", SAMPLES["roadmap"])))
    assert png[:4] == b"\x89PNG" and image_size(png) == (1600, 900)


# ── 이미지 축소 ──────────────────────────────────────────
def _noise_jpeg(w: int, h: int) -> bytes:
    import random

    rnd = random.Random(7)
    im = Image.frombytes("RGB", (w, h), bytes(rnd.getrandbits(8) for _ in range(w * h * 3)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_shrink_image_jpeg_noise() -> None:
    data = _noise_jpeg(3000, 1700)
    assert len(data) > 512_000
    out, mime = shrink_image(data, "image/jpeg")
    assert mime == "image/jpeg" and len(out) <= 512_000
    w, h = image_size(out)
    assert max(w, h) <= 2000 and abs(w / h - 3000 / 1700) < 0.01


def test_shrink_image_png_keeps_png_when_small() -> None:
    im = Image.new("RGBA", (300, 200), (255, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out, mime = shrink_image(buf.getvalue(), "image/png")
    assert mime == "image/png" and image_size(out) == (300, 200)
    assert Image.open(io.BytesIO(out)).getpixel((0, 0)) == (255, 255, 255)  # 투명 → 흰 배경


def test_open_failures() -> None:
    with pytest.raises(ValueError, match="열 수 없습니다"):
        image_size(b"not an image")
    with pytest.raises(ValueError, match="열 수 없습니다"):
        shrink_image(b"\x89PNG\r\n\x1a\n garbage", "image/png")


# ── v2: 분석 기법 표·경제성, As-Is/To-Be 흑백 구분 ─────────────────
@pytest.mark.parametrize("key", ["pugh", "cost_benefit"])
def test_technique_matrix_and_ledger_samples_draw_every_text(key: str) -> None:
    mod = sys.modules["figure_samples_tool"]
    spec = parse_spec("technique", mod.TECHNIQUE_SAMPLES[key])
    svg = render_svg(spec, palette=PALETTE, aspect="16:9")
    plain = _plain(svg)
    for t in texts_of(spec):
        assert t in plain, (key, t)
    ElementTree.fromstring(svg)


def test_as_is_to_be_uses_dash_and_pattern_not_colour_only() -> None:
    spec = parse_spec("as_is_to_be", SAMPLES["as_is_to_be"])
    svg = render_svg(spec, palette=PALETTE, aspect="16:9")
    assert 'stroke-dasharray="14 8"' in svg  # 왼쪽(현재) 점선 테두리
    assert "pat-hatch" in svg and "pat-dots" in svg  # 쪽마다 다른 무늬
    assert "<polygon" in svg  # 가운데 화살표
