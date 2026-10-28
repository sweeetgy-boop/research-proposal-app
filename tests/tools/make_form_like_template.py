"""서식 점검(항목 12) 테스트용 "실물 양식을 닮은" HWPX 템플릿 생성.

    .venv/bin/python tests/tools/make_form_like_template.py [출력 경로]

실물 양식(config/templates/proposal_korail.hwpx)은 커밋하지 않으므로, 그 구조를 흉내 낸 파일을
fixture 로 남긴다 — 장·항목·세부·줄표 제목 줄의 공백 들여쓰기, 제목을 복제한 본문 자리표시자 단락
(특이사항은 13pt 굵게), 3장 가. 만 내어쓰기, 활용계획 목록 칸의 단락 모양 세 가지, 실용화 계획 칸
(10pt), 제안자 표. slots.yaml 의 자리표시자를 모두 정확히 한 번 넣는다.

글자는 실물 양식의 고정 문구(tools/build_form_template.py 앵커와 같은 공개 서식 문구)만 쓴다.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "hwpx" / "proposal_form_like.hwpx"

# (id, 정렬, 왼쪽, 들여쓰기, 줄 간격)
PARAS = {
    "body": ("JUSTIFY", 0, 0, 160),
    "hang_expected": ("JUSTIFY", 0, -1717, 160),
    "note": ("JUSTIFY", 0, -2565, 160),
    "center": ("CENTER", 0, 0, 160),
    "cell_a": ("JUSTIFY", 0, -2069, 110),
    "cell_b": ("JUSTIFY", 0, -1300, 110),
    "cell_c": ("JUSTIFY", 0, -1600, 110),
    "cell_label": ("JUSTIFY", 0, 0, 110),
    "prop": ("CENTER", 0, 0, 160),
}
# (높이, 굵게)
CHARS = {
    "c13b": (1300, True),
    "c12": (1200, False),
    "c9": (900, False),
    "c10": (1000, False),
    "c13": (1300, False),
    "c9b": (900, True),
    "c12b": (1200, True),
}

UTIL = [
    ("가. 중장기 전략 및 주요업무계획 반영", "strategy_plan", "cell_a"),
    ("나. 제도(규정 및 업무처리 기준 등) 제・개정", "regulation", "cell_b"),
    ("다. 사업 타당성 검토 및 경영의사결정 근거자료 활용", "feasibility", "cell_b"),
    ("라. 외부기관 협상 근거자료 활용", "negotiation", "cell_b"),
    (
        "마. 새로운 시설・설비 또는 유지보수 시스템・방법의 개발 및 운영방법 개선",
        "facility_method",
        "cell_c",
    ),
    ("바. 차량 및 기존 시설물의 개량 또는 대체", "rolling_stock", "cell_b"),
    ("사. 컴퓨터 프로그램의 개발 및 제공", "software", "cell_b"),
    ("아. 매뉴얼 작성 및 배포", "manual", "cell_b"),
    ("자. 기타", "other", "cell_b"),
    ("차. 실용화계획 있음", "commercialization", "cell_b"),
]

LINES_BEFORE_TABLE = [
    ("body", "c12b", "[별지 제2호서식] <개정 2024.02.19.>"),
    ("center", "c13b", "연구과제 제안서"),
    ("body", "c13b", "1. 연구개요"),
    ("body", "c12", " 가. 연구과제명 : {{title}}"),
    (
        "body",
        "c12",
        " 나. 소요예산(추정액) : 예산과목 {{budget.account}}  금액 : {{budget.amount}} 천원",
    ),
    (
        "body",
        "c12",
        " 다. 과제유형(해당사항에 체크) : 기초연구( {{task_type:basic}} ), 응용연구( "
        "{{task_type:applied}} ), 개발연구( {{task_type:development}} )",
    ),
    ("body", "c13b", "2. 연구배경 및 목적(제안사유)"),
    ("body", "c12", " 가. 연구배경 및 필요성"),
    ("body", "c12", "  (1) 정책적 중요도"),
    ("body", "c12", "    {{policy_importance}}"),
    ("body", "c12", "  (2) 기술적 중요도"),
    ("body", "c12", "    {{tech_importance}}"),
    ("body", "c12", "  (3) 공사 경영전략과의 정합성 등(공사 중장기 전략경영과 연계하여 작성)"),
    ("body", "c12", "   - 전략방향 : {{strategy_alignment:direction}}"),
    ("body", "c12", "   - 전략과제 : {{strategy_alignment:task}}"),
    ("body", "c12", "    {{strategy_alignment}}"),
    ("body", "c12", " 나. 연구목적"),
    ("body", "c12", "   {{objective}}"),
    ("body", "c12", " 다. 연구 방법 및 주요내용 "),
    ("body", "c12", "   {{method}}"),
    ("body", "c13b", "3. 기대효과"),
    (
        "note",
        "c9",
        "  ※ 제안과제의 연구결과가 우리 공사의 경영혁신 등에 기여할 수 있는 기대효과 기술",
    ),
    ("hang_expected", "c12", "  가. 경영혁신 측면"),
    ("hang_expected", "c12", "    {{expected_management}}"),
    ("body", "c12", "  나. 기술혁신 측면"),
    ("body", "c12", "    {{expected_technology}}"),
    ("body", "c12", "  다. 대외위상 측면"),
    ("body", "c12", "    {{expected_standing}}"),
    ("body", "c13b", "4. 연구결과 활용계획"),
]
LINES_AFTER_TABLE = [
    ("body", "c13b", "5. 특이사항 :"),
    ("body", "c13b", "  {{overlap_review}}"),  # 실물처럼 제목(13pt 굵게)을 복제한 본문 단락
    (
        "body",
        "c12b",
        "연구개발 규정 시행세칙 제13조 1항의 규정에 따라 위와 같이 연구과제를 제안합니다.",
    ),
]
PROPOSER = [
    ["{{proposed_on}}", "{{department}}"],
    ["☏ {{proposer.phone}}", "☏ {{head.phone}}"],
    ["{{proposer.rank}}", "{{head.rank}}"],
    ["{{proposer.name}}  (인)", "{{head.name}}  (인)"],
]


def _tok(p: str, c: str) -> str:
    return f"⟦{p}|{c}⟧"


def _clone(xml: str, tag: str, base_id: str, new_id: int) -> str:
    m = re.search(rf'<hh:{tag} id="{base_id}"[^>]*>.*?</hh:{tag}>', xml, re.S)
    assert m, tag
    return re.sub(r'id="\d+"', f'id="{new_id}"', m.group(0), count=1)


def _para_xml(base: str, align: str, left: int, intent: int, spacing: int) -> str:
    out = re.sub(r'(<hh:align horizontal=")[A-Z_]+"', rf'\g<1>{align}"', base, count=1)
    head, _, tail = out.partition("<hp:default>")

    def put(part: str, k: int) -> str:
        part = re.sub(r'(<hc:intent value=")-?\d+"', rf'\g<1>{intent * k}"', part)
        part = re.sub(r'(<hc:left value=")-?\d+"', rf'\g<1>{left * k}"', part)
        return re.sub(r'(<hh:lineSpacing type="PERCENT" value=")\d+"', rf'\g<1>{spacing}"', part)

    return put(head, 1) + ("<hp:default>" + put(tail, 2) if tail else "")


def _char_xml(base: str, height: int, bold: bool) -> str:
    out = re.sub(r'height="\d+"', f'height="{height}"', base, count=1)
    out = out.replace("<hh:bold/>", "")
    if bold:
        out = out.replace("<hh:underline", "<hh:bold/><hh:underline", 1)
    return out


def _append(xml: str, container: str, items: list[str]) -> str:
    idx = xml.index(f"</hh:{container}>")
    xml = xml[:idx] + "".join(items) + xml[idx:]
    return re.sub(
        rf'(<hh:{container} itemCnt=")(\d+)"',
        lambda m: f'{m.group(1)}{int(m.group(2)) + len(items)}"',
        xml,
        count=1,
    )


def main(out: Path = DEFAULT_OUT) -> Path:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    for p, c, text in LINES_BEFORE_TABLE:
        doc.add_paragraph(_tok(p, c) + text)
    util = doc.add_table(2, 1)
    util.set_cell_text(
        0, 0, _tok(UTIL[0][2], "c9") + f"{UTIL[0][0]}(   {{{{utilization:{UTIL[0][1]}}}}}   )"
    )
    cell0 = util.cell(0, 0)
    for label, option, p in UTIL[1:]:
        c = "c9b" if option == "commercialization" else "c9"
        cell0.add_paragraph(_tok(p, c) + f"{label}(   {{{{utilization:{option}}}}}   )")
    util.set_cell_text(
        1, 0, _tok("cell_label", "c10") + "실용화 계획 : 구체적으로 작성(필요시 별지 추가)"
    )
    util.cell(1, 0).add_paragraph(_tok("cell_label", "c10") + "  {{utilization}}")
    for p, c, text in LINES_AFTER_TABLE:
        doc.add_paragraph(_tok(p, c) + text)
    prop = doc.add_table(len(PROPOSER), 2)
    for r, row in enumerate(PROPOSER):
        for col, text in enumerate(row):
            prop.set_cell_text(r, col, _tok("prop", "c10") + text)
    data = doc.to_bytes()

    zin = zipfile.ZipFile(io.BytesIO(data))
    header = zin.read("Contents/header.xml").decode("utf-8")
    section = zin.read("Contents/section0.xml").decode("utf-8")
    para_ids = [int(x) for x in re.findall(r'<hh:paraPr id="(\d+)"', header)]
    char_ids = [int(x) for x in re.findall(r'<hh:charPr id="(\d+)"', header)]
    base_para = re.search(r'<hh:paraPr id="0"[^>]*>.*?</hh:paraPr>', header, re.S).group(0)
    base_char = re.search(r'<hh:charPr id="0"[^>]*>.*?</hh:charPr>', header, re.S).group(0)
    pid: dict[str, int] = {}
    new_paras = []
    for i, (name, (align, left, intent, spacing)) in enumerate(PARAS.items()):
        pid[name] = max(para_ids) + 1 + i
        xml = _para_xml(base_para, align, left, intent, spacing)
        new_paras.append(re.sub(r'id="\d+"', f'id="{pid[name]}"', xml, count=1))
    cid: dict[str, int] = {}
    new_chars = []
    for i, (name, (height, bold)) in enumerate(CHARS.items()):
        cid[name] = max(char_ids) + 1 + i
        xml = _char_xml(base_char, height, bold)
        new_chars.append(re.sub(r'id="\d+"', f'id="{cid[name]}"', xml, count=1))
    header = _append(header, "paraProperties", new_paras)
    header = _append(header, "charProperties", new_chars)

    def restyle(m: re.Match[str]) -> str:
        para = m.group(0)
        t = re.search(r"⟦(\w+)\|(\w+)⟧", para)
        if not t:
            return para
        p, c = t.group(1), t.group(2)
        para = para.replace(t.group(0), "", 1)
        para = re.sub(r'paraPrIDRef="\d+"', f'paraPrIDRef="{pid[p]}"', para, count=1)
        return re.sub(r'<hp:run charPrIDRef="\d+"', f'<hp:run charPrIDRef="{cid[c]}"', para)

    # 안쪽(칸) 단락부터: 표를 품지 않은 단락만 정규식으로 잡힌다
    section = re.sub(r"<hp:p [^>]*>(?:(?!<hp:p ).)*?</hp:p>", restyle, section, flags=re.S)
    assert "⟦" not in section, "스타일 표식이 남았습니다"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            if info.filename == "Contents/header.xml":
                body = header.encode("utf-8")
            elif info.filename == "Contents/section0.xml":
                body = section.encode("utf-8")
            else:
                body = zin.read(info)
            new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new.compress_type = info.compress_type
            new.external_attr = info.external_attr
            zout.writestr(new, body)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return out


if __name__ == "__main__":
    path = main(Path(sys.argv[1])) if len(sys.argv) > 1 else main()
    print(path, path.stat().st_size, "bytes")
