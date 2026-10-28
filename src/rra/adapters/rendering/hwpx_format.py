"""HWPX 서식 통일 — 줄맞춤(왼쪽 여백 + 내어쓰기)·글자 크기·표 칸 서식·그림 캡션 (항목 12).

렌더 결과(zip bytes)를 받아 단락마다 "있어야 할 서식"을 정하고, 다르면 고친 뒤 다시 점검한다.
HWPX 를 만들 때마다 돈다 (`HwpxRenderer.render`·`render_with_figures`).

단계(본문 영역 = 첫 장 제목 "1. " 이후, 표 밖 단락):
- 장 제목 "1. "            왼쪽 0, 13pt (양식 그대로)
- 항목 "가. "              왼쪽 600, 12pt
- 세부 "(1) "              왼쪽 1200, 12pt
- 줄표 "- "                왼쪽 1800, 12pt
- 본문 "○ " (생성 문장)    부모 단계 + 600 (장 1200 / 항목 1800 / 세부 2400), 12pt 보통
- 안내 "※"                 왼쪽 600, 글자는 양식 그대로
모든 단계는 내어쓰기(intent 음수)로 둘째 줄부터 머리표 뒤에 맞춘다. 공백 들여쓰기는 지운다.
줄 간격은 160%.

표 칸: 머리표 줄이 있는 칸(활용계획 목록·실용화 계획)은 칸마다 단락 모양 하나·글자 크기 하나 —
양식에서 그 칸이 가진 모양(가장 많이 쓴 것, 생성 문장이 있으면 그 칸 첫 단락 모양에
내어쓰기)을 쓴다.
그림: 그림 단락·캡션("그림 n. …")·출처 줄은 가운데 정렬, 12pt 보통.

보안 F: 글자를 새로 넣지 않는다 — 앞 공백 제거와 paraPrIDRef·charPrIDRef 변경, header.xml 에 같은
모양의 단락·글자 모양(복제)을 더하는 것뿐이다. 결과는 렌더러가 defusedxml 로 다시 파싱한다
(`verify_hwpx`). 바뀐 단락의 줄 배치 캐시(linesegarray)는 지운다 — 한/글이 다시 배치한다.
보고(FormatReport)에는 건수만 남긴다 (본문 없음).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import unescape

HEADER_PATH = "Contents/header.xml"
_SECTION_PATH = re.compile(r"Contents/section\d+\.xml")

BODY_HEIGHT = 1200  # 12pt (HWPUNIT: 1pt = 100)
CHAPTER_HEIGHT = 1300  # 장 제목 13pt — 양식 그대로
CAPTION_HEIGHT = 1200
LINE_SPACING = 160  # %
EM_HANG = 1.5  # 머리표 + 공백 폭 어림 (글자 크기 배수) — 칸 안 "○ " 내어쓰기


@dataclass(frozen=True)
class LevelStyle:
    """단계 하나의 단락 모양. left·hang 은 HWPUNIT, height 는 글자 크기(None 이면 그대로)."""

    left: int
    hang: int
    height: int | None
    body_char: bool = False  # True 면 run 글자 모양을 본문 글자(12pt 보통)로 바꾼다


LEVELS: dict[str, LevelStyle] = {
    "chapter": LevelStyle(0, 1700, CHAPTER_HEIGHT),
    "item": LevelStyle(600, 1800, BODY_HEIGHT),
    "sub": LevelStyle(1200, 2200, BODY_HEIGHT),
    "dash": LevelStyle(1800, 1100, BODY_HEIGHT),
    "bullet_chapter": LevelStyle(1200, 1800, BODY_HEIGHT, body_char=True),
    "bullet_item": LevelStyle(1800, 1800, BODY_HEIGHT, body_char=True),
    "bullet_sub": LevelStyle(2400, 1800, BODY_HEIGHT, body_char=True),
    "note": LevelStyle(600, 1500, None),
}
LEVEL_LABELS = {
    "chapter": "장 제목(1.)",
    "item": "항목(가.)",
    "sub": "세부(1))",
    "dash": "줄표(-)",
    "bullet_chapter": "본문 ○ (장 아래)",
    "bullet_item": "본문 ○ (항목 아래)",
    "bullet_sub": "본문 ○ (세부 아래)",
    "note": "안내(※)",
    "caption": "그림·캡션",
    "cell": "표 칸",
}
ISSUE_KINDS = ("level_style", "font_size", "leading_spaces", "cell_style", "caption")
ISSUE_LABELS = {
    "level_style": "단계별 단락 모양",
    "font_size": "글자 크기",
    "leading_spaces": "앞 공백 들여쓰기",
    "cell_style": "표 칸 서식 통일",
    "caption": "그림 캡션 서식",
}

_WS = " \t　 "
_CHAPTER = re.compile(r"^\d{1,2}\.\s")
_ITEM = re.compile(r"^[가-하]\.\s")
_SUB = re.compile(r"^\(\d{1,2}\)\s")
_DASH = re.compile(r"^-\s")
_NOTE = re.compile(r"^※")
_APPENDIX = re.compile(r"^별첨 \S+$")  # "별첨 그림" 머리 (그림 별첨)
_FIG_NOTE = re.compile(r"^\(별첨 .{1,20} 참조\)$")  # 본문 자리의 "(별첨 그림 n 참조)"
_CAPTION = re.compile(r"^그림 \d{1,3}\. ")

_TAGS = re.compile(
    r"<hp:p\s[^>]*>|</hp:p>|<hp:tc\b[^>]*>|</hp:tc>|<hp:tbl\b|<hp:pic\b|<hp:container\b"
)
_T = re.compile(r"<hp:t>([^<]*)</hp:t>")
_RUN = re.compile(r'<hp:run charPrIDRef="(\d+)"')
_LINESEG = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.S)
_CELL_ADDR = re.compile(r'<hp:cellAddr colAddr="(\d+)" rowAddr="(\d+)"/>')


# ── 보고 ─────────────────────────────────────────────────
@dataclass
class FormatReport:
    """서식 점검 결과 — 건수만 (본문 없음). fixed = 고친 단락 수(종류별), remaining = 고친 뒤
    남은 불일치(0 이어야 정상)."""

    paragraphs: int = 0  # 점검한 단락 수 (본문 단계·표 칸·캡션)
    fixed: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ISSUE_KINDS, 0))
    remaining: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ISSUE_KINDS, 0))
    styles_added: int = 0
    levels: dict[str, int] = field(default_factory=dict)  # 단계별 단락 수

    @property
    def ok(self) -> bool:
        return not any(self.remaining.values())

    @property
    def fixed_total(self) -> int:
        return sum(self.fixed.values())

    def payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "paragraphs": self.paragraphs,
            "fixed": dict(self.fixed),
            "fixed_total": self.fixed_total,
            "remaining": dict(self.remaining),
            "styles_added": self.styles_added,
            "levels": dict(sorted(self.levels.items())),
        }


# ── header.xml 단락·글자 모양 ──────────────────────────────
_PARA_PR = re.compile(r'<hh:paraPr id="(\d+)"[^>]*>.*?</hh:paraPr>', re.S)
_CHAR_PR = re.compile(r'<hh:charPr id="(\d+)"[^>]*>.*?</hh:charPr>', re.S)


@dataclass(frozen=True)
class ParaShape:
    align: str
    left: int
    intent: int
    spacing: int | None


def _attr_int(xml: str, tag: str) -> int:
    m = re.search(rf'<hc:{tag} value="(-?\d+)"', xml)
    return int(m.group(1)) if m else 0


def para_shape(xml: str) -> ParaShape:
    """paraPr XML → 정렬·왼쪽 여백·들여쓰기(case 값 = HWPUNIT)·줄 간격."""
    align = re.search(r'<hh:align horizontal="([A-Z_]+)"', xml)
    part = _margin_part(xml)
    ls = re.search(r'<hh:lineSpacing type="PERCENT" value="(\d+)"', part)
    return ParaShape(
        align.group(1) if align else "JUSTIFY",
        _attr_int(part, "left"),
        _attr_int(part, "intent"),
        int(ls.group(1)) if ls else None,
    )


class Header:
    """header.xml 의 paraPr·charPr 조회와 복제(같은 모양이 있으면 재사용)."""

    def __init__(self, xml: str):
        self.xml = xml
        self.paras = {m.group(1): m.group(0) for m in _PARA_PR.finditer(xml)}
        self.chars = {m.group(1): m.group(0) for m in _CHAR_PR.finditer(xml)}
        self._new_paras: list[str] = []
        self._new_chars: list[str] = []
        self._para_index = {_norm(v): k for k, v in self.paras.items()}
        self._char_index = {_norm(v): k for k, v in self.chars.items()}

    @property
    def added(self) -> int:
        return len(self._new_paras) + len(self._new_chars)

    def height(self, char_id: str) -> int | None:
        xml = self.chars.get(char_id)
        m = re.search(r'height="(\d+)"', xml or "")
        return int(m.group(1)) if m else None

    def bold(self, char_id: str) -> bool:
        return "<hh:bold/>" in (self.chars.get(char_id) or "")

    def shape(self, para_id: str) -> ParaShape | None:
        xml = self.paras.get(para_id)
        return para_shape(xml) if xml else None

    def para(
        self,
        base_id: str,
        *,
        left: int,
        intent: int,
        align: str | None = None,
        spacing: int | None = LINE_SPACING,
    ) -> str:
        """base 단락 모양에서 왼쪽 여백·들여쓰기·정렬·줄 간격만 바꾼 모양의 id.
        spacing None 이면 base 의 줄 간격 그대로 (표 칸)."""
        base = self.paras.get(base_id)
        if base is None:
            return base_id
        xml = base
        if align:
            xml = re.sub(r'(<hh:align horizontal=")[A-Z_]+"', rf'\g<1>{align}"', xml, count=1)
        xml = _set_margins(xml, left=left, intent=intent)
        if spacing is not None:
            xml = re.sub(
                r'(<hh:lineSpacing type=")[A-Z_]+(" value=")\d+"',
                rf'\g<1>PERCENT\g<2>{spacing}"',
                xml,
            )
        return self._find_or_add(xml, self.paras, self._para_index, self._new_paras)

    def char(self, base_id: str, *, height: int | None = None, bold: bool | None = None) -> str:
        """base 글자 모양에서 크기·굵게만 바꾼 모양의 id (같으면 base 그대로)."""
        base = self.chars.get(base_id)
        if base is None:
            return base_id
        xml = base
        if height is not None:
            xml = re.sub(
                r'(<hh:charPr id="\d+"[^>]*?height=")\d+"', rf'\g<1>{height}"', xml, count=1
            )
        if bold is False:
            xml = xml.replace("<hh:bold/>", "")
        return self._find_or_add(xml, self.chars, self._char_index, self._new_chars)

    def _find_or_add(
        self, xml: str, table: dict[str, str], index: dict[str, str], new: list[str]
    ) -> str:
        key = _norm(xml)
        if key in index:
            return index[key]
        new_id = str(max((int(k) for k in table), default=-1) + 1)
        xml = re.sub(r'id="\d+"', f'id="{new_id}"', xml, count=1)
        table[new_id] = xml
        index[key] = new_id
        new.append(xml)
        return new_id

    def render(self) -> str:
        xml = self.xml
        xml = _append(xml, "hh:paraProperties", self._new_paras)
        return _append(xml, "hh:charProperties", self._new_chars)


def _norm(xml: str) -> str:
    return re.sub(r'id="\d+"', "", xml, count=1)


_SWITCH = re.compile(r"<hp:switch>.*?</hp:switch>", re.S)


def _margin_part(xml: str) -> str:
    """여백이 든 hp:switch 의 hp:case 부분(HWPUNIT 그대로). switch 가 없으면 전체."""
    for m in _SWITCH.finditer(xml):
        block = m.group(0)
        if "<hh:margin>" in block:
            return block.split("<hp:default>")[0]
    return xml


def _set_margins(xml: str, *, left: int, intent: int) -> str:
    """hp:case(HwpUnitChar) 는 그대로, hp:default 는 2배 (한/글이 저장하는 두 값의 관계).
    여백이 없는 switch(제목 번호 등)는 건드리지 않는다."""

    def put(part: str, factor: int) -> str:
        part = re.sub(r'(<hc:intent value=")-?\d+"', rf'\g<1>{intent * factor}"', part)
        return re.sub(r'(<hc:left value=")-?\d+"', rf'\g<1>{left * factor}"', part)

    def block(m: re.Match[str]) -> str:
        text = m.group(0)
        if "<hh:margin>" not in text:
            return text
        if "<hp:default>" in text:
            head, tail = text.split("<hp:default>", 1)
            return put(head, 1) + "<hp:default>" + put(tail, 2)
        return put(text, 1)

    if _SWITCH.search(xml) and "<hh:margin>" in "".join(_SWITCH.findall(xml)):
        return _SWITCH.sub(block, xml)
    return put(xml, 1)


def _append(xml: str, container: str, items: list[str]) -> str:
    if not items:
        return xml
    close = f"</{container}>"
    idx = xml.find(close)
    if idx < 0:
        return xml
    xml = xml[:idx] + "".join(items) + xml[idx:]
    return re.sub(
        rf'(<{container} itemCnt=")(\d+)"',
        lambda m: f'{m.group(1)}{int(m.group(2)) + len(items)}"',
        xml,
        count=1,
    )


# ── 섹션 단락 ───────────────────────────────────────────
@dataclass
class Para:
    start: int
    end: int
    depth: int  # 0 = 섹션 바로 아래
    cell: tuple[int, int] | None  # 가장 안쪽 표 칸 (<hp:tc> 시작·끝)
    container: bool = False  # 표·그림 상자를 품은 단락
    pic: bool = False


def scan(xml: str) -> list[Para]:
    """섹션 XML 의 단락을 위치·깊이·소속 칸과 함께 (중첩 단락은 표 칸 안에서만)."""
    out: list[Para] = []
    stack: list[list[Any]] = []  # ["p", start, container, pic] | ["tc", start]
    for m in _TAGS.finditer(xml):
        tag = m.group(0)
        if tag == "<hp:pic":  # 그림은 가장 안쪽 단락에만 표시 ("<hp:p" 보다 먼저 본다)
            inner = next((s for s in reversed(stack) if s[0] == "p"), None)
            if inner is not None:
                inner[3] = True
        elif tag.startswith("<hp:p"):
            stack.append(["p", m.start(), False, False])
        elif tag == "</hp:p>":
            while stack and stack[-1][0] != "p":
                stack.pop()  # 깨진 구조 — 칸 표시를 버린다
            if not stack:
                continue
            _, start, container, pic = stack.pop()
            depth = sum(1 for s in stack if s[0] == "p")
            cell = next(((s[1], -1) for s in reversed(stack) if s[0] == "tc"), None)
            out.append(Para(start, m.end(), depth, cell, container, pic))
        elif tag.startswith("<hp:tc"):
            stack.append(["tc", m.start()])
        elif tag == "</hp:tc>":
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == "tc":
                    tc_start = stack[i][1]
                    for p in out:
                        if p.cell == (tc_start, -1):
                            p.cell = (tc_start, m.end())
                    del stack[i]
                    break
        else:  # <hp:tbl / <hp:container — 품고 있는 모든 단락에 표시
            for s in stack:
                if s[0] == "p":
                    s[2] = True
    out.sort(key=lambda p: p.start)
    return out


def para_text(para_xml: str) -> str:
    return "".join(unescape(t) for t in _T.findall(para_xml))


def _para_id(para_xml: str) -> str:
    m = re.search(r'paraPrIDRef="(\d+)"', para_xml[: para_xml.find(">")])
    return m.group(1) if m else "0"


def _runs(para_xml: str) -> list[str]:
    return _RUN.findall(para_xml)


def _visible_runs(para_xml: str) -> list[str]:
    """글자가 있는 run 의 charPr (빈 run 은 크기를 따지지 않는다)."""
    out = []
    for m in re.finditer(r'<hp:run charPrIDRef="(\d+)"(/>|>(.*?)</hp:run>)', para_xml, re.S):
        inner = m.group(3) or ""
        if any(t.strip(_WS) for t in _T.findall(inner)):
            out.append(m.group(1))
    return out


@dataclass
class Plan:
    """단락 하나를 어떻게 바꿀지 — None 은 그대로."""

    kind: str  # 단계 이름 | cell | caption
    para_id: str | None = None
    char_map: dict[str, str] = field(default_factory=dict)  # 원래 charPr → 바꿀 charPr
    strip: bool = True


def classify(text: str, bullet: str = "○") -> str | None:
    t = text.lstrip(_WS)
    if not t:
        return None
    if _CHAPTER.match(t) or _APPENDIX.match(t):
        return "chapter"
    if _ITEM.match(t):
        return "item"
    if _SUB.match(t):
        return "sub"
    if _DASH.match(t):
        return "dash"
    if t.startswith(bullet) or _FIG_NOTE.match(t):
        return "bullet"
    if _NOTE.match(t):
        return "note"
    return None


def _cell_has_markers(texts: Iterable[str], bullet: str) -> bool:
    return any(classify(t, bullet) in ("item", "bullet", "sub", "dash") for t in texts)


class _Planner:
    def __init__(self, header: Header, captions: Collection[str], bullet: str):
        self.h = header
        self.captions = {c.strip(_WS) for c in captions if c and c.strip(_WS)}
        self.bullet = bullet.strip() or "○"
        self.base_para: str | None = None
        self.body_char: str | None = None

    def is_caption(self, text: str, para: Para) -> bool:
        t = text.strip(_WS)
        return para.pic or (bool(t) and (t in self.captions or bool(_CAPTION.match(t))))

    def plan(self, xml: str, paras: list[Para]) -> dict[int, Plan]:
        leaf = [p for p in paras if not p.container or p.pic]
        texts = {p.start: para_text(xml[p.start : p.end]) for p in leaf}
        top = [p for p in leaf if p.depth == 0 and p.cell is None]
        # 기준 모양: 첫 장 제목 단락(양식 본문 단락 모양)과 첫 항목 run(본문 글자)
        for p in top:
            kind = classify(texts[p.start], self.bullet)
            if kind == "chapter" and self.base_para is None:
                self.base_para = _para_id(xml[p.start : p.end])
            if kind == "item" and self.body_char is None:
                runs = _visible_runs(xml[p.start : p.end]) or _runs(xml[p.start : p.end])
                if runs:
                    self.body_char = runs[0]
        if self.base_para is None and leaf:
            self.base_para = _para_id(xml[leaf[0].start : leaf[0].end])
        if self.body_char is None:
            for p in leaf:
                runs = _visible_runs(xml[p.start : p.end])
                if runs:
                    self.body_char = runs[0]
                    break
        body = (
            self.h.char(self.body_char, height=BODY_HEIGHT, bold=False)
            if self.body_char is not None
            else None
        )
        plans: dict[int, Plan] = {}
        started, parent = False, "chapter"
        for p in top:
            text = texts[p.start]
            if self.is_caption(text, p):
                plans[p.start] = self._caption(xml, p, body)
                continue
            kind = classify(text, self.bullet)
            if kind == "chapter" and not _APPENDIX.match(text.strip(_WS)):
                started = True
            if not started or kind is None:
                continue
            if kind in ("chapter", "item", "sub"):
                parent = kind
            level = f"bullet_{parent}" if kind == "bullet" else kind
            plans[p.start] = self._level(xml, p, level, body)
        # 표 칸 — 머리표 줄이 있는 칸만 (제안자 표 같은 칸은 그대로)
        cells: dict[tuple[int, int], list[Para]] = {}
        for p in leaf:
            if p.cell is not None:
                cells.setdefault(p.cell, []).append(p)
        for members in cells.values():
            caps = [p for p in members if self.is_caption(texts[p.start], p)]
            for p in caps:
                plans[p.start] = self._caption(xml, p, body)
            rest = [p for p in members if p not in caps]
            if not rest or not _cell_has_markers((texts[p.start] for p in rest), self.bullet):
                continue
            for start, plan in self._cell(xml, rest, texts).items():
                plans[start] = plan
        return plans

    def _level(self, xml: str, p: Para, level: str, body: str | None) -> Plan:
        style = LEVELS[level]
        para_xml = xml[p.start : p.end]
        base = self.base_para or _para_id(para_xml)
        target = self.h.para(base, left=style.left, intent=-style.hang)
        char_map: dict[str, str] = {}
        for cid in set(_runs(para_xml)):
            if style.body_char and body is not None:
                char_map[cid] = body
            elif style.height is not None and self.h.height(cid) != style.height:
                char_map[cid] = self.h.char(cid, height=style.height)
        return Plan(level, target, char_map)

    def _caption(self, xml: str, p: Para, body: str | None) -> Plan:
        para_xml = xml[p.start : p.end]
        base = self.base_para or _para_id(para_xml)
        target = self.h.para(base, left=0, intent=0, align="CENTER")
        char_map: dict[str, str] = {}
        for cid in set(_runs(para_xml)):
            if body is not None and (self.h.height(cid) != CAPTION_HEIGHT or self.h.bold(cid)):
                char_map[cid] = self.h.char(body, height=CAPTION_HEIGHT, bold=False)
        return Plan("caption", target, char_map)

    def _cell(self, xml: str, members: list[Para], texts: dict[int, str]) -> dict[int, Plan]:
        ids = [_para_id(xml[p.start : p.end]) for p in members if texts[p.start].strip(_WS)]
        ids = ids or [_para_id(xml[members[0].start : members[0].end])]
        heights: Counter[int] = Counter()
        for p in members:
            for cid in _visible_runs(xml[p.start : p.end]):
                h = self.h.height(cid)
                if h is not None:
                    heights[h] += 1
        size = heights.most_common(1)[0][0] if heights else None
        has_bullet = any(classify(texts[p.start], self.bullet) == "bullet" for p in members)
        if has_bullet:
            first = ids[0]
            hang = round((size or BODY_HEIGHT) * EM_HANG)
            target = self.h.para(first, left=0, intent=-hang, spacing=None)
        else:
            target = Counter(ids).most_common(1)[0][0]  # 칸의 원래 모양 중 가장 많이 쓴 것
        out: dict[int, Plan] = {}
        for p in members:
            char_map: dict[str, str] = {}
            if size is not None:
                for cid in set(_runs(xml[p.start : p.end])):
                    if self.h.height(cid) not in (None, size):
                        char_map[cid] = self.h.char(cid, height=size)
            out[p.start] = Plan("cell", target, char_map)
        return out


def _has_leading_ws(para_xml: str) -> bool:
    """보이는 첫 글자 앞에 공백이 있나 (공백만 있는 run 도 앞 공백으로 본다)."""
    joined = para_text(para_xml)
    return bool(joined.strip(_WS)) and joined[0] in _WS


def _strip_leading(para_xml: str) -> str:
    done = False

    def fix(m: re.Match[str]) -> str:
        nonlocal done
        if done:
            return m.group(0)
        raw = m.group(1)
        text = unescape(raw)
        if not text:
            return m.group(0)
        stripped = text.lstrip(_WS)
        if stripped:
            done = True
        # 지우는 건 앞 공백 글자뿐 — 남은 부분은 원래 (escape 된) 문자열 그대로
        cut = len(text) - len(stripped)
        return "<hp:t>" + _drop_chars(raw, cut) + "</hp:t>"

    return _T.sub(fix, para_xml)


def _drop_chars(raw: str, n: int) -> str:
    """escape 된 문자열에서 앞 n 글자(공백류, 엔티티 아님)를 지운다."""
    i = 0
    while n > 0 and i < len(raw):
        if raw[i] == "&":  # 공백류는 엔티티가 아니다 (&#160; 은 남긴다 — 드묾)
            break
        i += 1
        n -= 1
    return raw[i:]


def _issues(header: Header, para_xml: str, plan: Plan) -> list[str]:
    out: list[str] = []
    kind = {"cell": "cell_style", "caption": "caption"}.get(plan.kind, "level_style")
    if plan.para_id is not None and _para_id(para_xml) != plan.para_id:
        out.append(kind)
    runs = set(_runs(para_xml))
    if any(cid in plan.char_map and plan.char_map[cid] != cid for cid in runs):
        out.append("font_size" if kind == "level_style" else kind)
    if plan.strip and _has_leading_ws(para_xml):
        out.append("leading_spaces")
    return list(dict.fromkeys(out))


def _apply(para_xml: str, plan: Plan) -> str:
    out = para_xml
    if plan.para_id is not None:
        head_end = out.find(">")
        head = re.sub(
            r'paraPrIDRef="\d+"', f'paraPrIDRef="{plan.para_id}"', out[:head_end], count=1
        )
        out = head + out[head_end:]
    if plan.char_map:
        out = _RUN.sub(
            lambda m: f'<hp:run charPrIDRef="{plan.char_map.get(m.group(1), m.group(1))}"', out
        )
    if plan.strip:
        out = _strip_leading(out)
    return _LINESEG.sub("", out)


def format_section(
    xml: str, header: Header, *, captions: Collection[str] = (), bullet: str = "○"
) -> tuple[str, dict[str, int], dict[str, int], int]:
    """섹션 하나 — (고친 XML, 고친 단락 수(종류별), 단계별 단락 수, 점검 단락 수)."""
    paras = scan(xml)
    plans = _Planner(header, captions, bullet).plan(xml, paras)
    fixed = dict.fromkeys(ISSUE_KINDS, 0)
    levels: dict[str, int] = {}
    for start in sorted(plans, reverse=True):
        p = next(q for q in paras if q.start == start)
        plan = plans[start]
        para_xml = xml[p.start : p.end]
        levels[plan.kind] = levels.get(plan.kind, 0) + 1
        problems = _issues(header, para_xml, plan)
        for k in problems:
            fixed[k] += 1
        if problems:
            xml = xml[: p.start] + _apply(para_xml, plan) + xml[p.end :]
    return xml, fixed, levels, len(plans)


def check_section(
    xml: str, header: Header, *, captions: Collection[str] = (), bullet: str = "○"
) -> dict[str, int]:
    """고치지 않고 불일치만 센다 (종류별 단락 수)."""
    paras = scan(xml)
    plans = _Planner(header, captions, bullet).plan(xml, paras)
    counts = dict.fromkeys(ISSUE_KINDS, 0)
    for p in paras:
        plan = plans.get(p.start)
        if plan is None:
            continue
        for k in _issues(header, xml[p.start : p.end], plan):
            counts[k] += 1
    return counts


# ── zip 단위 ─────────────────────────────────────────────
def _read(data: bytes) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        infos = zin.infolist()
        return infos, {i.filename: zin.read(i) for i in infos}


def _write(infos: list[zipfile.ZipInfo], parts: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for info in infos:  # 순서·압축 방식 유지 (mimetype 은 첫 항목, 무압축)
            new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new.compress_type = info.compress_type
            new.external_attr = info.external_attr
            zout.writestr(new, parts[info.filename])
    return buf.getvalue()


def format_hwpx(
    data: bytes, *, captions: Collection[str] = (), bullet: str = "○"
) -> tuple[bytes, FormatReport]:
    """HWPX 서식 점검 + 고침. 고친 뒤 다시 점검해 남은 불일치를 remaining 에 센다."""
    infos, parts = _read(data)
    if HEADER_PATH not in parts:
        return data, FormatReport()
    header = Header(parts[HEADER_PATH].decode("utf-8"))
    report = FormatReport()
    sections = [i.filename for i in infos if _SECTION_PATH.fullmatch(i.filename)]
    changed = False
    for name in sections:
        xml = parts[name].decode("utf-8")
        new_xml, fixed, levels, n = format_section(xml, header, captions=captions, bullet=bullet)
        report.paragraphs += n
        for k, v in fixed.items():
            report.fixed[k] += v
        for k, v in levels.items():
            report.levels[k] = report.levels.get(k, 0) + v
        if new_xml != xml:
            parts[name] = new_xml.encode("utf-8")
            changed = True
    report.styles_added = header.added
    if header.added:
        parts[HEADER_PATH] = header.render().encode("utf-8")
        changed = True
    for name in sections:  # 다시 점검 — 같은 계획으로 0 이어야 한다
        again = check_section(parts[name].decode("utf-8"), header, captions=captions, bullet=bullet)
        for k, v in again.items():
            report.remaining[k] += v
    return (_write(infos, parts) if changed else data), report


def inspect_hwpx(data: bytes, *, bullet: str = "○") -> list[dict[str, Any]]:
    """단락별 서식 표 (측정 문서용) — 단계·정렬·왼쪽 여백·내어쓰기·줄 간격·글자 크기·앞 공백.
    본문은 넣지 않고 머리표만 (예: "가.", "○")."""
    infos, parts = _read(data)
    header = Header(parts.get(HEADER_PATH, b"").decode("utf-8"))
    rows: list[dict[str, Any]] = []
    for info in infos:
        if not _SECTION_PATH.fullmatch(info.filename):
            continue
        xml = parts[info.filename].decode("utf-8")
        paras = scan(xml)
        plans = _Planner(header, (), bullet).plan(xml, paras)
        for p in paras:
            if p.container and not p.pic:
                continue
            para_xml = xml[p.start : p.end]
            text = para_text(para_xml)
            plan = plans.get(p.start)
            shape = header.shape(_para_id(para_xml))
            heights = sorted(
                {h / 100 for c in _visible_runs(para_xml) if (h := header.height(c)) is not None}
            )
            rows.append(
                {
                    "level": plan.kind if plan else ("표 칸" if p.cell else "-"),
                    "marker": _marker(text, bullet),
                    "in_cell": p.cell is not None,
                    "para": _para_id(para_xml),
                    "align": shape.align if shape else "?",
                    "left": shape.left if shape else 0,
                    "hang": -shape.intent if shape and shape.intent < 0 else 0,
                    "spacing": shape.spacing if shape else None,
                    "pt": heights,
                    "leading_space": _has_leading_ws(para_xml),
                }
            )
    return rows


def _marker(text: str, bullet: str) -> str:
    t = text.lstrip(_WS)
    for pat in (_CHAPTER, _ITEM, _SUB, _DASH):
        m = pat.match(t)
        if m:
            return m.group(0).strip()
    if t.startswith(bullet):
        return bullet
    if _NOTE.match(t):
        return "※"
    if _CAPTION.match(t):
        return "그림 n."
    return "" if not t.strip() else "…"
