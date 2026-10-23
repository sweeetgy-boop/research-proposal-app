"""HWPX 렌더러 (Step 8) — 생성 모드·템플릿 모드, 보안 F(escape·재파싱), 확정값·슬롯 규칙.

python-hwpx 로 만든 결과를 zip 으로 열고 섹션 XML 을 defusedxml 로 파싱해 확인한다.
"""

import io
import re
import zipfile
from pathlib import Path

import defusedxml.ElementTree as DET
import pytest
import yaml

from rra.adapters.rendering import (
    ConfirmationRequired,
    HwpxRenderer,
    RenderedXmlInvalid,
    SlotMap,
    TemplateSlotUnfilled,
    UnknownSlot,
    sanitize,
    slot_values,
)
from rra.adapters.rendering.hwpx import verify_hwpx
from rra.application.ports.renderer import RendererPort, RenderRejected
from rra.domain.models import (
    Budget,
    Confirmation,
    Draft,
    ProposalRequest,
    ProposerInfo,
    Section,
    Sentence,
    StrategyCatalog,
)
from rra.domain.models.proposer import Person

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "tests" / "fixtures" / "hwpx" / "proposal_template_min.hwpx"
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

HOSTILE = '궤도 <틀림> & "감지" ]]> <hp:t>주입</hp:t> 연구\x00\x1b'
SECTIONS = [
    "title",
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


@pytest.fixture
def slots():
    data = yaml.safe_load(
        (ROOT / "config" / "templates" / "proposal_korail.slots.yaml").read_text(encoding="utf-8")
    )
    return SlotMap.from_config(data)


@pytest.fixture
def strategy():
    return StrategyCatalog.model_validate(
        {
            "directions": [
                {"id": "D1", "name": "안전", "tasks": [{"id": "D1-1", "name": "예방정비"}]}
            ]
        }
    )


def request(**kw):
    base = {"current_state": "현황", "root_cause": "원인", "limitation": "한계", "goal": "목표"}
    return ProposalRequest(**{**base, **kw})


def draft(sections=None, req=None):
    return Draft(
        run_id="20260101000000-deadbeef", request=req or request(), sections=sections or []
    )


def full_draft():
    secs = [
        Section(key=k, sentences=[Sentence(text=f"{k} 문장 1"), Sentence(text=f"{k} 문장 2")])
        for k in SECTIONS
    ]
    secs[0] = Section(key="title", sentences=[Sentence(text=HOSTILE)])
    req = request(
        department="철도연구원",
        remarks="비고 <특이>",
        budget=Budget(account="연구개발비", amount_thousand_krw=150000),
    )
    return draft(secs, req)


CONFIRMED = Confirmation(
    choices={
        "task_type": ["applied"],
        "utilization": ["software", "manual"],
        "strategy_alignment": ["D1-1"],
    }
)
PROPOSER = ProposerInfo(
    proposed_on="2026-10-23",
    proposer=Person(name="홍길동", rank="선임연구원", phone="010-0000-0000"),
    head=Person(name="김부장", rank="처장", phone="010-1111-1111"),
)


def section_xml(data: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml").decode("utf-8")


def plain_text(data: bytes) -> str:
    from hwpx.document import HwpxDocument

    return HwpxDocument.open(data).text.plain()


# ── 순수 함수 ──────────────────────────────────────────────
def test_sanitize_strips_xml_forbidden_chars_but_keeps_newlines():
    assert sanitize("a\x00b\x1bc\n d\r\ne") == "abc\n d\ne"
    assert sanitize(None) == "" and sanitize("x" * 10, limit=3) == "xxx"


def test_slot_map_rejects_bad_placeholders():
    with pytest.raises(ValueError, match="자리표시자 형식"):
        SlotMap.from_config({"text": {"title": "<<연구과제명>>"}})


def test_slot_values_fill_text_choice_input_and_render_only(slots, strategy):
    values = slot_values(
        full_draft(), slots, confirmation=CONFIRMED, proposer=PROPOSER, strategy=strategy
    )
    assert values["{{연구과제명}}"] == sanitize(HOSTILE)  # escape 는 넣는 자리에서
    assert values["{{체크_응용연구}}"] == "■" and values["{{체크_기초연구}}"] == "□"
    assert values["{{체크_활용_사}}"] == "■" and values["{{체크_활용_가}}"] == "□"
    assert values["{{전략방향}}"] == "안전" and values["{{전략과제}}"] == "예방정비"
    assert values["{{예산금액}}"] == "150,000" and values["{{제안부서}}"] == "철도연구원"
    assert values["{{특이사항}}"].endswith("\n비고 <특이>")  # remarks 를 이어 붙인다
    assert values["{{제안자_성명}}"] == "홍길동" and values["{{부서장_연락처}}"] == "010-1111-1111"
    assert set(values) == slots.placeholders()


def test_choices_come_only_from_confirmation_not_from_llm_proposal(slots, strategy):
    proposed = Section(key="task_type", sentences=[], choices=["development"])  # LLM 제안
    values = slot_values(
        draft([proposed]),
        slots,
        confirmation=Confirmation(choices={"task_type": ["basic"], "utilization": ["other"]}),
        proposer=None,
        strategy=strategy,
    )
    assert values["{{체크_기초연구}}"] == "■" and values["{{체크_개발연구}}"] == "□"


def test_missing_confirmation_is_refused(slots, strategy):
    with pytest.raises(ConfirmationRequired, match="task_type, utilization"):
        slot_values(draft(), slots, confirmation=None, proposer=None, strategy=strategy)
    with pytest.raises(ConfirmationRequired, match="utilization"):
        slot_values(
            draft(),
            slots,
            confirmation=Confirmation(choices={"task_type": ["basic"]}),
            proposer=None,
            strategy=strategy,
        )


def test_unknown_slots_and_options_are_errors(slots, strategy):
    ok = Confirmation(choices={"task_type": ["basic"], "utilization": ["other"]})
    with pytest.raises(UnknownSlot, match="선언되지 않은 자리표시자"):
        slot_values(
            draft(),
            slots,
            confirmation=ok,
            proposer=None,
            strategy=strategy,
            extra={"{{없는칸}}": "x"},
        )
    with pytest.raises(UnknownSlot, match="slots.yaml 에 없는 선택지"):
        slot_values(
            draft(),
            slots,
            confirmation=Confirmation(choices={"task_type": ["evil"], "utilization": ["other"]}),
            proposer=None,
            strategy=strategy,
        )
    with pytest.raises(UnknownSlot, match="전략 목록에 없는 id"):
        slot_values(
            draft(),
            slots,
            confirmation=Confirmation(
                choices={
                    "task_type": ["basic"],
                    "utilization": ["other"],
                    "strategy_alignment": ["X9"],
                }
            ),
            proposer=None,
            strategy=strategy,
        )
    assert issubclass(UnknownSlot, RenderRejected) and issubclass(
        ConfirmationRequired, RenderRejected
    )


# ── 생성 모드 ──────────────────────────────────────────────
def test_generate_mode_empty_draft_renders_every_form_section(slots, strategy):
    r = HwpxRenderer(slots, strategy=strategy)
    assert isinstance(r, RendererPort) and r.mode == "generate"
    data = r.render(
        draft(),
        confirmation=Confirmation(choices={"task_type": ["basic"], "utilization": ["other"]}),
    )
    assert verify_hwpx(data) == ["Contents/section0.xml"]
    text = plain_text(data)
    for label in (
        "1. 과제 개요",
        "가. 연구과제명",
        "나. 소요예산(추정액)",
        "다. 과제유형",
        "2. 제안 배경 및 목적",
        "(1) 정책적 중요도",
        "(2) 기술적 중요도",
        "(3) 공사 경영전략과의 정합성",
        "나. 연구목적",
        "다. 연구 방법 및 주요내용",
        "3. 기대효과",
        "4. 연구결과 활용계획",
        "5. 특이사항",
        "제안일자",
        "제안부서장",
    ):
        assert label in text, label
    assert "■ 기초연구" in text and "□ 응용연구" in text and "■ 자. 기타" in text


def test_generate_mode_escapes_hostile_text_and_round_trips(slots, strategy):
    data = HwpxRenderer(slots, strategy=strategy).render(
        full_draft(), confirmation=CONFIRMED, proposer=PROPOSER
    )
    xml = section_xml(data)
    DET.fromstring(xml)  # well-formed
    assert "<hp:t>주입</hp:t>" not in xml  # 값 속 태그는 데이터로만 남는다
    assert "&lt;hp:t&gt;주입&lt;/hp:t&gt;" in xml and "&lt;틀림&gt; &amp;" in xml
    assert "\x00" not in xml and "\x1b" not in xml
    text = plain_text(data)
    assert '궤도 <틀림> & "감지" ]]> <hp:t>주입</hp:t> 연구' in text  # 다시 열면 원문 그대로
    assert (
        "■ 응용연구" in text
        and "■ 사. 컴퓨터 프로그램의 개발 및 제공" in text
        and "■ 아. 매뉴얼" in text
    )
    assert "안전, 예방정비" in text or ("안전" in text and "예방정비" in text)
    assert "예산과목: 연구개발비 / 금액: 150,000 천원" in text
    assert "선임연구원 홍길동 (연락처 010-0000-0000)" in text and "처장 김부장" in text
    assert "비고 <특이>" in text


# ── 템플릿 모드 ────────────────────────────────────────────
def test_template_mode_fills_only_placeholders_and_keeps_structure(slots, strategy):
    r = HwpxRenderer(slots, strategy=strategy, template_path=TEMPLATE)
    assert r.mode == "template"
    data = r.render(full_draft(), confirmation=CONFIRMED, proposer=PROPOSER)
    verify_hwpx(data)
    before = zipfile.ZipFile(io.BytesIO(TEMPLATE.read_bytes())).namelist()
    after = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert sorted(before) == sorted(after)  # 템플릿 구조 그대로
    xml = section_xml(data)
    assert not re.search(r"\{\{[^}]+\}\}", xml)  # 자리표시자 전부 치환
    assert (
        "&lt;hp:t&gt;주입&lt;/hp:t&gt;" in xml and "<hp:t>주입</hp:t>" not in xml
    )  # escape 로만 들어간다
    text = plain_text(data)
    assert "■" in text and "□" in text and "홍길동" in text and "150,000" in text
    assert '궤도 <틀림> & "감지" ]]>' in text
    # 템플릿의 라벨은 그대로 남아 있다
    assert "연구과제 제안서 (테스트 템플릿)" in text and "체크:task_type:basic" in text


def test_template_mode_rejects_placeholders_split_across_runs(slots, strategy, tmp_path):
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    p = doc.add_paragraph("과제명: {{연구과")
    p.add_run("제명}}")  # run 이 갈라진 자리표시자
    path = tmp_path / "split.hwpx"
    path.write_bytes(doc.to_bytes())
    # 갈라진 자리표시자는 치환 대상이 아니고 검출도 되지 않는다
    # → 다른 선언 슬롯이 남아 있는지로 검출한다
    doc2 = HwpxDocument.new()
    doc2.add_paragraph("{{연구과제명}} {{정책적중요도}}")
    t = doc2.add_table(1, 1)
    t.set_cell_text(0, 0, "{{체크_기초연구}}")
    good = tmp_path / "good.hwpx"
    good.write_bytes(doc2.to_bytes())
    r = HwpxRenderer(slots, strategy=strategy, template_path=good)
    out = r.render(full_draft(), confirmation=CONFIRMED)  # 선언된 슬롯 일부만 쓰는 템플릿도 된다
    assert "{{" not in section_xml(out)

    # 선언된 슬롯이 치환되지 않고 남으면 거부 — escape 된 값 안의 '{{' 는 자리표시자가 아니다
    unfilled = SlotMap.from_config(
        {"text": {"title": "{{연구과제명}}"}, "choice": {}, "input": {}, "render_only": {}}
    )
    doc3 = HwpxDocument.new()
    doc3.add_paragraph(
        "{{연구과제명}} {{정책적중요도}}"
    )  # 두 번째는 이 SlotMap 에 없어 그대로 남아도 된다
    partial = tmp_path / "partial.hwpx"
    partial.write_bytes(doc3.to_bytes())
    assert "{{정책적중요도}}" in section_xml(
        HwpxRenderer(
            unfilled, strategy=strategy, template_path=partial, required_choices=()
        ).render(full_draft())
    )


def test_template_mode_reports_unfilled_declared_slots(slots, strategy, tmp_path, monkeypatch):
    """치환 뒤에도 선언된 자리표시자가 남으면(값이 비어 있어도 치환은 되므로, 값 자체에 자리표시자가
    들어오는 경우) 거부한다."""
    r = HwpxRenderer(slots, strategy=strategy, template_path=TEMPLATE)
    hostile = full_draft()
    hostile.sections[0] = Section(key="title", sentences=[Sentence(text="{{제안자_성명}}")])
    # 값 속 자리표시자는 escape 되지 않는 문자({ })라 치환 결과에 남는다
    # → 다음 슬롯이 또 치환될 수 있다.
    # 순서상 title 이 먼저 치환되고 render_only 가 나중이라 값 속 {{제안자_성명}} 도 치환된다.
    data = r.render(hostile, confirmation=CONFIRMED, proposer=PROPOSER)
    assert "{{" not in section_xml(data)
    # 반대로 마지막 슬롯 값에 자리표시자를 넣으면 남는다 → TemplateSlotUnfilled
    hostile2 = full_draft()
    with_marker = ProposerInfo(head=Person(phone="{{부서장_연락처}}"))
    with pytest.raises(TemplateSlotUnfilled, match="부서장_연락처"):
        r.render(hostile2, confirmation=CONFIRMED, proposer=with_marker)


def test_verify_rejects_broken_xml_and_bad_zip():
    with pytest.raises(RenderedXmlInvalid, match="zip"):
        verify_hwpx(b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", "<hs:sec><unclosed></hs:sec>")
    with pytest.raises(RenderedXmlInvalid, match="well-formed"):
        verify_hwpx(buf.getvalue())
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as z:
        z.writestr("mimetype", "x")
    with pytest.raises(RenderedXmlInvalid, match="섹션 XML"):
        verify_hwpx(buf2.getvalue())


def test_verify_rejects_entity_expansion(slots):
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<sec>&b;</sec>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", bomb)
    with pytest.raises(RenderedXmlInvalid):
        verify_hwpx(buf.getvalue())
