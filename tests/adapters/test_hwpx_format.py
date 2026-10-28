"""항목 12 HWPX 서식 통일 — 단계별 단락 모양(왼쪽 여백 + 내어쓰기)·글자 크기·앞 공백·표 칸·캡션.

실물 양식을 닮은 고정 템플릿(tests/fixtures/hwpx/proposal_form_like.hwpx,
tests/tools/make_form_like_template.py 로 만든다)으로 렌더한 결과를 이 파일의 독립 파서
(defusedxml)로 읽어 확인한다 — 서식 모듈의 판정 함수를 쓰지 않는다.
"""

import io
import json
import re
import zipfile
from pathlib import Path

import defusedxml.ElementTree as DET
import pytest
import yaml

from rra.adapters.rendering import HwpxRenderer, SlotMap
from rra.adapters.rendering.hwpx import verify_hwpx
from rra.adapters.rendering.hwpx_format import FormatReport, format_hwpx
from rra.domain.models import Confirmation, Draft, ProposalRequest, Section, Sentence

ROOT = Path(__file__).parents[2]
FORM_LIKE = ROOT / "tests" / "fixtures" / "hwpx" / "proposal_form_like.hwpx"
SLOTS = ROOT / "config" / "templates" / "proposal_korail.slots.yaml"
REAL_TEMPLATE = ROOT / "config" / "templates" / "proposal_korail.hwpx"
NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
}
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

SECTIONS = [
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
LONG = "궤도 틀림 데이터를 수집해 열화 모델을 만들고 현장 검증까지 이어지는 긴 문장입니다. " * 3
CONF = Confirmation(choices={"task_type": ["applied"], "utilization": ["software", "manual"]})


def slots() -> SlotMap:
    return SlotMap.from_config(yaml.safe_load(SLOTS.read_text(encoding="utf-8")))


def renderer(template: Path = FORM_LIKE, **kw) -> HwpxRenderer:
    return HwpxRenderer(slots(), template_path=template, **kw)


def make_draft(text: str = LONG) -> Draft:
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    secs = [Section(key="title", sentences=[Sentence(text="궤도 열화 예측 모델 개발")])]
    secs += [
        Section(key=k, sentences=[Sentence(text=f"{k} {text}"), Sentence(text="둘째 문장.")])
        for k in SECTIONS
    ]
    secs += [
        Section(key="task_type", sentences=[], choices=["applied"]),
    ]
    return Draft(run_id="r1", request=req, sections=secs, template="korail_rnd_proposal_v2024")


# ── 독립 파서 ─────────────────────────────────────────────
def styles(data: bytes) -> tuple[dict, dict]:
    head = DET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("Contents/header.xml"))
    paras = {}
    for pp in head.iter(f"{{{NS['hh']}}}paraPr"):
        cases = [c for c in pp.iter(f"{{{NS['hp']}}}case") if c.find("hh:margin", NS) is not None]
        scope = cases[0] if cases else pp
        margin = scope.find(".//hh:margin", NS)
        spacing = scope.find(".//hh:lineSpacing", NS)
        paras[pp.get("id")] = {
            "align": pp.find("hh:align", NS).get("horizontal"),
            "left": int(margin.find("hc:left", NS).get("value")),
            "intent": int(margin.find("hc:intent", NS).get("value")),
            "spacing": int(spacing.get("value")),
        }
    chars = {
        cp.get("id"): {
            "pt": int(cp.get("height")) / 100,
            "bold": cp.find("hh:bold", NS) is not None,
        }
        for cp in head.iter(f"{{{NS['hh']}}}charPr")
    }
    return paras, chars


def paragraphs(data: bytes) -> list[dict]:
    """[{text, para, chars, cell}] — 표를 품은 단락은 빼고 칸 안 단락은 cell=(행,열)."""
    sec = DET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml"))
    out = []

    def walk(el, cell=None, tbl=None):
        for p in el.findall("hp:p", NS):
            runs = p.findall("hp:run", NS)
            tables = [t for r in runs for t in r.findall("hp:tbl", NS)]
            if not tables:
                text = "".join(t.text or "" for r in runs for t in r.findall("hp:t", NS))
                out.append(
                    {
                        "text": text,
                        "para": p.get("paraPrIDRef"),
                        "chars": [
                            r.get("charPrIDRef")
                            for r in runs
                            if "".join(t.text or "" for t in r.findall("hp:t", NS)).strip()
                        ],
                        "cell": cell,
                        "tbl": tbl,
                        "pic": any(r.find("hp:pic", NS) is not None for r in runs),
                    }
                )
            for t in tables:
                for tc in t.iter(f"{{{NS['hp']}}}tc"):
                    addr = tc.find("hp:cellAddr", NS)
                    walk(
                        tc.find("hp:subList", NS),
                        (int(addr.get("rowAddr")), int(addr.get("colAddr"))),
                        id(t),
                    )

    walk(sec)
    return out


def level_of(text: str) -> str | None:
    t = text.lstrip()
    if re.match(r"^\d\.\s", t):
        return "chapter"
    if re.match(r"^[가-하]\.\s", t):
        return "item"
    if re.match(r"^\(\d\)\s", t):
        return "sub"
    if t.startswith("- "):
        return "dash"
    if t.startswith("○ "):
        return "bullet"
    return None


@pytest.fixture(scope="module")
def rendered():
    r = renderer()
    data = r.render(make_draft(), confirmation=CONF)
    return data, r.last_format


def top(data):
    return [p for p in paragraphs(data) if p["cell"] is None]


# ── 단계별 단락 모양 ─────────────────────────────────────────
def test_every_level_has_one_paragraph_style_with_left_margin_and_hanging_indent(rendered):
    data, _ = rendered
    paras, _chars = styles(data)
    by_level: dict[str, set[str]] = {}
    for p in top(data):
        lv = level_of(p["text"])
        if lv in ("chapter", "item", "sub", "dash"):
            by_level.setdefault(lv, set()).add(p["para"])
    # 장 제목·항목·세부·줄표는 단계마다 단락 모양 하나 (3장 가. 만 내어쓰기이던 것이 통일)
    assert all(len(ids) == 1 for ids in by_level.values()), by_level
    lefts = {lv: paras[next(iter(ids))]["left"] for lv, ids in by_level.items()}
    assert lefts["chapter"] < lefts["item"] < lefts["sub"] < lefts["dash"]
    for lv, ids in by_level.items():
        shape = paras[next(iter(ids))]
        assert shape["intent"] < 0, f"{lv}: 내어쓰기(둘째 줄 정렬)가 없음"
        assert shape["spacing"] == 160


def test_bullets_align_under_their_parent_level_and_wrap_after_the_bullet(rendered):
    data, _ = rendered
    paras, _ = styles(data)
    seq = top(data)
    parent, lefts = None, {}
    for p in seq:
        lv = level_of(p["text"])
        if lv in ("chapter", "item", "sub"):
            parent = lv
        if lv == "bullet":
            lefts.setdefault(parent, set()).add(paras[p["para"]]["left"])
            assert paras[p["para"]]["intent"] < 0  # 머리표 뒤로 줄맞춤
    # 장(5. 특이사항) < 항목(나. 연구목적) < 세부((1) 정책적 중요도) 아래 순으로 깊다
    assert {k: len(v) for k, v in lefts.items()} == {"chapter": 1, "item": 1, "sub": 1}
    assert max(lefts["chapter"]) < max(lefts["item"]) < max(lefts["sub"])


def test_no_paragraph_starts_with_space_indentation(rendered):
    data, _ = rendered
    leading = [
        p["text"][:12]
        for p in paragraphs(data)
        if level_of(p["text"]) and p["text"][:1] in (" ", "　", "\t")
    ]
    assert leading == []


def test_body_is_12pt_regular_and_only_chapter_titles_are_13pt(rendered):
    data, _ = rendered
    _, chars = styles(data)
    for p in top(data):
        lv = level_of(p["text"])
        sizes = {chars[c]["pt"] for c in p["chars"]}
        if lv == "chapter":
            assert sizes == {13.0}
        elif lv in ("item", "sub", "dash"):
            assert sizes == {12.0}, p["text"][:10]
        elif lv == "bullet":  # 특이사항 본문도 제목(13pt 굵게)을 따라가지 않는다
            assert sizes == {12.0}
            assert not any(chars[c]["bold"] for c in p["chars"])


def test_form_table_cells_use_one_style_each_from_the_form(rendered):
    data, _ = rendered
    paras, chars = styles(data)
    cells: dict[tuple, list[dict]] = {}
    for p in paragraphs(data):
        if p["cell"] is not None:
            cells.setdefault((p["tbl"], p["cell"]), []).append(p)
    util = [ps for ps in cells.values() if any("중장기 전략" in p["text"] for p in ps)][0]
    plan = [ps for ps in cells.values() if any(p["text"].startswith("실용화 계획") for p in ps)][0]
    assert len({p["para"] for p in util}) == 1  # 가.~차. 한 모양 (원래 셋)
    assert {chars[c]["pt"] for p in util for c in p["chars"]} == {9.0}
    assert paras[util[0]["para"]]["spacing"] == 110  # 칸 원래 줄 간격
    assert len({p["para"] for p in plan}) == 1
    assert {chars[c]["pt"] for p in plan for c in p["chars"]} == {10.0}
    shape = paras[plan[0]["para"]]
    assert shape["intent"] < 0 and shape["spacing"] == 110  # ○ 문장 둘째 줄 정렬
    assert all(not p["text"].startswith(" ") for p in plan)


def test_format_report_counts_fixes_without_any_text_and_nothing_remains(rendered):
    data, report = rendered
    assert report["ok"] is True
    assert sum(report["remaining"].values()) == 0
    assert report["fixed"]["level_style"] > 0
    assert report["fixed"]["leading_spaces"] > 0
    assert report["fixed"]["cell_style"] > 0
    assert report["fixed"]["font_size"] > 0  # 특이사항 본문 13pt 굵게 → 12pt
    dumped = json.dumps(report, ensure_ascii=False)
    assert "궤도" not in dumped and "{{" not in dumped  # 건수만


def test_format_pass_is_idempotent_and_reuses_styles(rendered):
    data, _ = rendered
    again, report = format_hwpx(data)
    assert report.fixed_total == 0 and report.ok
    assert report.styles_added == 0
    assert again == data


def test_format_check_runs_on_every_render_and_can_be_turned_off():
    r = renderer(format_check=False)
    data = r.render(make_draft(), confirmation=CONF)
    assert r.last_format is None
    _, report = format_hwpx(data)
    assert report.fixed_total > 0  # 끄면 고치지 않은 그대로 — 점검이 찾아낸다
    assert isinstance(report, FormatReport)


# ── 보안 F 유지 ────────────────────────────────────────────
def test_hostile_text_is_still_escaped_and_reparsed_after_formatting():
    hostile = '   <hp:t>주입</hp:t> & "감지" ]]> \x00 끝'
    r = renderer()
    data = r.render(make_draft(hostile), confirmation=CONF)
    verify_hwpx(data)
    xml = zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml").decode("utf-8")
    assert "<hp:t>주입</hp:t> &amp;" not in xml
    assert "&lt;hp:t&gt;주입&lt;/hp:t&gt; &amp; " in xml
    texts = [p["text"] for p in paragraphs(data)]
    assert any('<hp:t>주입</hp:t> & "감지"' in t for t in texts)


def test_leading_space_strip_never_eats_escaped_entities():
    from rra.adapters.rendering.hwpx_format import _strip_leading

    head, run = '<hp:p id="1" paraPrIDRef="0">', '<hp:run charPrIDRef="0">'
    para = f"{head}{run}<hp:t>  &amp;lt; 값</hp:t></hp:run></hp:p>"
    assert "<hp:t>&amp;lt; 값</hp:t>" in _strip_leading(para)
    only = f"{head}{run}<hp:t>   </hp:t></hp:run>{run}<hp:t>  ○ 본문</hp:t></hp:run></hp:p>"
    out = _strip_leading(only)
    assert "<hp:t></hp:t>" in out and "<hp:t>○ 본문</hp:t>" in out


# ── 그림 캡션 ─────────────────────────────────────────────
def test_figure_caption_and_source_line_are_12pt_centered():
    from rra.adapters.figures import render_svg, svg_to_png
    from rra.domain.models.figure import Figure, parse_spec

    palette = yaml.safe_load((ROOT / "config/figures.yaml").read_text(encoding="utf-8"))["palette"]
    spec = parse_spec(
        "concept",
        {"boxes": [{"label": "현황"}, {"label": "문제"}, {"label": "해결"}, {"label": "효과"}]},
    )
    fonts = sorted((ROOT / "config/templates/figures/fonts").glob("*.otf"))
    png = svg_to_png(render_svg(spec, palette=palette, width_px=600), font_files=fonts, dpi=96)
    fig = Figure(
        id="f:method:1",
        kind="concept",
        section="method",
        caption="연구 개념도",
        spec=spec,
        source_caption="출처: 공개 통계(2025)",
    )
    r = renderer()
    data, placements = r.render_with_figures(
        make_draft(), confirmation=CONF, figures=[(fig, png, "image/png")]
    )
    assert placements[0].placement == "inline"
    paras, chars = styles(data)
    rows = paragraphs(data)
    caption = next(p for p in rows if p["text"].startswith("그림 1. "))
    source = next(p for p in rows if p["text"] == "출처: 공개 통계(2025)")
    picture = next(p for p in rows if p["pic"])
    for p in (caption, source):
        assert paras[p["para"]]["align"] == "CENTER"
        assert {chars[c]["pt"] for c in p["chars"]} == {12.0}
        assert not any(chars[c]["bold"] for c in p["chars"])
    assert paras[picture["para"]]["align"] == "CENTER"
    assert r.last_format["ok"] is True and r.last_format["levels"]["caption"] >= 3


# ── 실물 양식 (있을 때만) ───────────────────────────────────
@pytest.mark.skipif(not REAL_TEMPLATE.is_file(), reason="실물 템플릿 없음 (config/templates)")
def test_real_form_template_passes_the_format_check():
    r = renderer(REAL_TEMPLATE)
    r.render(make_draft(), confirmation=CONF)
    assert r.last_format["ok"] is True
    assert r.last_format["levels"]["chapter"] == 5
