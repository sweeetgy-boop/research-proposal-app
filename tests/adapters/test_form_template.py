"""실물 양식 템플릿 (tools/build_form_template.py) — 원본·결과 파일이 있을 때만 돈다.

- 원본(data/templates/proposal_form_original.hwpx)이 있으면: 변환 스크립트가 slots.yaml 의
  자리표시자를 전부, 각 1회, <hp:t> 안에 넣고 다른 zip 항목은 바이트 그대로 두는지.
- 템플릿(config/templates/proposal_korail.hwpx)이 있으면: 실제 렌더 결과에 {{ }} 가 0개,
  XML well-formed, 확정값만 ( ○ ), 항목 제목·순서가 PDF 원본과 같은지.
둘 다 커밋되지 않는 파일이라 CI 에서는 skip 된다.
"""

from __future__ import annotations

import importlib.util
import io
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from rra.adapters.rendering import HwpxRenderer, SlotMap
from rra.adapters.rendering.hwpx import verify_hwpx
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
ORIGINAL = ROOT / "data" / "templates" / "proposal_form_original.hwpx"
TEMPLATE = ROOT / "config" / "templates" / "proposal_korail.hwpx"
SLOTS = ROOT / "config" / "templates" / "proposal_korail.slots.yaml"
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# PDF 원본(data/templates/proposal_form_original.pdf)의 항목 제목 순서 (2026-10-26 대조)
FORM_ORDER = [
    "[별지 제2호서식] <개정 2024.02.19.>",
    "연구과제 제안서",
    "1. 연구개요",
    "가. 연구과제명",
    "나. 소요예산(추정액)",
    "다. 과제유형(해당사항에 체크)",
    "2. 연구배경 및 목적(제안사유)",
    "가. 연구배경 및 필요성",
    "(1) 정책적 중요도",
    "(2) 기술적 중요도",
    "(3) 공사 경영전략과의 정합성",
    "- 전략방향",
    "- 전략과제",
    "나. 연구목적",
    "다. 연구 방법 및 주요내용",
    "3. 기대효과",
    "가. 경영혁신 측면",
    "나. 기술혁신 측면",
    "다. 대외위상 측면",
    "4. 연구결과 활용계획",
    "가. 중장기 전략 및 주요업무계획 반영",
    "차. 실용화계획 있음",
    "실용화 계획 :",
    "5. 특이사항",
    "제안일자",
    "제안부서",
    "제안자",
    "연락처",
    "직　급",
    "성　명",
    "한국철도공사 철도연구원장 귀하",
]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_form_template", ROOT / "tools" / "build_form_template.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _slots() -> SlotMap:
    return SlotMap.from_config(yaml.safe_load(SLOTS.read_text(encoding="utf-8")))


def _draft() -> Draft:
    keys = [k for k in _slots().text if k != "strategy_alignment"]
    sections = [
        Section(key=k, sentences=[Sentence(text=f"{k} 문장 하나."), Sentence(text=f"{k} 문장 둘.")])
        for k in keys
    ]
    req = ProposalRequest(
        current_state="현황",
        root_cause="원인",
        limitation="한계",
        goal="목표",
        department="철도연구원 기술연구처",
        remarks="비고 <특이>",
        budget=Budget(account="연구개발비", amount_thousand_krw=150000),
    )
    return Draft(run_id="20260101000000-deadbeef", request=req, sections=sections)


CONFIRMED = Confirmation(
    choices={
        "task_type": ["applied"],
        "utilization": ["facility_method", "software", "commercialization"],
    }
)
PROPOSER = ProposerInfo(
    proposed_on="2026-10-26",
    proposer=Person(name="홍길동", rank="선임연구원", phone="042-000-0000"),
    head=Person(name="김철도", rank="처장", phone="042-000-0001"),
)


@pytest.mark.skipif(not ORIGINAL.is_file(), reason="실물 양식 원본 없음 (data/templates)")
def test_builder_inserts_every_declared_placeholder_once_and_keeps_other_parts(tmp_path):
    build = _builder()
    out = tmp_path / "proposal_korail.hwpx"
    stats = build.build(ORIGINAL, out)
    declared = _slots().placeholders()
    assert stats["placeholders"] == len(declared) == 36
    with zipfile.ZipFile(ORIGINAL) as a, zipfile.ZipFile(out) as b:
        assert a.namelist() == b.namelist()  # 순서까지 같다 (mimetype 첫 항목)
        assert b.infolist()[0].filename == "mimetype" and b.infolist()[0].compress_type == 0
        for name in a.namelist():
            if name != "Contents/section0.xml":
                assert a.read(name) == b.read(name), name
        xml = b.read("Contents/section0.xml").decode("utf-8")
    found = re.findall(r"\{\{[^}]+\}\}", xml)
    assert sorted(found) == sorted(declared)
    # 체크 칸은 괄호 안, 한 run 안
    assert "기초연구( {{task_type:basic}} ), 응용연구( {{task_type:applied}} )" in xml
    other = '</hp:run><hp:run charPrIDRef="22"><hp:t>(   {{utilization:other}}   )'
    assert "<hp:t>자. 기타</hp:t>" + other in xml
    # 본문 단락은 제목 단락과 같은 paraPr·charPr
    assert '<hp:run charPrIDRef="25"><hp:t>    {{policy_importance}}</hp:t>' in xml
    assert "<hp:t>☏ {{proposer.phone}}</hp:t>" in xml
    assert "<hp:t>{{proposer.name}}  (인)</hp:t>" in xml
    # 원본 안내문·수신처는 그대로
    assert "※ " in xml and "한국철도공사 철도연구원장 귀하" in xml
    assert "실용화 계획 : 구체적으로 작성(필요시 별지 추가)" in xml
    verify_hwpx(out.read_bytes())


@pytest.mark.skipif(not ORIGINAL.is_file(), reason="실물 양식 원본 없음 (data/templates)")
def test_builder_refuses_when_anchor_is_missing(tmp_path):
    build = _builder()
    with zipfile.ZipFile(ORIGINAL) as z:
        xml = z.read("Contents/section0.xml").decode("utf-8")
    broken = xml.replace("<hp:t> 가. 연구과제명 : </hp:t>", "<hp:t> 가. 과제명 : </hp:t>")
    with pytest.raises(build.FormChanged, match="연구과제명"):
        build.build_section(broken)
    with pytest.raises(build.FormChanged, match="이미"):
        build.build_section(xml.replace("1. 연구개요", "1. 연구개요 {{x}}"))


@pytest.mark.skipif(not TEMPLATE.is_file(), reason="실물 템플릿 없음 (config/templates)")
def test_real_template_renders_without_leftover_placeholders_in_form_order():
    from hwpx.document import HwpxDocument

    renderer = HwpxRenderer(_slots(), strategy=StrategyCatalog(), template_path=TEMPLATE)
    assert renderer.mode == "template"
    data = renderer.render(_draft(), confirmation=CONFIRMED, proposer=PROPOSER)
    assert verify_hwpx(data) == ["Contents/section0.xml"]  # zip + defusedxml 재파싱
    xml = zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml").decode("utf-8")
    assert re.findall(r"\{\{[^}]+\}\}", xml) == []  # 남은 자리표시자 0개
    text = HwpxDocument.open(data).text.plain()
    # 항목 제목·순서 = PDF 원본
    cursor = 0
    for label in FORM_ORDER:  # 앞 항목 뒤에서 차례로 찾는다 (※ 안내문 속 "제안부서" 등과 구분)
        cursor = text.index(label, cursor) + len(label)
    # 체크: 확정값만 ○
    assert "응용연구( ○ )" in text and "기초연구(   )" in text and "개발연구(   )" in text
    assert "운영방법 개선(   ○   )" in text and "개발 및 제공(   ○   )" in text
    assert "실용화계획 있음(   ○   )" in text and "매뉴얼 작성 및 배포(       )" in text
    # 문장별 단락, 한 줄 칸 인라인, 제안자 표
    # 줄맞춤은 공백이 아니라 단락 모양(왼쪽 여백·내어쓰기)이 한다 (항목 12)
    assert "\n○ method 문장 하나.\n○ method 문장 둘." in text
    assert "\n○ policy_importance 문장 하나." in text
    assert "\n가. 연구과제명 : title 문장 하나. title 문장 둘." in text
    assert "예산과목 연구개발비  금액 : 150,000 천원" in text
    assert "\n- 전략방향 : \n" in text  # 전략 목록이 비어 있으면 빈칸
    assert "☏ 042-000-0000" in text and "홍길동  (인)" in text and "김철도  (인)" in text
    assert "2026. 10. 26." in text and "철도연구원 기술연구처" in text
    assert "○ 비고 <특이>" in text and "&lt;" not in text
