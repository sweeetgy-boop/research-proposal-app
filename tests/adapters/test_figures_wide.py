"""[23] 그림 가로 배치·글자 하한(밑그림), 흰 여백 자르기·비율 맞춤(PNG), 양식 본문 폭 읽기·HWPX
그림 크기와
맞춤 기록(placement.fit)."""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from defusedxml import ElementTree as ET
from PIL import Image

from rra.adapters.figures import fit_aspect, render_svg, svg_to_png
from rra.adapters.figures.png import pad_to_aspect
from rra.adapters.figures.render import MIN_FONT
from rra.adapters.rendering import HwpxRenderer, SlotMap
from rra.adapters.rendering.hwpx_geometry import body_width
from rra.domain.models import Confirmation, Draft, ProposalRequest, Section, Sentence
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.rules import figure_fit as fit
from rra.domain.rules.figures import texts_of

ROOT = Path(__file__).parents[2]
CONFIG = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))
PALETTE = CONFIG["palette"]
FONTS = sorted((ROOT / "config/templates/figures/fonts").glob("*.otf"))
TEMPLATE = ROOT / "tests/fixtures/hwpx/proposal_template_min.hwpx"
REAL_FORM = ROOT / "config/templates/proposal_korail.hwpx"
SLOTS = ROOT / "config/templates/proposal_korail.slots.yaml"
NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
sys.path.insert(0, str(ROOT / "tools"))
from figure_samples import SAMPLE_SPECS, WIDE_SAMPLES  # noqa: E402


def _sizes(svg: str) -> list[float]:
    return [float(x) for x in re.findall(r'font-size="([\d.]+)"', svg)]


# ── 밑그림: 글자 하한·넘침 ───────────────────────────────────
@pytest.mark.parametrize("kind", list(SAMPLE_SPECS))
def test_no_text_below_9pt_at_body_width(kind):
    spec = parse_spec(kind, SAMPLE_SPECS[kind])
    svg = render_svg(spec, palette=PALETTE, aspect=fit.choose_aspect(spec))
    m = fit.svg_metrics(svg)
    assert min(_sizes(svg)) >= MIN_FONT
    assert fit.font_pt(m.min_font, fit.DEFAULT_BODY_WIDTH_MM) >= 9.0 - fit.PT_TOLERANCE
    assert m.overflow == 0, kind  # 샘플 글자는 하한 크기로 칸에 들어간다


def test_too_much_text_is_reported_as_overflow_not_shrunk_below_floor():
    data = {
        "as_is": [{"tag": "현황", "text": "가" * 30}] * 4,
        "to_be": [{"tag": "목표", "text": "나" * 30}] * 4,
        "solution": "다" * 30,
    }
    svg = render_svg(parse_spec("as_is_to_be", data), palette=PALETTE, aspect="4:1")
    assert fit.svg_metrics(svg).overflow > 0
    assert min(_sizes(svg)) >= MIN_FONT


def test_min_font_follows_the_body_width():
    spec = parse_spec("as_is_to_be", SAMPLE_SPECS["as_is_to_be"])
    narrow = fit.min_font_units(9.0, 100.0)  # 좁은 칸(100mm)이면 하한이 크다
    svg = render_svg(spec, palette=PALETTE, aspect="16:9", min_font=narrow)
    assert min(_sizes(svg)) >= round(narrow, 1)


# ── 밑그림: 가로 배치 ────────────────────────────────────────
def _group_heads(svg: str, n: int) -> list[tuple[float, float]]:
    """묶음 머리글 띠(높이 62) 의 (x, y)."""
    heads = re.findall(r'<rect x="([\d.]+)" y="([\d.]+)" width="[\d.]+" height="62.0"', svg)
    return [(float(x), float(y)) for x, y in heads][: n * 2 : 2]


def test_swot_is_four_cells_in_one_row():
    spec = parse_spec("technique", SAMPLE_SPECS["technique"])
    svg = render_svg(spec, palette=PALETTE, aspect="16:9", arrange="row")
    heads = _group_heads(svg, 4)
    assert len({y for _x, y in heads}) == 1 and len({x for x, _y in heads}) == 4


@pytest.mark.parametrize(
    ("name", "arrange", "rows"),
    [
        ("technique-pestel", "grid", 2),
        ("technique-force_field", "split", 1),
        ("technique-delphi", "flow", 1),
    ],
)
def test_technique_arrangements_are_horizontal(name, arrange, rows):
    kind, data = WIDE_SAMPLES[name]
    spec = parse_spec(kind, data)
    svg = render_svg(
        spec, palette=PALETTE, aspect=fit.choose_aspect(spec, arrange=arrange), arrange=arrange
    )
    heads = _group_heads(svg, len(spec.groups))
    assert len({y for _x, y in heads}) == rows
    for t in texts_of(spec):
        assert t in svg.replace("&amp;", "&")
    if arrange == "flow":
        assert svg.count("marker-end=") >= len(spec.groups) - 1  # 묶음 사이 화살표


def test_as_is_to_be_is_left_and_right_columns():
    spec = parse_spec("as_is_to_be", SAMPLE_SPECS["as_is_to_be"])
    svg = render_svg(spec, palette=PALETTE, aspect="21:9")
    panels = re.findall(
        r'<rect x="([\d.]+)" y="16.0" width="([\d.]+)" height="[\d.]+" rx="16"', svg
    )
    xs = sorted({float(x) for x, _w in panels})
    assert len(xs) == 2 and xs[1] > 800  # 왼쪽 단·오른쪽 단


def test_stat_chart_source_is_left_to_the_hwpx_caption_line():
    spec = parse_spec("stat_chart", SAMPLE_SPECS["stat_chart"])
    svg = render_svg(spec, palette=PALETTE, aspect="16:9")
    assert spec.source.caption() not in svg


# ── PNG: 흰 여백 자르기·비율 맞춤 ─────────────────────────────
def _png(w: int, h: int, box: tuple[int, int, int, int]) -> bytes:
    im = Image.new("RGB", (w, h), (255, 255, 255))
    im.paste((30, 60, 120), box)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_fit_aspect_trims_white_margins_and_pads_to_exact_ratio():
    data = _png(2100, 900, (100, 337, 2000, 562))  # 21:9 캔버스 가운데 4:1 띠
    out, mime = fit_aspect(data, "image/png", "4:1")
    w, h = Image.open(io.BytesIO(out)).size
    assert mime == "image/png" and abs(w / h - 4.0) < 0.01
    assert w >= 1900  # 좌우 여백을 잘랐다 (내용 폭 + 작은 여백)


def test_fit_aspect_keeps_in_between_ratio_without_adding_side_margins():
    data = _png(2100, 900, (400, 100, 1700, 800))  # 21:9 요청인데 내용은 약 1.86:1
    out, _ = fit_aspect(data, "image/png", "21:9", min_ratio=16 / 9)
    w, h = Image.open(io.BytesIO(out)).size
    assert 16 / 9 <= w / h < 21 / 9  # 좌우를 채워 21:9 로 만들지 않는다


def test_fit_aspect_pads_sides_when_content_is_taller_and_never_crops_text():
    data = _png(1600, 900, (700, 50, 900, 850))
    out, _ = fit_aspect(data, "image/png", "16:9", min_ratio=16 / 9)
    im = Image.open(io.BytesIO(out)).convert("RGB")
    assert abs(im.width / im.height - 16 / 9) < 0.01
    dark = sum(1 for px in im.getdata() if px[0] < 100)
    assert dark >= 200 * 800 * 0.9  # 내용은 그대로


def test_pad_to_aspect_puts_4_to_1_baseline_in_21_9_canvas():
    out = pad_to_aspect(_png(1600, 400, (0, 0, 1600, 400)), "21:9")
    w, h = Image.open(io.BytesIO(out)).size
    assert abs(w / h - 21 / 9) < 0.01 and w == 1600


# ── 양식 본문 폭 ──────────────────────────────────────────
def test_body_width_from_template_page_and_paragraph_margins():
    width, page_h = body_width(TEMPLATE.read_bytes())
    assert page_h > 80000 and 30000 < width < 59528


@pytest.mark.skipif(not REAL_FORM.is_file(), reason="실물 양식 없음 (미커밋)")
def test_real_form_body_width_is_153_8_mm():
    width, page_h = body_width(REAL_FORM.read_bytes())
    assert (width, page_h) == (43606, 84189)  # 59528 − 7086×2 − 단락 오른쪽 1750
    assert round(width / fit.HWPUNIT_PER_MM, 1) == 153.8


# ── HWPX 그림 크기·맞춤 기록 ─────────────────────────────────
def _renderer():
    slots = SlotMap.from_config(yaml.safe_load(SLOTS.read_text(encoding="utf-8")))
    return HwpxRenderer(slots, template_path=TEMPLATE)


def _draft():
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    sections = [
        Section(key="title", sentences=[Sentence(text="궤도 열화 예측")]),
        Section(key="method", sentences=[Sentence(text="방법 문장 하나.")]),
        Section(key="task_type", sentences=[], choices=["applied"]),
        Section(key="utilization", sentences=[], choices=["software"]),
    ]
    return Draft(run_id="r1", request=req, sections=sections, template="korail_rnd_proposal_v2024")


CONF = Confirmation(choices={"task_type": ["applied"], "utilization": ["software"]})


def _figure(planned=None) -> Figure:
    spec = parse_spec(
        "concept", {"boxes": [{"label": x} for x in ("현황", "문제", "해결 방안", "기대효과")]}
    )
    return Figure(
        id="f:method:1", kind="concept", section="method", spec=spec, caption="개념도", fit=planned
    )


def _pic_size(data: bytes) -> tuple[int, int]:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml").decode()
    cur = ET.fromstring(xml).find(".//hp:pic/hp:curSz", NS)
    return int(cur.get("width")), int(cur.get("height"))


def test_hwpx_figure_width_is_the_marker_place_width_and_height_follows_ratio():
    """고정 템플릿은 방법 칸이 표 칸(약 71mm) — 칸 폭 − 칸 여백 − 단락 여백이 그림 폭, 글자 크기는
    그 폭으로
    다시 계산된다(본문 폭 153.8mm 기준 9.3pt → 칸 폭에선 작다고 기록)."""
    planned = fit.make_fit(fit.BodyFrame(), "21:9", min_pt=9.3)
    png = _png(2100, 900, (0, 0, 2100, 900))
    r = _renderer()
    data, placements = r.render_with_figures(
        _draft(), confirmation=CONF, figures=[(_figure(planned), png, "image/png")]
    )
    w, h = _pic_size(data)
    assert abs(h - round(w * 900 / 2100)) <= 1
    p = placements[0].fit
    assert p is not None and p.fits and p.ratio == "21:9"
    assert abs(p.width_mm - w / fit.HWPUNIT_PER_MM) < 0.2
    assert p.min_text_pt == round(9.3 * p.width_mm / 153.8, 1) and p.text_ok is False
    assert "BinData/BIN0001.png" in zipfile.ZipFile(io.BytesIO(data)).namelist()


@pytest.mark.skipif(not REAL_FORM.is_file(), reason="실물 양식 없음 (미커밋)")
def test_real_form_figure_is_exactly_the_body_width():
    from rra.composition import build_renderer, load_settings

    keys = ["title", "objective", "method", "task_type", "utilization"]
    sections = [
        Section(
            key=k,
            sentences=[Sentence(text=f"{k} 문장.")],
            choices=["applied"]
            if k == "task_type"
            else (["software"] if k == "utilization" else []),
        )
        for k in keys
    ]
    draft = Draft(
        run_id="r",
        request=ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d"),
        sections=sections,
        template="korail_rnd_proposal_v2024",
    )
    planned = fit.make_fit(fit.BodyFrame(), "21:9", min_pt=9.3)
    fig = _figure(planned).model_copy(update={"section": "objective", "id": "f:objective:1"})
    data, placements = build_renderer(load_settings()).render_with_figures(
        draft, confirmation=CONF, figures=[(fig, _png(2100, 900, (0, 0, 2100, 900)), "image/png")]
    )
    w, h = _pic_size(data)
    assert w == 43606 and abs(h - round(43606 * 9 / 21)) <= 1
    p = placements[0].fit
    assert (p.width_mm, p.height_mm, p.fits, p.text_ok, p.min_text_pt) == (
        153.8,
        65.9,
        True,
        True,
        9.3,
    )


def test_hwpx_tall_legacy_figure_is_capped_at_a_third_of_the_page():
    png = _png(600, 2400, (0, 0, 600, 2400))  # 옛 세로 그림 (1:4)
    data, placements = _renderer().render_with_figures(
        _draft(), confirmation=CONF, figures=[(_figure(), png, "image/png")]
    )
    w, h = _pic_size(data)
    assert h <= int(84186 / 3) + 1 and w < h
    assert placements[0].fit.fits is False  # 통합 점검 "본문 폭에 맞게 들어감" 에서 걸린다


@pytest.mark.skipif(not FONTS, reason="번들 폰트 없음")
def test_real_baseline_png_has_the_chosen_ratio():
    spec = parse_spec(*WIDE_SAMPLES["schedule-4to1"])
    aspect = fit.choose_aspect(spec)
    png = svg_to_png(render_svg(spec, palette=PALETTE, aspect=aspect), font_files=FONTS, dpi=96)
    w, h = Image.open(io.BytesIO(png)).size
    assert aspect == "4:1" and abs(w / h - 4.0) < 0.02


def test_technique_prelim_note_goes_to_the_caption_line_not_the_image():
    """분석 기법 그림의 "제안 내용 기반 예비 평가"는 그림 안이 아니라 캡션 아래 12pt 줄로
    (2026-10-29 — 그림 안 안내문은 9pt 밑으로 그려졌다). 판단 표시는 그대로 남는다."""
    from rra.adapters.rendering.hwpx import _caption_lines
    from rra.domain.models.figure import PRELIM_NOTE, Figure, parse_spec
    from rra.domain.rules.figures import texts_of
    from tests.figure_v2_helpers import SWOT

    spec = parse_spec("technique", {"technique": "swot", "title": "SWOT 분석", **SWOT})
    fig = Figure(id="f:method:t1", kind="technique", section="method", spec=spec)
    assert PRELIM_NOTE not in texts_of(spec)
    assert _caption_lines(fig) == [f"※ {PRELIM_NOTE}"]
