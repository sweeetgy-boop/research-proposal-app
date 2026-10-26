"""실물 양식(별지 제2호서식, 2024.02.19.) HWPX 에 자리표시자를 넣어 템플릿을 만든다.

    .venv/bin/python tools/build_form_template.py \\
        data/templates/proposal_form_original.hwpx config/templates/proposal_korail.hwpx

- 원본과 결과는 커밋하지 않는다 (data/ 와 config/templates/proposal_korail.hwpx 는 .gitignore).
- section0.xml 문자열만 바꾼다. 다른 zip 항목(header.xml·미리보기 등)은 바이트 그대로 복사한다.
- 자리표시자는 slots.yaml 에 선언된 것만, 각각 정확히 한 번, 칸 안의 한 run(<hp:t>) 에 넣는다.
  글꼴·크기·단락 모양은 그 run·단락의 것을 그대로 쓴다 (charPr·paraPr 을 만들지 않는다).
- 체크 칸은 양식의 괄호를 유지하고 괄호 안에 선택지별 자리표시자를 넣는다 → 렌더 때 ( ○ ) / (   ).
- 여러 문장 섹션은 제목 아래에 본문 단락(제목 단락의 paraPr·charPr 복제)을 하나 만들어 자리표시자를
  넣는다. 렌더러(adapters/rendering/hwpx.py expand_paragraphs)가 문장마다 그 단락을 복제한다.
- 모든 고정 문구(앵커)는 원본에 정확히 한 번 있어야 한다. 양식이 바뀌어 앵커가 없거나 여러 개면
  멈춘다 — 추측해서 넣지 않는다.
- 끝으로 defusedxml 재파싱, 자리표시자 전수 대조(선언 == 삽입, 각 1회)를 통과해야 저장한다.

매핑표(2026-10-26 확인) 는 docs/architecture.md §4.4 Step 8 참고.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SLOTS_YAML = ROOT / "config" / "templates" / "proposal_korail.slots.yaml"
DEFAULT_SRC = ROOT / "data" / "templates" / "proposal_form_original.hwpx"
DEFAULT_OUT = ROOT / "config" / "templates" / "proposal_korail.hwpx"
SECTION = "Contents/section0.xml"
_PLACEHOLDER = re.compile(r"\{\{[^{}]{1,40}\}\}")
P_OPEN, P_CLOSE = "<hp:p ", "</hp:p>"

# 양식의 표 id (원본 section0.xml). 활용계획 표 / 제안자 표
TBL_UTILIZATION = "1230389247"
TBL_PROPOSER = "1230389248"

# ── 1) 인라인 치환: (앵커 <hp:t> 문구, 바꿀 문구). 앵커는 원본에 정확히 한 번 ──
INLINE: list[tuple[str, str]] = [
    ("<hp:t> 가. 연구과제명 : </hp:t>", "<hp:t> 가. 연구과제명 : {{title}}</hp:t>"),
    ("<hp:t>예산과목                </hp:t>", "<hp:t>예산과목 {{budget.account}}</hp:t>"),
    ("<hp:t>금액  :         천원</hp:t>", "<hp:t>금액 : {{budget.amount}} 천원</hp:t>"),
    (
        "기초연구(   ), 응용연구(   ), 개발연구(   )",
        "기초연구( {{task_type:basic}} ), 응용연구( {{task_type:applied}} ), "
        "개발연구( {{task_type:development}} )",
    ),
    (
        "<hp:t>   - 전략방향 : </hp:t>",
        "<hp:t>   - 전략방향 : {{strategy_alignment:direction}}</hp:t>",
    ),
    ("<hp:t>   - 전략과제 : </hp:t>", "<hp:t>   - 전략과제 : {{strategy_alignment:task}}</hp:t>"),
]

# 4. 활용계획 가~차 — 라벨 문구(원본 그대로) → 선택지 id. "(       )" 7칸을 "(   {{…}}   )" 로
UTILIZATION_LABELS: list[tuple[str, str]] = [
    ("가. 중장기 전략 및 주요업무계획 반영", "strategy_plan"),
    ("나. 제도(규정 및 업무처리 기준 등) 제・개정", "regulation"),
    ("다. 사업 타당성 검토 및 경영의사결정 근거자료 활용", "feasibility"),
    ("라. 외부기관 협상 근거자료 활용", "negotiation"),
    ("마. 새로운 시설・설비 또는 유지보수 시스템・방법의 개발 및 운영방법 개선", "facility_method"),
    ("바. 차량 및 기존 시설물의 개량 또는 대체", "rolling_stock"),
    ("사. 컴퓨터 프로그램의 개발 및 제공", "software"),
    ("아. 매뉴얼 작성 및 배포", "manual"),
    ("자. 기타", "other"),
    ("차. 실용화계획 있음", "commercialization"),
]

# ── 2) 제목 아래 본문 단락: (제목 <hp:t> 문구, 자리표시자, 본문 앞 들여쓰기) ──
# 제목 단락(paraPr·charPr)을 복제해 바로 뒤에 넣는다.
BODY_AFTER_HEADING: list[tuple[str, str, str]] = [
    ("  (1) 정책적 중요도", "{{policy_importance}}", "    "),
    ("  (2) 기술적 중요도", "{{tech_importance}}", "    "),
    ("   - 전략과제 : {{strategy_alignment:task}}", "{{strategy_alignment}}", "    "),
    (" 나. 연구목적", "{{objective}}", "   "),
    (" 다. 연구 방법 및 주요내용 ", "{{method}}", "   "),  # 원본의 9pt 빈 단락은 그대로 둔다
    ("  가. 경영혁신 측면", "{{expected_management}}", "    "),
    ("  나. 기술혁신 측면", "{{expected_technology}}", "    "),
    ("  다. 대외위상 측면", "{{expected_standing}}", "    "),
    ("5. 특이사항 :", "{{overlap_review}}", "  "),
]

# ── 3) 제안자 표 셀: (row, col) → 셀 안 <hp:t> 를 통째로 바꿀 문구 (None 이면 빈 run 에 넣는다) ──
PROPOSER_CELLS: list[tuple[int, int, str | None, str]] = [
    (0, 1, "  20    .        .        .", "{{proposed_on}}"),
    (1, 1, None, "{{department}}"),
    (3, 1, " ☏ (    )      - 　  　", "☏ {{proposer.phone}}"),
    (3, 2, " ☏ (    )      - 　  　", "☏ {{head.phone}}"),
    (4, 1, None, "{{proposer.rank}}"),
    (4, 2, None, "{{head.rank}}"),
    (5, 1, "          　　　(인)", "{{proposer.name}}  (인)"),
    (5, 2, "          　　　(인)", "{{head.name}}  (인)"),
]
UTILIZATION_BODY = ("실용화 계획 : 구체적으로 작성(필요시 별지 추가)", "{{utilization}}", "  ")


class FormChanged(RuntimeError):
    """양식 원본이 분석 때와 달라 앵커를 찾을 수 없다 (또는 여러 개)."""


def _once(xml: str, anchor: str) -> int:
    n = xml.count(anchor)
    if n != 1:
        raise FormChanged(f"앵커가 {n}번 나옵니다 (1번이어야 함): {anchor!r}")
    return xml.index(anchor)


def _paragraph_bounds(xml: str, inner_idx: int) -> tuple[int, int]:
    start = xml.rfind(P_OPEN, 0, inner_idx)
    end = xml.find(P_CLOSE, inner_idx)
    if start < 0 or end < 0:
        raise FormChanged("단락 경계를 찾을 수 없습니다.")
    end += len(P_CLOSE)
    para = xml[start:end]
    if para.count(P_OPEN) != 1 or "<hp:tbl" in para:
        raise FormChanged("단락 안에 표·중첩 단락이 있습니다.")
    return start, end


def _clone_body_paragraph(para: str, text: str) -> str:
    """제목 단락을 복제해 본문 단락으로: 첫 <hp:t>…</hp:t> 의 글자만 바꾸고 나머지는 그대로."""
    runs = re.findall(r"<hp:t>[^<]*</hp:t>", para)
    if not runs:
        raise FormChanged("복제할 단락에 <hp:t> 가 없습니다.")
    body = para.replace(runs[0], f"<hp:t>{text}</hp:t>", 1)
    for extra in runs[1:]:  # 제목에 run 이 여러 개면 뒤 run 은 비운다
        body = body.replace(extra, "<hp:t></hp:t>", 1)
    return body


def _insert_body_after(xml: str, heading: str, placeholder: str, indent: str) -> str:
    idx = _once(xml, f"<hp:t>{heading}</hp:t>")
    start, end = _paragraph_bounds(xml, idx)
    body = _clone_body_paragraph(xml[start:end], indent + placeholder)
    return xml[:end] + body + xml[end:]


def _table_bounds(xml: str, tbl_id: str) -> tuple[int, int]:
    start = _once(xml, f'<hp:tbl id="{tbl_id}"')
    depth, i = 0, start
    while True:
        nxt_open = xml.find("<hp:tbl ", i)
        nxt_close = xml.find("</hp:tbl>", i)
        if nxt_close < 0:
            raise FormChanged("표 끝을 찾을 수 없습니다.")
        if 0 <= nxt_open < nxt_close:
            depth, i = depth + 1, nxt_open + 1
        else:
            depth, i = depth - 1, nxt_close + len("</hp:tbl>")
            if depth == 0:
                return start, i


def _cell_bounds(xml: str, tbl_id: str, row: int, col: int) -> tuple[int, int]:
    """표의 (row, col) 셀 subList 범위. cellAddr 는 subList 뒤에 온다."""
    t0, t1 = _table_bounds(xml, tbl_id)
    table = xml[t0:t1]
    addr = f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
    a = _once(table, addr)
    sub_start = table.rfind("<hp:subList", 0, a)
    sub_end = table.rfind("</hp:subList>", 0, a)
    if sub_start < 0 or sub_end < 0 or sub_end < sub_start:
        raise FormChanged(f"셀 ({row},{col}) subList 를 찾을 수 없습니다.")
    return t0 + sub_start, t0 + sub_end


def _replace_in_cell(xml: str, tbl_id: str, row: int, col: int, old: str | None, new: str) -> str:
    s, e = _cell_bounds(xml, tbl_id, row, col)
    cell = xml[s:e]
    if old is None:  # 빈 셀: 자기 닫힘 run 하나 → 그 charPr 로 텍스트 run
        empties = re.findall(r'<hp:run charPrIDRef="\d+"/>', cell)
        if len(empties) != 1 or "<hp:t>" in cell:
            raise FormChanged(f"셀 ({row},{col}) 이 비어 있지 않습니다.")
        cell = cell.replace(empties[0], empties[0][:-2] + f"><hp:t>{new}</hp:t></hp:run>")
    else:
        anchor = f"<hp:t>{old}</hp:t>"
        if cell.count(anchor) != 1:
            raise FormChanged(f"셀 ({row},{col}) 앵커가 없습니다: {old!r}")
        cell = cell.replace(anchor, f"<hp:t>{new}</hp:t>")
    return xml[:s] + cell + xml[e:]


def build_section(xml: str) -> str:
    if "{{" in xml:
        raise FormChanged("원본에 이미 '{{' 가 있습니다.")
    # 1) 인라인
    for anchor, new in INLINE:
        _once(xml, anchor)
        xml = xml.replace(anchor, new)
    # 4. 활용계획 체크 칸 — 각 라벨 바로 뒤의 "(       )" (라벨과 같은 run 이거나 바로 다음 run)
    for label, option in UTILIZATION_LABELS:
        same_run = f"<hp:t>{label}(       )</hp:t>"
        next_run = f'<hp:t>{label}</hp:t></hp:run><hp:run charPrIDRef="22"><hp:t>(       )</hp:t>'
        mark = f"(   {{{{utilization:{option}}}}}   )"
        if xml.count(same_run) == 1:
            xml = xml.replace(same_run, f"<hp:t>{label}{mark}</hp:t>")
        elif xml.count(next_run) == 1:
            xml = xml.replace(next_run, next_run.replace("(       )", mark))
        else:
            raise FormChanged(f"활용계획 체크 칸을 찾을 수 없습니다: {label!r}")
    # 2) 제목 아래 본문 단락
    for heading, placeholder, indent in BODY_AFTER_HEADING:
        xml = _insert_body_after(xml, heading, placeholder, indent)
    # 4. 실용화 계획: 표 r1c0 라벨 단락 아래에 본문 단락
    s, e = _cell_bounds(xml, TBL_UTILIZATION, 1, 0)
    cell = xml[s:e]
    label, placeholder, indent = UTILIZATION_BODY
    idx = cell.index(f"<hp:t>{label}</hp:t>") if cell.count(f"<hp:t>{label}</hp:t>") == 1 else -1
    if idx < 0:
        raise FormChanged("실용화 계획 라벨을 찾을 수 없습니다.")
    ps, pe = _paragraph_bounds(cell, idx)
    cell = cell[:pe] + _clone_body_paragraph(cell[ps:pe], indent + placeholder) + cell[pe:]
    xml = xml[:s] + cell + xml[e:]
    # 3) 제안자 표
    for row, col, old, new in PROPOSER_CELLS:
        xml = _replace_in_cell(xml, TBL_PROPOSER, row, col, old, new)
    return xml


def declared_placeholders(slots_yaml: Path = SLOTS_YAML) -> set[str]:
    data = yaml.safe_load(slots_yaml.read_text(encoding="utf-8"))
    out: set[str] = set()
    for section in ("text", "input", "render_only"):
        out |= {str(v).strip() for v in (data.get(section) or {}).values()}
    for opts in (data.get("choice") or {}).values():
        out |= {str(v).strip() for v in (opts or {}).values()}
    return out


def check_section(xml: str, declared: set[str]) -> None:
    import defusedxml.ElementTree as DET

    DET.fromstring(xml.encode("utf-8"))
    found = _PLACEHOLDER.findall(xml)
    dupes = sorted({p for p in found if found.count(p) != 1})
    if dupes:
        raise FormChanged(f"자리표시자가 여러 번 들어갔습니다: {dupes}")
    missing, unknown = sorted(declared - set(found)), sorted(set(found) - declared)
    if missing or unknown:
        raise FormChanged(f"slots.yaml 대조 실패 — 빠짐 {missing} / 선언 안 됨 {unknown}")
    # 자리표시자는 한 run 안에: <hp:t>…{{x}}…</hp:t> 밖에서 발견되면 실패
    for ph in found:
        i = xml.index(ph)
        if xml.rfind("<hp:t>", 0, i) < xml.rfind("</hp:t>", 0, i):
            raise FormChanged(f"{ph} 가 <hp:t> 밖에 있습니다.")


def build(src: Path, out: Path, slots_yaml: Path = SLOTS_YAML) -> dict[str, int]:
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        extra = [n for n in names if re.fullmatch(r"Contents/section[1-9]\d*\.xml", n)]
        if SECTION not in names or extra:
            raise FormChanged("섹션은 Contents/section0.xml 하나여야 합니다.")
        xml = build_section(zin.read(SECTION).decode("utf-8"))
        check_section(xml, declared_placeholders(slots_yaml))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zout:
            for info in zin.infolist():  # 순서·압축 방식 유지 (mimetype 은 첫 항목, 무압축)
                data = xml.encode("utf-8") if info.filename == SECTION else zin.read(info)
                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                zout.writestr(new_info, data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return {"placeholders": len(_PLACEHOLDER.findall(xml)), "bytes": len(buf.getvalue())}


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else DEFAULT_SRC
    out = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    if not src.is_file():
        print(f"원본이 없습니다: {src}", file=sys.stderr)
        return 2
    try:
        stats = build(src, out)
    except FormChanged as exc:
        print(f"양식 구조가 분석 때와 다릅니다 — 중단: {exc}", file=sys.stderr)
        return 1
    print(f"저장: {out} ({stats['bytes']:,} bytes, 자리표시자 {stats['placeholders']}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
