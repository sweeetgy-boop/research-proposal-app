"""[G] HWPX 그림 삽입 — 섹션 칸 안(inline) 그림+캡션, 별첨(appendix) 경로, BinData·manifest 등록,
구조 검증. 고정 템플릿(tests/fixtures/hwpx/proposal_template_min.hwpx) + 실제 밑그림 PNG."""

import io
import zipfile
from pathlib import Path

import pytest
import yaml
from defusedxml import ElementTree as ET

from rra.adapters.figures import render_svg, svg_to_png
from rra.adapters.rendering import HwpxRenderer, SlotMap
from rra.adapters.rendering.hwpx import figure_marker
from rra.application.ports.renderer import RenderRejected
from rra.domain.models import Confirmation, Draft, ProposalRequest, Section, Sentence
from rra.domain.models.figure import Figure, parse_spec

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "tests/fixtures/hwpx/proposal_template_min.hwpx"
SLOTS = ROOT / "config/templates/proposal_korail.slots.yaml"
FONTS = sorted((ROOT / "config/templates/figures/fonts").glob("*.otf"))
NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}


@pytest.fixture(scope="module")
def png():
    palette = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))["palette"]
    spec = parse_spec(
        "concept",
        {
            "boxes": [
                {"label": "현황", "lines": ["궤도 틀림 반복"]},
                {"label": "문제", "lines": ["노반 침하"]},
                {"label": "해결 방안", "lines": ["열화 예측 모델"]},
                {"label": "기대효과", "lines": ["보수 비용 절감"]},
            ]
        },
    )
    return svg_to_png(render_svg(spec, palette=palette, width_px=800), font_files=FONTS, dpi=96)


def make_draft():
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    sections = [
        Section(key="title", sentences=[Sentence(text="궤도 열화 예측")]),
        Section(key="objective", sentences=[Sentence(text="목적 문장.")]),
        Section(
            key="method",
            sentences=[Sentence(text="방법 문장 하나."), Sentence(text="방법 문장 둘.")],
        ),
        Section(key="task_type", sentences=[], choices=["applied"]),
        Section(key="utilization", sentences=[], choices=["software"]),
    ]
    return Draft(run_id="r1", request=req, sections=sections, template="korail_rnd_proposal_v2024")


def figure(fid="f:method:1", section="method", caption="연구 개념도", source=""):
    spec = parse_spec(
        "concept",
        {
            "boxes": [
                {"label": "현황"},
                {"label": "문제"},
                {"label": "해결 방안"},
                {"label": "기대효과"},
            ]
        },
    )
    return Figure(
        id=fid, kind="concept", section=section, caption=caption, spec=spec, source_caption=source
    )


def renderer(**kw):
    slots = SlotMap.from_config(yaml.safe_load(SLOTS.read_text(encoding="utf-8")))
    return HwpxRenderer(slots, template_path=TEMPLATE, **kw)


def section_xml(data: bytes):
    zf = zipfile.ZipFile(io.BytesIO(data))
    return zf, zf.read("Contents/section0.xml").decode("utf-8")


CONF = Confirmation(choices={"task_type": ["applied"], "utilization": ["software"]})


def test_inline_figure_goes_into_the_section_cell_with_caption_and_bindata(png):
    r = renderer()
    data, placements = r.render_with_figures(
        make_draft(),
        confirmation=CONF,
        figures=[(figure(source="출처: 궤도 보고서, 2024년, 3쪽"), png, "image/png")],
    )
    zf, xml = section_xml(data)
    names = zf.namelist()
    assert "BinData/BIN0001.png" in names and zf.read("BinData/BIN0001.png") == png
    hpf = zf.read("Contents/content.hpf").decode()
    assert 'href="BinData/BIN0001.png"' in hpf and 'isEmbeded="1"' in hpf
    assert "binDataList" in zf.read("Contents/header.xml").decode()
    assert figure_marker("f:method:1") not in xml  # 표식은 그림으로 바뀌었다
    root = ET.fromstring(xml)
    pics = root.findall(".//hp:pic", NS)
    assert len(pics) == 1 and pics[0].find("hp:curSz", NS).get("width") not in (None, "0")
    assert "그림 1. 연구 개념도" in xml and "출처: 궤도 보고서, 2024년, 3쪽" in xml
    # 그림이 방법 칸 안(방법 문장 뒤)에 있다
    cell_text = xml.split("방법 문장 둘.")[1]
    assert "<hp:pic" in cell_text[:4000] and "그림 1. 연구 개념도" in cell_text[:6000]
    assert placements[0].placement == "inline" and placements[0].number == 1
    assert placements[0].bytes == len(png) and "별첨" not in xml


def test_appendix_placement_puts_figures_at_the_end_with_reference_note(png):
    r = renderer(figure_placement="appendix", figure_caption_prefix="그림")
    figs = [
        (figure(), png, "image/png"),
        (figure("f:objective:1", "objective", "개념"), png, "image/png"),
    ]
    data, placements = r.render_with_figures(make_draft(), confirmation=CONF, figures=figs)
    zf, xml = section_xml(data)
    assert [p.placement for p in placements] == ["appendix", "appendix"]
    assert "(별첨 그림 1 참조)" in xml and "(별첨 그림 2 참조)" in xml
    tail = xml[
        xml.index("별첨 그림</hp:t>") if "별첨 그림</hp:t>" in xml else xml.index("별첨 그림") :
    ]
    assert tail.count("<hp:pic") == 2 and "그림 2. 개념" in tail
    assert len([n for n in zf.namelist() if n.startswith("BinData/")]) == 2


def test_figure_without_a_paragraph_slot_section_falls_back_to_appendix(png):
    r = renderer()
    data, placements = r.render_with_figures(
        make_draft(), confirmation=CONF, figures=[(figure("f:title:1", "title"), png, "image/png")]
    )
    _, xml = section_xml(data)
    assert placements[0].placement == "appendix" and "별첨 그림" in xml


def test_rejects_unknown_mime_and_no_figures_is_plain_render(png):
    r = renderer()
    with pytest.raises(RenderRejected):
        r.render_with_figures(
            make_draft(), confirmation=CONF, figures=[(figure(), png, "image/gif")]
        )
    data, placements = r.render_with_figures(make_draft(), confirmation=CONF, figures=[])
    assert placements == [] and data == r.render(make_draft(), confirmation=CONF)


def test_jpeg_figure_is_registered_as_jpg(png):
    from PIL import Image

    buf = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(buf, format="JPEG", quality=70)
    jpg = buf.getvalue()
    data, placements = renderer().render_with_figures(
        make_draft(), confirmation=CONF, figures=[(figure(), jpg, "image/jpeg")]
    )
    zf, _ = section_xml(data)
    assert "BinData/BIN0001.jpg" in zf.namelist() and placements[0].bytes == len(jpg)


REAL_TEMPLATE = ROOT / "config/templates/proposal_korail.hwpx"


@pytest.mark.skipif(not REAL_TEMPLATE.is_file(), reason="실물 양식 없음 (미커밋)")
def test_real_form_puts_figure_right_after_the_section_body(png):
    """실물 양식은 섹션 본문이 표 밖 단락 — 그림·캡션·출처가 그 단락 바로 뒤, 다음 섹션 앞."""
    from rra.composition import build_renderer, load_settings

    r = build_renderer(load_settings())
    keys = [
        "title",
        "task_type",
        "policy_importance",
        "tech_importance",
        "strategy_alignment",
        "objective",
        "method",
        "expected_management",
        "expected_technology",
        "expected_standing",
        "utilization",
        "overlap_review",
    ]
    sections = [
        Section(
            key=k,
            sentences=[Sentence(text=f"{k} 문장 하나."), Sentence(text=f"{k} 문장 둘.")],
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
    fig = figure("f:objective:1", "objective", "연구 개념도", source="출처: 시험 문서, 2024년, 3쪽")
    data, placements = r.render_with_figures(
        draft, confirmation=CONF, figures=[(fig, png, "image/png")]
    )
    _, xml = section_xml(data)
    assert placements[0].placement == "inline"
    pic = xml.index("<hp:pic")
    assert (
        xml.index("objective 문장 둘")
        < pic
        < xml.index("그림 1. 연구 개념도")
        < xml.index("출처: 시험 문서")
    )
    assert xml.index("출처: 시험 문서") < xml.index("method 문장 하나") and "별첨" not in xml
