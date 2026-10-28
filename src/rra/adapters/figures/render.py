"""그림 명세 → 템플릿 SVG 밑그림 ([G] 2026-10-28, architecture §4.16).

순수 파이썬(문자열 조립)으로 종류별 SVG 를 만든다. 외부 참조·스크립트·`<style>`·이미지 없음,
글자는 전부 XML escape(명세 글자는 LLM 출력 = 비신뢰). 좌표계는 폭 1600 기준 viewBox 고정,
width/height 속성은 `width_px`·`aspect` 로 정한다(PNG 픽셀 폭 = width × zoom).

- 글자는 `texts_of(spec)` 의 모든 문자열이 그대로 들어간다(수치 그래프 출처 캡션만 예외 — HWPX 캡션 아래
  12pt 출처 줄이 맡는다, [23]). 여러 줄로 나뉘는 글자는 `<tspan>` 으로 쪼개고 원문을 `aria-label` 에 함께 둔다.
- 긴 한글은 `wrap_text` 로 줄바꿈(띄어쓰기 우선, 없으면 글자 수) + 상자를 넘치면 글자 크기 축소.
  폭 추정: CJK 0.95em, 라틴 0.55em.
- 흑백 인쇄: 계열마다 명도가 다른 채움 + 무늬(점·빗금·격자) 덧씌움 + 선 모양(dasharray).
  제안 과제 열·현재 단계는 `accent`.
- [23] 가로 배치·글자 하한(2026-10-28 밤, ADR 0041): 그림은 본문 폭(실물 양식 153.8mm)에 꽉 채워 넣으므로
  viewBox 글자 1단위 ≈ 0.27pt. `min_font`(기본 9pt 에 해당하는 33단위) 밑으로는 줄이지 않고, 그래도 칸에
  안 들어가면 넘침으로 세어 root `data-overflow` 에 적는다 — 유스케이스가 글자를 줄여 다시 그린다.
  본문 글자 37(≈10pt)·머리글 42~46. 분석 기법 묶음은 `arrange`(row·split·flow·grid·table)로 가로 배치.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape

from pydantic import BaseModel

from rra.domain.models.figure import (
    KIND_LABEL,
    AsIsToBeSpec,
    ComparisonSpec,
    ConceptSpec,
    ProcessSpec,
    RoadmapSpec,
    ScheduleSpec,
    StatChartSpec,
    TechniqueSpec,
)
from rra.domain.rules.figure_fit import MIN_TEXT_PT, min_font_units
from rra.domain.rules.figures import NO_INFO, technique_arrangement

BASE_W = 1600  # viewBox 폭 (좌표계 기준)
FONT = "Pretendard"
CJK_EM = 0.95
LATIN_EM = 0.55
LINE_GAP = 1.3
# 본문 폭 153.8mm 에 넣었을 때 9pt (실물 양식 기준). 예전 하한 11 은 3pt 였다
MIN_FONT = math.ceil(min_font_units(MIN_TEXT_PT, 43606 * 25.4 / 7200) * 10) / 10
F_BODY = 37.0  # ≈ 10pt
F_HEAD = 42.0
F_TITLE = 46.0
F_SMALL = 34.0  # ≈ 9.3pt — 이름표·눈금·안내문
_DEFAULT_SERIES = (
    {"fill": "#dbe7f3", "stroke": "#1f4e79", "pattern": "solid", "dash": ""},
    {"fill": "#9fc0dc", "stroke": "#1f4e79", "pattern": "dots", "dash": "6 3"},
    {"fill": "#5f8fb8", "stroke": "#123a5c", "pattern": "hatch", "dash": "2 2"},
    {"fill": "#2b5f8e", "stroke": "#0b2d4d", "pattern": "cross", "dash": "8 3 2 3"},
)


# ── 공용 ───────────────────────────────────────────────────
def figure_size(aspect: str, width_px: int = BASE_W) -> tuple[int, int]:
    """'16:9' → (width_px, height_px). 모르는 비율은 16:9."""
    try:
        a, b = (float(x) for x in aspect.split(":", 1))
        if a <= 0 or b <= 0:
            raise ValueError(aspect)
    except (ValueError, AttributeError):
        a, b = 16.0, 9.0
    return int(width_px), int(round(width_px * b / a))


def text_width(text: str, font_size: float) -> float:
    """대략 폭(px) — CJK 0.95em, 그 외 0.55em."""
    w = 0.0
    for ch in text:
        w += font_size * (CJK_EM if ord(ch) > 0x2E7F else LATIN_EM)
    return w


def wrap_text(text: str, max_chars: int) -> list[str]:
    """띄어쓰기 단위로 줄을 채우고, 한 단어가 길면 글자 수로 자른다. 항상 줄 1개 이상."""
    max_chars = max(1, int(max_chars))
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        if not word:
            continue
        while len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        cand = f"{cur} {word}" if cur else word
        if len(cand) <= max_chars:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def wrap_width(text: str, box_w: float, fs: float) -> list[str]:
    """[23] 폭(px) 기준 줄바꿈 — 띄어쓰기 단위로 채우고, 한 단어가 폭을 넘으면 글자 단위로 자른다.
    글자 수 기준(wrap_text)은 숫자·영문이 섞인 짧은 배지("30% 절감")를 불필요하게 두 줄로 나눴다."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        if not word:
            continue
        while text_width(word, fs) > box_w and len(word) > 1:
            if cur:
                lines.append(cur)
                cur = ""
            k = len(word)
            while k > 1 and text_width(word[:k], fs) > box_w:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        cand = f"{cur} {word}" if cur else word
        if text_width(cand, fs) <= box_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def _fits(lines: Sequence[str], fs: float, box_w: float, box_h: float) -> bool:
    return (
        all(text_width(ln, fs) <= box_w for ln in lines)
        and len(lines) * fs * LINE_GAP <= box_h + fs * 0.4
    )


def fit_text(
    text: str, box_w: float, box_h: float, size: float, *, min_size: float = MIN_FONT
) -> tuple[list[str], float]:
    """상자(w×h)에 들어가도록 줄바꿈 + 크기 축소. (줄 목록, 글자 크기)."""
    fs = float(size)
    lines = [text]
    while True:
        lines = wrap_width(text, box_w, fs)
        if _fits(lines, fs, box_w, box_h) or fs <= min_size:
            return lines, fs
        fs = max(min_size, fs - 1.5)


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


class _Palette:
    def __init__(self, palette: Mapping[str, Any]):
        self.ink = str(palette.get("ink", "#1a1a1a"))
        self.muted = str(palette.get("muted", "#5b5b5b"))
        self.line = str(palette.get("line", "#8c8c8c"))
        self.paper = str(palette.get("paper", "#ffffff"))
        self.accent = str(palette.get("accent", "#b45309"))
        self.warn = str(palette.get("warn", "#9a3412"))
        raw = palette.get("series") or []
        self.series: list[dict[str, str]] = [
            {
                "fill": str(s.get("fill", d["fill"])),
                "stroke": str(s.get("stroke", d["stroke"])),
                "pattern": str(s.get("pattern", d["pattern"]) or "solid"),
                "dash": str(s.get("dash", "") or ""),
            }
            for s, d in zip(raw, _DEFAULT_SERIES, strict=False)
        ] or [dict(d) for d in _DEFAULT_SERIES]

    def s(self, i: int) -> dict[str, str]:
        return self.series[i % len(self.series)]


class _Canvas:
    """SVG 조각 모음. 모든 글자는 escape 를 거친다. 글자는 min_font 밑으로 줄이지 않고, 그래도 넘치면
    overflow 를 센다(root data-overflow)."""

    def __init__(
        self, pal: _Palette, width: int, height: int, title: str, min_font: float = MIN_FONT
    ):
        self.p = pal
        self.w = width
        self.h = height
        self.vh = int(round(BASE_W * height / width))  # viewBox 높이
        self.title = title
        self.min_font = math.ceil(float(min_font) * 10) / 10  # SVG 에 소수 1자리로 적힌다
        self.overflow = 0
        self.parts: list[str] = []
        self.defs: list[str] = []
        self._def_ids: set[str] = set()

    def fs(self, size: float) -> float:
        return max(float(size), self.min_font)

    # defs
    def marker(self, color: str) -> str:
        mid = "arrow-" + color.lstrip("#")
        if mid not in self._def_ids:
            self._def_ids.add(mid)
            self.defs.append(
                f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
                f'markerHeight="5" orient="auto-start-reverse">'
                f'<path d="M0 0 L10 5 L0 10 z" fill="{color}"/></marker>'
            )
        return mid

    def pattern(self, kind: str, stroke: str) -> str | None:
        if kind not in ("dots", "hatch", "cross"):
            return None
        pid = f"pat-{kind}-{stroke.lstrip('#')}"
        if pid not in self._def_ids:
            self._def_ids.add(pid)
            if kind == "dots":
                body = f'<circle cx="5" cy="5" r="1.6" fill="{stroke}"/>'
            elif kind == "hatch":
                body = f'<path d="M0 10 L10 0" stroke="{stroke}" stroke-width="1.4"/>'
            else:
                body = f'<path d="M0 10 L10 0 M0 0 L10 10" stroke="{stroke}" stroke-width="1.2"/>'
            self.defs.append(
                f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="10" height="10">'
                f"{body}</pattern>"
            )
        return pid

    # shapes
    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str,
        stroke: str = "none",
        sw: float = 2,
        rx: float = 0,
        pattern: str | None = None,
        opacity: float = 0.55,
    ) -> None:
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:g}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}"/>'
        )
        if pattern:
            self.parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:g}" '
                f'fill="url(#{pattern})" fill-opacity="{opacity:g}" stroke="none"/>'
            )

    def series_rect(
        self, i: int, x: float, y: float, w: float, h: float, *, rx: float = 0, sw: float = 2
    ) -> None:
        s = self.p.s(i)
        self.rect(
            x,
            y,
            w,
            h,
            fill=s["fill"],
            stroke=s["stroke"],
            sw=sw,
            rx=rx,
            pattern=self.pattern(s["pattern"], s["stroke"]),
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str,
        sw: float = 2,
        dash: str = "",
        arrow: bool = False,
    ) -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        if arrow:
            extra += f' marker-end="url(#{self.marker(stroke)})"'
        self.parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
            f'stroke-width="{sw:g}" stroke-linecap="round"{extra}/>'
        )

    def polyline(self, pts: Sequence[tuple[float, float]], *, stroke: str, sw: float, dash: str):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<polyline points="{d}" fill="none" stroke="{stroke}" stroke-width="{sw:g}" '
            f'stroke-linejoin="round" stroke-linecap="round"{extra}/>'
        )

    def circle(self, cx: float, cy: float, r: float, *, fill: str, stroke: str, sw: float = 2):
        self.parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:g}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw:g}"/>'
        )

    # text
    def text_box(
        self,
        text: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        size: float,
        bold: bool = False,
        color: str | None = None,
        anchor: str = "middle",
        valign: str = "middle",
        pad: float = 10,
    ) -> float:
        """상자(x,y,w,h) 안에 글자를 넣는다(줄바꿈·축소, min_font 아래로는 줄이지 않는다).
        반환: 쓴 높이(px). 하한 크기로도 넘치면 overflow 를 센다."""
        if not text:
            return 0.0
        size = self.fs(size)
        inner_w = max(10.0, w - 2 * pad)
        inner_h = max(size, h - 2 * pad)
        lines, fs = fit_text(text, inner_w, inner_h, size, min_size=self.min_font)
        if not _fits(lines, fs, inner_w, inner_h):
            self.overflow += 1
        lh = fs * LINE_GAP
        block_h = len(lines) * lh
        if valign == "top":
            first = y + pad + fs
        elif valign == "bottom":
            first = y + h - pad - block_h + fs
        else:
            first = y + h / 2 - block_h / 2 + fs * 0.95
        if anchor == "start":
            tx = x + pad
        elif anchor == "end":
            tx = x + w - pad
        else:
            tx = x + w / 2
        weight = ' font-weight="bold"' if bold else ""
        label = f' aria-label="{_attr(text)}"' if len(lines) > 1 else ""
        fill = color or self.p.ink
        head = (
            f'<text x="{tx:.1f}" y="{first:.1f}" font-family="{FONT}" font-size="{fs:.1f}"'
            f'{weight} fill="{fill}" text-anchor="{anchor}"{label}>'
        )
        if len(lines) == 1:
            self.parts.append(head + escape(lines[0]) + "</text>")
        else:
            spans = "".join(
                f'<tspan x="{tx:.1f}" dy="{(0 if i == 0 else lh):.1f}">{escape(ln)}</tspan>'
                for i, ln in enumerate(lines)
            )
            self.parts.append(head + spans + "</text>")
        return block_h

    def label(
        self,
        text: str,
        x: float,
        y: float,
        *,
        size: float,
        anchor: str = "middle",
        bold: bool = False,
        color: str | None = None,
        max_w: float | None = None,
    ) -> None:
        """한 줄 글자(기준선 y). max_w 가 있으면 넘치지 않게 축소만 한다(줄바꿈 없음, 하한까지)."""
        fs = self.fs(size)
        if max_w is not None:
            while text_width(text, fs) > max_w and fs > self.min_font:
                fs = max(self.min_font, fs - 1.0)
            if text_width(text, fs) > max_w + 1:
                self.overflow += 1
        weight = ' font-weight="bold"' if bold else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs:.1f}"{weight} '
            f'fill="{color or self.p.ink}" text-anchor="{anchor}">{escape(text)}</text>'
        )

    def arrow_between(self, x1: float, x2: float, y: float, *, color: str | None = None) -> None:
        self.line(x1, y, x2, y, stroke=color or self.p.line, sw=6, arrow=True)

    def render(self) -> str:
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {BASE_W} {self.vh}" font-family="{FONT}" '
            f'data-overflow="{self.overflow}" '
            f'role="img" aria-label="{_attr(self.title)}">'
            f"<title>{escape(self.title)}</title>{defs}"
            f'<rect x="0" y="0" width="{BASE_W}" height="{self.vh}" fill="{self.p.paper}"/>'
            + "".join(self.parts)
            + "</svg>"
        )


# ── 진입 ───────────────────────────────────────────────────
def render_svg(
    spec: BaseModel,
    *,
    palette: Mapping[str, Any],
    aspect: str = "16:9",
    width_px: int = BASE_W,
    caption: str = "",
    min_font: float = MIN_FONT,
    arrange: str | None = None,
) -> str:
    """종류별 SVG 밑그림. caption 은 그림 안에 그리지 않고 `<title>` 에만 둔다.
    min_font: 글자 하한(viewBox 단위) — 본문 폭에서 min_text_pt 가 되는 값. arrange: 분석 기법 배치."""
    kind = str(getattr(spec, "kind", ""))
    w, h = figure_size(aspect, width_px)
    title = caption or getattr(spec, "title", None) or KIND_LABEL.get(kind, "그림")
    cv = _Canvas(_Palette(palette), w, h, title, min_font=min_font)
    if isinstance(spec, ConceptSpec):
        _concept(cv, spec)
    elif isinstance(spec, ProcessSpec):
        _process(cv, spec)
    elif isinstance(spec, ScheduleSpec):
        _schedule(cv, spec)
    elif isinstance(spec, StatChartSpec):
        _stat_chart(cv, spec)
    elif isinstance(spec, ComparisonSpec):
        _comparison(cv, spec)
    elif isinstance(spec, RoadmapSpec):
        _roadmap(cv, spec)
    elif isinstance(spec, AsIsToBeSpec):
        _as_is_to_be(cv, spec)
    elif isinstance(spec, TechniqueSpec):
        _technique(cv, spec, technique_arrangement(spec, arrange))
    else:
        raise ValueError(f"지원하지 않는 그림 종류: {kind!r}")
    return cv.render()


# ── concept: 상자 4개 가로 한 줄 → ───────────────────────────
def _concept(cv: _Canvas, spec: ConceptSpec) -> None:
    m, gap = 24.0, 56.0
    n = len(spec.boxes)
    box_w = (BASE_W - 2 * m - gap * (n - 1)) / n
    box_h = cv.vh - 2 * m
    y = m
    head_h = min(box_h * 0.24, 110.0)
    for i, b in enumerate(spec.boxes):
        x = m + i * (box_w + gap)
        last = i == n - 1
        s = cv.p.s(0)
        stroke = cv.p.accent if last else s["stroke"]
        cv.rect(x, y, box_w, box_h, fill=cv.p.paper, stroke=stroke, sw=3, rx=14)
        cv.rect(x, y, box_w, head_h, fill=s["fill"], stroke="none", rx=14)
        cv.rect(x, y + head_h - 14, box_w, 14, fill=s["fill"])  # 둥근 모서리 아래쪽 채움
        cv.line(x, y + head_h, x + box_w, y + head_h, stroke=stroke, sw=3)
        cv.text_box(b.label, x, y, box_w, head_h, size=F_HEAD, bold=True, pad=10)
        if b.lines:
            body_y = y + head_h + 10
            body_h = box_h - head_h - 20
            line_h = body_h / len(b.lines)
            for j, ln in enumerate(b.lines):
                cv.text_box(
                    "○ " + ln,
                    x,
                    body_y + j * line_h,
                    box_w,
                    line_h,
                    size=F_BODY,
                    anchor="start",
                    valign="top",
                    pad=12,
                )
        if not last:
            cv.arrow_between(x + box_w + 6, x + box_w + gap - 6, y + box_h / 2)


# ── process: 단계 상자 가로 한 줄 + 산출물 ─────────────────────────
def _process(cv: _Canvas, spec: ProcessSpec) -> None:
    m = 24.0
    n = len(spec.stages)
    gap = 40.0 if n >= 5 else 56.0
    box_w = (BASE_W - 2 * m - gap * (n - 1)) / n
    box_y = m
    box_h = max(cv.vh * 0.26, 140.0)
    out_y = box_y + box_h + 18
    out_h = cv.vh - out_y - m
    for i, st in enumerate(spec.stages):
        x = m + i * (box_w + gap)
        cv.series_rect(0 if i < n - 1 else 1, x, box_y, box_w, box_h, rx=12, sw=3)
        cv.text_box(st.name, x, box_y, box_w, box_h, size=F_HEAD, bold=True, pad=10)
        cv.line(x + box_w / 2, box_y + box_h, x + box_w / 2, out_y, stroke=cv.p.line, sw=2)
        if st.outputs:
            cv.rect(x, out_y, box_w, out_h, fill=cv.p.paper, stroke=cv.p.line, sw=1.5, rx=8)
            head = 52.0
            cv.label(
                "산출물",
                x + 12,
                out_y + 40,
                size=F_SMALL,
                anchor="start",
                color=cv.p.muted,
                bold=True,
            )
            cv.line(x + 8, out_y + head, x + box_w - 8, out_y + head, stroke=cv.p.line, sw=1)
            slot_h = (out_h - head - 6) / len(st.outputs)
            for j, o in enumerate(st.outputs):
                cv.text_box(
                    "· " + o,
                    x,
                    out_y + head + j * slot_h,
                    box_w,
                    slot_h,
                    size=F_BODY,
                    anchor="start",
                    valign="top",
                    pad=10,
                )
        if i < n - 1:
            cv.arrow_between(x + box_w + 4, x + box_w + gap - 4, box_y + box_h / 2)


# ── schedule: 가로로 긴 간트 ─────────────────────────────────────
def _schedule(cv: _Canvas, spec: ScheduleSpec) -> None:
    m_l, m_r, m_b = 24.0, 24.0, 20.0
    fs_name = F_BODY
    fs_tick = F_SMALL
    head = fs_tick * 1.9  # 위쪽 월 눈금 줄
    longest = max((text_width(s.name, fs_name) for s in spec.stages), default=200.0)
    name_w = min(max(longest + 30, 300.0), 560.0)
    total = max(1, spec.total_months)
    x0 = m_l + name_w
    unit_w = text_width("개월", fs_tick) + 10
    x1 = BASE_W - m_r - unit_w
    chart_w = x1 - x0
    y0 = m_b + head
    y1 = cv.vh - m_b
    n = len(spec.stages)
    row_h = (y1 - y0) / n
    # 눈금 간격 — 숫자 글자가 겹치지 않게 (1·2·3·6·12개월 중 가장 촘촘한 것)
    slot = chart_w / total
    label_w = text_width(str(total), fs_tick) + 12
    step = next((k for k in (1, 2, 3, 6, 12) if slot * k >= label_w), 12)
    cv.label("개월", BASE_W - m_r, y0 - 18, size=fs_tick, anchor="end", color=cv.p.muted)
    for mth in range(0, total + 1):
        x = x0 + chart_w * mth / total
        major = mth % step == 0
        if mth > 0 and (major or step == 1):
            cv.line(x, y0, x, y1, stroke=cv.p.line, sw=1.2, dash="3 3")
        if mth > 0 and major:
            cv.label(str(mth), x - slot / 2, y0 - 18, size=fs_tick, color=cv.p.muted)
    cv.rect(x0, y0, chart_w, y1 - y0, fill="none", stroke=cv.p.line, sw=1.5)
    for i, st in enumerate(spec.stages):
        ry = y0 + i * row_h
        if i > 0:
            cv.line(m_l, ry, x1, ry, stroke=cv.p.line, sw=1)
        cv.text_box(st.name, m_l, ry, name_w - 8, row_h, size=fs_name, anchor="start", pad=6)
        bx = x0 + chart_w * (st.start_month - 1) / total
        bw = max(4.0, chart_w * (st.end_month - st.start_month + 1) / total)
        bh = min(row_h * 0.72, 70.0)
        by = ry + (row_h - bh) / 2
        cv.series_rect(i, bx, by, bw, bh, rx=6, sw=2)
        span = f"{st.start_month}~{st.end_month}개월"
        sw_txt = text_width(span, fs_tick)
        base = by + bh / 2 + fs_tick * 0.36
        if bw >= sw_txt + 16 and i % len(cv.p.series) < 2:  # 막대 안 (옅은 채움일 때)
            cv.label(span, bx + bw / 2, base, size=fs_tick, bold=True)
        elif bx + bw + sw_txt + 10 <= x1:
            cv.label(span, bx + bw + 8, base, size=fs_tick, anchor="start")
        else:
            cv.label(span, bx - 8, base, size=fs_tick, anchor="end", max_w=bx - x0 + name_w)


# ── stat_chart: 막대·꺾은선 ──────────────────────────────────
def _nice_max(v: float) -> float:
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for k in (1, 2, 2.5, 5, 10):
        if v <= k * mag:
            return k * mag
    return 10 * mag


def _stat_chart(cv: _Canvas, spec: StatChartSpec) -> None:
    """[23] 출처는 그림 밖 HWPX 출처 줄(12pt)이 맡는다 — 그림 안에 그리지 않는다."""
    m_l, m_r, m_t, m_b = 130.0, 30.0, 20.0, 20.0
    cats = spec.categories
    n_cat = len(cats)
    n_ser = len(spec.series)
    title_h = 64.0
    cv.text_box(
        spec.title, 24, m_t, BASE_W - 48 - 360, title_h, size=F_TITLE, bold=True, anchor="start"
    )
    # 범례 — 제목 오른쪽 또는 아래 줄
    ly = m_t + title_h + 8
    lx = m_l
    for i, s in enumerate(spec.series):
        cv.series_rect(i, lx, ly, 40, 26, sw=1.5)
        if spec.chart == "line":
            dash = cv.p.s(i)["dash"]
            cv.line(lx, ly + 13, lx + 40, ly + 13, stroke=cv.p.s(i)["stroke"], sw=4, dash=dash)
        cv.label(s.name, lx + 50, ly + 24, size=F_SMALL, anchor="start")
        lx += 50 + text_width(s.name, cv.fs(F_SMALL)) + 40
    if spec.unit:
        cv.label(
            f"(단위: {spec.unit})",
            BASE_W - m_r,
            ly + 24,
            size=F_SMALL,
            anchor="end",
            color=cv.p.muted,
        )
    # 축 영역
    y_top = ly + 40 + F_SMALL * 1.4
    y_bot = cv.vh - m_b - F_BODY * 1.5
    x_left = m_l
    x_right = BASE_W - m_r
    all_vals = [v for s in spec.series for v in s.values]
    vmax = _nice_max(max(all_vals) * 1.12 if all_vals else 1.0)
    vmin = min(0.0, min(all_vals)) if all_vals else 0.0
    if vmin < 0:
        vmin = -_nice_max(-vmin)
    span = vmax - vmin or 1.0

    def sy(v: float) -> float:
        return y_bot - (v - vmin) / span * (y_bot - y_top)

    ticks = 4
    for t in range(ticks + 1):
        v = vmin + span * t / ticks
        y = sy(v)
        cv.line(x_left, y, x_right, y, stroke=cv.p.line, sw=0.8, dash="4 4")
        cv.label(
            f"{v:g}",
            x_left - 12,
            y + 11,
            size=F_SMALL,
            anchor="end",
            color=cv.p.muted,
            max_w=m_l - 16,
        )
    cv.line(x_left, y_top, x_left, y_bot, stroke=cv.p.ink, sw=2)
    cv.line(x_left, sy(0.0), x_right, sy(0.0), stroke=cv.p.ink, sw=2)
    slot_w = (x_right - x_left) / n_cat
    use_vt = len(spec.value_texts) == n_cat * n_ser

    def vtext(si: int, ci: int, v: float) -> str:
        if use_vt:
            return spec.value_texts[si * n_cat + ci]
        return f"{v:g}{spec.unit}"

    if spec.chart == "bar":
        group_w = slot_w * 0.8
        bar_w = group_w / n_ser
        for ci in range(n_cat):
            gx = x_left + ci * slot_w + (slot_w - group_w) / 2
            for si, s in enumerate(spec.series):
                v = s.values[ci]
                bx = gx + si * bar_w
                top, base = sy(max(v, 0.0)), sy(min(v, 0.0))
                cv.series_rect(si, bx + 2, top, bar_w - 4, max(1.0, base - top), sw=1.5)
                cv.label(
                    vtext(si, ci, v),
                    bx + bar_w / 2,
                    top - 8 if v >= 0 else base + F_SMALL,
                    size=F_SMALL,
                    max_w=bar_w + 6,
                )
    else:
        for si, s in enumerate(spec.series):
            st = cv.p.s(si)
            pts = [(x_left + (ci + 0.5) * slot_w, sy(v)) for ci, v in enumerate(s.values)]
            cv.polyline(pts, stroke=st["stroke"], sw=5, dash=st["dash"])
            for ci, (px, py) in enumerate(pts):
                cv.circle(px, py, 8, fill=st["fill"], stroke=st["stroke"], sw=2)
                cv.label(
                    vtext(si, ci, s.values[ci]),
                    px,
                    py - 16 - si * 2,
                    size=F_SMALL,
                    max_w=slot_w,
                )
    for ci, c in enumerate(cats):
        cv.text_box(
            c,
            x_left + ci * slot_w,
            y_bot + 4,
            slot_w,
            F_BODY * 1.5,
            size=F_BODY,
            valign="top",
            pad=2,
        )


# ── comparison: 표 ─────────────────────────────────────────
def _comparison(cv: _Canvas, spec: ComparisonSpec) -> None:
    m = 20.0
    cols = [*spec.projects, spec.proposal]
    n_cols = len(cols)
    aspect_w = 230.0
    col_w = (BASE_W - 2 * m - aspect_w) / n_cols
    head_h = 150.0
    body_h = cv.vh - 2 * m - head_h
    row_h = body_h / len(spec.aspects)
    x_cols = [m + aspect_w + i * col_w for i in range(n_cols)]
    y0 = m
    # 머리글
    cv.rect(m, y0, aspect_w, head_h, fill=cv.p.s(1)["fill"], stroke=cv.p.ink, sw=1.5)
    cv.text_box("구분", m, y0, aspect_w, head_h, size=F_HEAD, bold=True)
    for i, c in enumerate(cols):
        is_prop = i == n_cols - 1
        cv.rect(x_cols[i], y0, col_w, head_h, fill=cv.p.s(1)["fill"], stroke=cv.p.ink, sw=1.5)
        tag = "제안 과제" if is_prop else "기존 과제"
        cv.label(tag, x_cols[i] + col_w / 2, y0 + 40, size=F_SMALL, color=cv.p.muted)
        cv.text_box(c.title, x_cols[i], y0 + 48, col_w, head_h - 52, size=F_BODY, bold=True, pad=8)
    # 본문
    for r, a in enumerate(spec.aspects):
        ry = y0 + head_h + r * row_h
        cv.rect(m, ry, aspect_w, row_h, fill=cv.p.s(0)["fill"], stroke=cv.p.ink, sw=1.5)
        cv.text_box(a, m, ry, aspect_w, row_h, size=F_BODY, bold=True)
        for i, c in enumerate(cols):
            val = (c.cells.get(a) or "").strip()
            cv.rect(x_cols[i], ry, col_w, row_h, fill=cv.p.paper, stroke=cv.p.ink, sw=1.5)
            if val:
                cv.text_box(val, x_cols[i], ry, col_w, row_h, size=F_BODY, anchor="start", pad=12)
            else:
                cv.text_box(NO_INFO, x_cols[i], ry, col_w, row_h, size=F_BODY, color=cv.p.muted)
    # 제안 과제 열 강조 테두리
    px = x_cols[-1]
    cv.rect(px, y0, col_w, head_h + body_h, fill="none", stroke=cv.p.accent, sw=5)


# ── roadmap: 성과지표 + 활용 단계 (가로로 긴 두 줄) ───────────────────
def _roadmap(cv: _Canvas, spec: RoadmapSpec) -> None:
    m = 20.0
    label_w = 120.0
    gap = 28.0
    top_y = m
    usable = cv.vh - 2 * m - 50
    top_h = usable * 0.5
    n_m = len(spec.metrics)
    mw = (BASE_W - m - label_w - m - gap * (n_m - 1)) / n_m
    cv.text_box(
        "성과지표", m, top_y, label_w, top_h, size=F_HEAD, bold=True, color=cv.p.muted, pad=4
    )
    for i, mt in enumerate(spec.metrics):
        x = m + label_w + i * (mw + gap)
        cv.series_rect(0, x, top_y, mw, top_h, rx=12, sw=2.5)
        name_h = top_h * 0.5
        cv.text_box(mt.name, x, top_y, mw, name_h, size=F_BODY, bold=True, pad=10)
        cv.line(x + 14, top_y + name_h, x + mw - 14, top_y + name_h, stroke=cv.p.line, sw=1.5)
        cv.text_box(
            mt.target, x, top_y + name_h, mw, top_h - name_h, size=F_BODY, pad=8, color=cv.p.accent
        )
    # 아래: 활용 단계
    bot_y = top_y + top_h + 50
    bot_h = cv.vh - bot_y - m
    n_s = len(spec.stages)
    sgap = 56.0
    sw_ = (BASE_W - m - label_w - m - sgap * (n_s - 1)) / n_s
    cv.text_box(
        "활용 단계", m, bot_y, label_w, bot_h, size=F_HEAD, bold=True, color=cv.p.muted, pad=4
    )
    for i, st in enumerate(spec.stages):
        x = m + label_w + i * (sw_ + sgap)
        last = i == n_s - 1
        s = cv.p.s(1)
        cv.rect(
            x,
            bot_y,
            sw_,
            bot_h,
            fill=s["fill"],
            stroke=cv.p.accent if last else s["stroke"],
            sw=4 if last else 2.5,
            rx=12,
            pattern=cv.pattern(s["pattern"], s["stroke"]) if last else None,
            opacity=0.35,
        )
        name_h = bot_h * 0.45 if st.desc else bot_h
        cv.text_box(st.name, x, bot_y, sw_, name_h, size=F_BODY, bold=True, pad=8)
        if st.desc:
            cv.text_box(
                st.desc,
                x,
                bot_y + name_h - 6,
                sw_,
                bot_h - name_h,
                size=F_BODY,
                valign="top",
                pad=8,
            )
        if not last:
            cv.arrow_between(x + sw_ + 4, x + sw_ + sgap - 4, bot_y + bot_h / 2)


# ── v2 [3] as_is_to_be: 현재 | 화살표(핵심 해결 방안) | 연구 후 — 좌우 두 단 ─────────────
_AS_IS = {"fill": "#eceff3", "head": "#d5d9e0", "stroke": "#c2410c", "ink": "#3f3f46"}
_TO_BE = {"fill": "#eef5ff", "head": "#cfe3fb", "stroke": "#15803d", "ink": "#0b2d4d"}
_ARROW = "#1e3a8a"


def _side_panel(
    cv: _Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    head: str,
    items: Sequence[Any],
    colors: Mapping[str, str],
    *,
    dashed: bool,
    pattern: str,
) -> None:
    """한쪽 단 — 머리글 띠(무늬) + 칸마다 이름표(tag, 첫 줄)와 글자(아래 줄).
    흑백 인쇄: 왼쪽 점선 테두리·빗금, 오른쪽 굵은 실선·점."""
    head_h = 76.0
    cv.rect(x, y, w, h, fill=colors["fill"], stroke="none", rx=16)
    cv.rect(
        x,
        y,
        w,
        head_h,
        fill=colors["head"],
        stroke="none",
        rx=16,
        pattern=cv.pattern(pattern, colors["stroke"]),
        opacity=0.35,
    )
    cv.text_box(head, x, y, w, head_h, size=F_TITLE, bold=True, color=colors["ink"], pad=6)
    border = (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="16" fill="none" '
        f'stroke="{colors["stroke"]}" stroke-width="{4 if dashed else 6}"'
        + (' stroke-dasharray="14 8"' if dashed else "")
        + "/>"
    )
    cv.parts.append(border)
    n = max(1, len(items))
    gap = 12.0
    top = y + head_h + 12
    row_h = (h - head_h - 24 - gap * (n - 1)) / n
    tag_h = F_SMALL * 1.35
    for i, it in enumerate(items):
        ry = top + i * (row_h + gap)
        cv.rect(x + 14, ry, w - 28, row_h, fill=cv.p.paper, stroke=colors["stroke"], sw=2, rx=10)
        tag_w = text_width(it.tag, cv.fs(F_SMALL)) + 28
        cv.rect(x + 14, ry, tag_w, tag_h, fill=colors["head"], stroke="none", rx=10)
        cv.text_box(
            it.tag, x + 14, ry, tag_w, tag_h, size=F_SMALL, bold=True, color=colors["ink"], pad=2
        )
        cv.text_box(
            it.text,
            x + 14,
            ry + tag_h,
            w - 28,
            row_h - tag_h,
            size=F_BODY,
            anchor="start",
            pad=12,
        )


def _as_is_to_be(cv: _Canvas, spec: Any) -> None:
    from rra.domain.rules.figures import AS_IS_HEAD, TO_BE_HEAD

    m = 16.0
    mid_w = 250.0
    panel_w = (BASE_W - 2 * m - mid_w) / 2
    y = m
    h = cv.vh - 2 * m
    _side_panel(cv, m, y, panel_w, h, AS_IS_HEAD, spec.as_is, _AS_IS, dashed=True, pattern="hatch")
    rx = BASE_W - m - panel_w
    _side_panel(cv, rx, y, panel_w, h, TO_BE_HEAD, spec.to_be, _TO_BE, dashed=False, pattern="dots")
    # 가운데 화살표 — 몸통 안에 핵심 해결 방안
    ax0 = m + panel_w + 8
    ax1 = rx - 8
    cy = y + h / 2
    body_h = h * 0.62
    head_w = 46.0
    pts = [
        (ax0, cy - body_h / 2),
        (ax1 - head_w, cy - body_h / 2),
        (ax1 - head_w, cy - body_h / 2 - 22),
        (ax1, cy),
        (ax1 - head_w, cy + body_h / 2 + 22),
        (ax1 - head_w, cy + body_h / 2),
        (ax0, cy + body_h / 2),
    ]
    d = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    cv.parts.append(f'<polygon points="{d}" fill="{_ARROW}" stroke="none"/>')
    cv.text_box(
        spec.solution,
        ax0,
        cy - body_h / 2,
        ax1 - head_w - ax0 + 16,
        body_h,
        size=F_BODY,
        bold=True,
        color="#ffffff",
        pad=8,
    )


# ── v2 [11] technique: 묶음 카드(가로 배치) / 평가 표 ───────────────────────────────
_LEVEL_DOTS = {"상": 3, "중": 2, "하": 1}


def _rating_chip(cv: _Canvas, x: float, cy: float, rating: str, color: str) -> float:
    """강도 표시 — 동그라미 안에 상·중·하(채움 진하기 = 강도). 반환: 쓴 폭."""
    n = _LEVEL_DOTS.get(rating, 0)
    r = cv.fs(F_SMALL) * 0.72
    fill = color if n == 3 else (cv.p.s(1)["fill"] if n == 2 else cv.p.paper)
    ink = "#ffffff" if n == 3 else color
    cv.circle(x + r, cy, r, fill=fill, stroke=color, sw=2.5)
    cv.label(rating, x + r, cy + cv.fs(F_SMALL) * 0.36, size=F_SMALL, bold=True, color=ink)
    return 2 * r + 8


def _technique(cv: _Canvas, spec: Any, arrange: str) -> None:
    m = 18.0
    title_h = 60.0
    note_h = F_SMALL * 1.4
    cv.text_box(
        spec.title, m, m - 4, BASE_W - 2 * m, title_h, size=F_TITLE, bold=True, anchor="start"
    )
    cv.label(spec.note, BASE_W - m, cv.vh - m, size=F_SMALL, anchor="end", color=cv.p.muted)
    top = m + title_h + 6
    bottom = cv.vh - m - note_h
    if spec.rows:
        _technique_matrix(cv, spec, m, top, BASE_W - 2 * m, bottom - top)
    else:
        _technique_groups(cv, spec, m, top, BASE_W - 2 * m, bottom - top, arrange)


def _technique_groups(
    cv: _Canvas, spec: Any, x0: float, y0: float, w: float, h: float, arrange: str
) -> None:
    from rra.domain.models.figure import NEED_CALC

    n = len(spec.groups)
    if arrange == "grid":
        cols = math.ceil(n / 2)
    else:
        cols = max(1, n)  # row·split·flow — 한 줄
    rows = math.ceil(n / cols)
    gap = 54.0 if arrange == "flow" else (40.0 if arrange == "split" else 16.0)
    cw = (w - gap * (cols - 1)) / cols
    ch = (h - 16 * (rows - 1)) / rows
    head_h = 62.0
    for i, g in enumerate(spec.groups):
        r, c = divmod(i, cols)
        x = x0 + c * (cw + gap)
        y = y0 + r * (ch + 16)
        s = cv.p.s(i)
        cv.rect(x, y, cw, ch, fill=cv.p.paper, stroke=s["stroke"], sw=3, rx=12)
        cv.rect(
            x,
            y,
            cw,
            head_h,
            fill=s["fill"],
            stroke="none",
            rx=12,
            pattern=cv.pattern(s["pattern"], s["stroke"]),
            opacity=0.3,
        )
        cv.text_box(g.name, x, y, cw, head_h, size=F_HEAD, bold=True, anchor="start", pad=14)
        if arrange == "flow" and c < cols - 1:
            cv.arrow_between(x + cw + 4, x + cw + gap - 4, y + ch / 2, color=s["stroke"])
        k = max(1, len(g.items))
        avail = ch - head_h - 12
        slot = avail / k
        top = y + head_h + 6
        for j, it in enumerate(g.items):
            iy = top + j * slot
            lead = 0.0
            badge_w = 0.0
            if it.rating:
                lead = _rating_chip(cv, x + 12, iy + cv.fs(F_BODY) * 0.9, it.rating, s["stroke"])
            elif it.amount:
                muted = it.amount == NEED_CALC
                badge_w = min(cw * 0.42, text_width(it.amount, cv.fs(F_SMALL)) + 30)
                bh = cv.fs(F_SMALL) * 1.5
                cv.rect(
                    x + cw - badge_w - 10,
                    iy + slot / 2 - bh / 2,
                    badge_w,
                    bh,
                    fill=cv.p.paper if muted else s["fill"],
                    stroke=s["stroke"],
                    sw=2,
                    rx=bh / 2,
                )
                cv.text_box(
                    it.amount,
                    x + cw - badge_w - 10,
                    iy + slot / 2 - bh / 2,
                    badge_w,
                    bh,
                    size=F_SMALL,
                    bold=not muted,
                    color=cv.p.muted if muted else cv.p.ink,
                    pad=4,
                )
            cv.text_box(
                it.text,
                x + 6 + lead,
                iy,
                cw - 12 - lead - badge_w - (14 if badge_w else 0),
                slot,
                size=F_BODY,
                anchor="start",
                valign="top" if it.rating else "middle",
                pad=8,
            )


def _technique_matrix(cv: _Canvas, spec: Any, x0: float, y0: float, w: float, h: float) -> None:
    name_w = min(480.0, w * 0.32)
    n = len(spec.columns)
    col_w = (w - name_w) / max(1, n)
    head_h = 96.0
    row_h = (h - head_h) / max(1, len(spec.rows))
    shade = {"상": 2, "+": 2, "중": 1, "0": 1, "하": 0, "−": 0}
    head = cv.p.s(1)
    cv.rect(x0, y0, name_w, head_h, fill=head["fill"], stroke=cv.p.ink, sw=1.5)
    cv.text_box("평가 기준", x0, y0, name_w, head_h, size=F_HEAD, bold=True)
    for j, col in enumerate(spec.columns):
        cx = x0 + name_w + j * col_w
        cv.rect(cx, y0, col_w, head_h, fill=head["fill"], stroke=cv.p.ink, sw=1.5)
        cv.text_box(col, cx, y0, col_w, head_h, size=F_BODY, bold=True, pad=6)
    for i, r in enumerate(spec.rows):
        ry = y0 + head_h + i * row_h
        cv.rect(x0, ry, name_w, row_h, fill=cv.p.s(0)["fill"], stroke=cv.p.ink, sw=1.5)
        cv.text_box(r.name, x0, ry, name_w, row_h, size=F_BODY, anchor="start", pad=12)
        for j, val in enumerate(r.cells):
            cx = x0 + name_w + j * col_w
            level = shade.get(val, 1)
            s = cv.p.s(1 if level == 2 else 0)  # 글자가 읽히게 옅은 두 단계 + 무늬
            cv.rect(
                cx,
                ry,
                col_w,
                row_h,
                fill=s["fill"] if level else cv.p.paper,
                stroke=cv.p.ink,
                sw=1.5,
                pattern=cv.pattern(s["pattern"], s["stroke"]) if level == 2 else None,
                opacity=0.25,
            )
            cv.text_box(val, cx, ry, col_w, row_h, size=F_TITLE, bold=True)
