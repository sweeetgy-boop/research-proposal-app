"""[23] HWPX 쪽·본문 폭 읽기 — 그림 폭 = 본문 안쪽 폭 (2026-10-28 밤, ADR 0041).

이 앱이 만든(또는 실물 양식에서 채운) HWPX 의 section XML 에서 쪽 정의(hp:pagePr 폭·높이, hp:margin
좌우)를 읽고, 그림이 들어갈 단락의 단락 모양(paraPr 오른쪽·왼쪽 여백)을 뺀다. 그림 표식이 표 칸 안이면
칸 폭(hp:cellSz) − 칸 여백(hp:cellMargin) − 단락 여백. 글자는 읽지 않는다(속성 숫자만).

단위: HWPUNIT(1/7200 인치). 실물 양식(별지 제2호서식): 쪽 59528 × 84189, 좌우 여백 7086, 본문 단락(42)
오른쪽 1750 → 43606 = 153.8mm. 그림 단락은 서식 점검(hwpx_format)이 왼쪽 0·들여쓰기 0·가운데 정렬로
바꾸므로 왼쪽 여백·들여쓰기는 빼지 않는다(오른쪽 여백만 남는다).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from rra.adapters.rendering.hwpx_format import HEADER_PATH, _margin_part

_SECTION = re.compile(r"Contents/section\d+\.xml")
_PAGE = re.compile(r'<hp:pagePr\b[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"')
_MARGIN = re.compile(r"<hp:margin\b[^>]*>")
_PARA_PR = re.compile(r'<hh:paraPr id="(\d+)"[^>]*>.*?</hh:paraPr>', re.S)
_P_OPEN = re.compile(r'<hp:p\s[^>]*paraPrIDRef="(\d+)"')
_CELL_SZ = re.compile(r'<hp:cellSz width="(\d+)"')
_CELL_MARGIN = re.compile(r'<hp:cellMargin left="(\d+)" right="(\d+)"')
MAX_XML = 20 * 1024 * 1024  # section 하나 상한 (이 앱이 만든 파일)


@dataclass(frozen=True)
class PageGeometry:
    page_width: int
    page_height: int
    margin_left: int
    margin_right: int

    @property
    def text_width(self) -> int:
        return self.page_width - self.margin_left - self.margin_right


def _attr(tag: str, name: str) -> int:
    m = re.search(rf'\b{name}="(-?\d+)"', tag)
    return int(m.group(1)) if m else 0


def _margin(xml: str, tag: str) -> int:
    m = re.search(rf'<hc:{tag} value="(-?\d+)"', _margin_part(xml))
    return int(m.group(1)) if m else 0


def _read(data: bytes) -> tuple[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = sorted(n for n in zf.namelist() if _SECTION.fullmatch(n))
        if not names:
            raise ValueError("section 이 없습니다")
        info = zf.getinfo(names[0])
        if info.file_size > MAX_XML:
            raise ValueError("section 이 너무 큽니다")
        section = zf.read(names[0]).decode("utf-8")
        header = zf.read(HEADER_PATH).decode("utf-8") if HEADER_PATH in zf.namelist() else ""
    return section, header


def page_geometry(section_xml: str) -> PageGeometry | None:
    page = _PAGE.search(section_xml)
    if not page:
        return None
    margin = _MARGIN.search(section_xml, page.end())
    tag = margin.group(0) if margin else ""
    return PageGeometry(
        int(page.group(1)), int(page.group(2)), _attr(tag, "left"), _attr(tag, "right")
    )


def _para_rights(header_xml: str) -> dict[str, int]:
    return {m.group(1): max(0, _margin(m.group(0), "right")) for m in _PARA_PR.finditer(header_xml)}


def figure_width(section_xml: str, header_xml: str, index: int) -> int | None:
    """section_xml 의 글자 위치 index(그림 표식)가 든 단락에 그림을 넣을 때의 폭(HWPUNIT)."""
    page = page_geometry(section_xml)
    if page is None:
        return None
    rights = _para_rights(header_xml)
    p_start = section_xml.rfind("<hp:p ", 0, index)
    m = _P_OPEN.match(section_xml, p_start) if p_start >= 0 else None
    para_right = rights.get(m.group(1), 0) if m else 0
    tc = section_xml.rfind("<hp:tc", 0, index)
    tc_end = section_xml.rfind("</hp:tc>", 0, index)
    if tc > tc_end:  # 표 칸 안
        end = section_xml.find("</hp:tc>", index)
        cell = section_xml[tc : end if end > 0 else len(section_xml)]
        sz = _CELL_SZ.search(cell)
        cm = _CELL_MARGIN.search(cell)
        if sz:
            inner = int(sz.group(1)) - (int(cm.group(1)) + int(cm.group(2)) if cm else 0)
            return max(1, inner - para_right)
    return max(1, page.text_width - para_right)


def body_width(data: bytes, marker: str | None = None) -> tuple[int, int] | None:
    """(그림 폭, 쪽 높이) HWPUNIT. marker 가 있으면 그 표식이 든 단락 기준, 없으면 본문(표 밖) 자리표시자
    단락 중 가장 흔한 단락 모양 기준. 읽지 못하면 None."""
    try:
        section, header = _read(data)
    except (ValueError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
        return None
    page = page_geometry(section)
    if page is None:
        return None
    if marker and marker in section:
        width = figure_width(section, header, section.index(marker))
        return (width, page.page_height) if width else None
    widths: dict[int, int] = {}
    for m in re.finditer(r"\{\{[a-z_]+\}\}", section):
        tc, tc_end = section.rfind("<hp:tc", 0, m.start()), section.rfind("</hp:tc>", 0, m.start())
        if tc > tc_end:
            continue
        w = figure_width(section, header, m.start())
        if w:
            widths[w] = widths.get(w, 0) + 1
    if not widths:
        return page.text_width, page.page_height
    return max(widths, key=lambda k: widths[k]), page.page_height
