"""[23] 그림 모양 — 가로 비율·본문 폭 맞춤·글자 크기 규칙 (순수 함수, 2026-10-28 밤, ADR 0041).

- 모든 그림은 가로로 넓게: As-Is/To-Be·분석 기법·개념도·체계도·그래프·비교표는 16:9 또는 21:9, 추진
일정표·
  로드맵처럼 옆으로 긴 내용은 21:9 또는 4:1 (`WIDE_ASPECTS`).
- HWPX 그림 폭 = 양식 본문 안쪽 폭(쪽 폭 − 좌우 여백 − 단락 오른쪽 여백, 표 칸이면 칸 폭 − 칸
  여백), 높이는
  비율로. 높이 상한은 쪽 높이의 1/3 — 넘으면 더 넓은 비율로 다시 그린다(`wider`).
- 글자 크기: 본문 폭으로 넣었을 때 그림 안 글자 ≥ `min_text_pt`(9pt). 밑그림은 SVG 글자
  크기(viewBox 1600 기준)
  × 폭 비로 계산(`svg_metrics`·`font_pt`), Nano Banana 그림은 OCR 글자 상자 높이로
  어림(`estimate_ocr_pt`).
  작으면 글자를 줄여(`shorten_spec` — 띄어쓰기 자리에서 자르고 항목 수를 줄인다) 다시 그린다.
- 4:1 은 Nano Banana imageConfig.aspectRatio 가 받지 않는다 — 생성은 21:9(`api_aspect`)로 하고,
  밑그림을 21:9
  캔버스 가운데 4:1 띠로 넣어 보낸 뒤 결과의 흰 여백을 잘라 4:1 로 맞춘다(어댑터 `fit_aspect`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from rra.domain.models.figure import (
    AsIsToBeSpec,
    ComparisonSpec,
    ConceptSpec,
    FigureFit,
    ProcessSpec,
    RoadmapSpec,
    ScheduleSpec,
    StatChartSpec,
    TechniqueSpec,
)

VIEWBOX_W = 1600.0  # 밑그림 좌표계 폭 (adapters/figures/render.BASE_W)
MM_PER_INCH = 25.4
PT_PER_MM = 72.0 / MM_PER_INCH
HWPUNIT_PER_MM = 7200.0 / MM_PER_INCH  # 1/7200 인치
MIN_TEXT_PT = 9.0
PT_TOLERANCE = 0.05  # 반올림 차이 (33.0 단위 = 8.99pt)
HEIGHT_SHARE = 1.0 / 3.0  # 그림 높이 상한 = 쪽 높이 × 1/3
# 실물 양식(별지 제2호서식) 본문: A4 210×297mm, 좌우 여백 25mm, 본문 단락 오른쪽 여백 1750 HWPUNIT
# → 153.8mm
DEFAULT_BODY_WIDTH_MM = 43606 / HWPUNIT_PER_MM
DEFAULT_PAGE_HEIGHT_MM = 84189 / HWPUNIT_PER_MM

# 종류별 쓸 수 있는 비율 (좁은 것 → 넓은 것)
_WIDE = ("16:9", "21:9")
_LONG = ("21:9", "4:1")
WIDE_ASPECTS: dict[str, tuple[str, ...]] = {
    "as_is_to_be": _WIDE,
    "technique": _WIDE,
    "concept": _WIDE,
    "process": _WIDE,
    "stat_chart": _WIDE,
    "comparison": _WIDE,
    "schedule": _LONG,
    "roadmap": _LONG,
}
# Nano Banana(gemini-3-pro-image) imageConfig.aspectRatio 가 받는 값
API_ASPECTS: frozenset[str] = frozenset(
    {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
)
# 분석 기법 그림 배치 (techniques.yaml arrange) — 모두 가로로 놓는다
ARRANGEMENTS: tuple[str, ...] = ("row", "split", "flow", "grid", "table")
# 글자 줄이기 단계 — (상자 글자 상한, 묶음당 항목 상한, 표 행 상한, 일정 단계 이름 상한)
SHORTEN_LEVELS: dict[int, tuple[int, int, int, int]] = {
    1: (22, 3, 5, 14),
    2: (16, 2, 4, 10),
}
MAX_SHORTEN = max(SHORTEN_LEVELS)

_FONT_SIZE = re.compile(r'font-size="([0-9]+(?:\.[0-9]+)?)"')
_OVERFLOW = re.compile(r'data-overflow="([0-9]+)"')
_SPACES = re.compile(r"\s+")


# ── 비율 ─────────────────────────────────────────────────
def ratio_value(aspect: str) -> float:
    """'21:9' → 2.333. 모르는 값은 16:9."""
    try:
        a, b = (float(x) for x in str(aspect).split(":", 1))
        if a > 0 and b > 0:
            return a / b
    except (ValueError, AttributeError):
        pass
    return 16.0 / 9.0


def allowed_aspects(kind: str) -> tuple[str, ...]:
    return WIDE_ASPECTS.get(kind, _WIDE)


def api_aspect(aspect: str) -> str:
    """생성 API 에 보낼 비율 — 받지 않는 비율(4:1)은 받는 값 중 가장 넓은 21:9."""
    return aspect if aspect in API_ASPECTS else "21:9"


def wider(kind: str, aspect: str) -> str | None:
    """같은 종류에서 지금보다 넓은 비율 중 가장 가까운 것. 없으면 None."""
    now = ratio_value(aspect)
    for cand in allowed_aspects(kind):
        if ratio_value(cand) > now + 1e-6:
            return cand
    return None


def narrower(kind: str, aspect: str) -> str | None:
    """같은 종류에서 지금보다 덜 넓은(세로가 긴) 허용 비율 중 가장 가까운 것. 없으면 None."""
    now = ratio_value(aspect)
    below = [a for a in allowed_aspects(kind) if ratio_value(a) < now - 1e-6]
    return below[-1] if below else None


def wide_aspect(kind: str, aspect: str) -> str:
    """예전 비율(4:3·3:2 등)을 그 종류의 가로 비율로 — 좁으면 가장 좁은 허용 비율로 올린다."""
    allowed = allowed_aspects(kind)
    if aspect in allowed:
        return aspect
    now = ratio_value(aspect)
    above = [a for a in allowed if ratio_value(a) >= now - 1e-6]
    return above[0] if above else allowed[-1]


def _longest(texts: Iterable[str]) -> int:
    return max((len(t) for t in texts if t), default=0)


def choose_aspect(spec: BaseModel, *, arrange: str | None = None) -> str:
    """내용 양으로 가로 비율을 고른다 (빈 공간이 크지 않게, 그러나 늘 가로로 넓게)."""
    if isinstance(spec, AsIsToBeSpec):
        n = max(len(spec.as_is), len(spec.to_be))
        longest = _longest([*(i.text for i in spec.as_is), *(i.text for i in spec.to_be)])
        return "21:9" if n <= 3 and longest <= 20 else "16:9"
    if isinstance(spec, TechniqueSpec):
        if spec.rows:
            return "21:9" if len(spec.rows) <= 3 else "16:9"
        n = len(spec.groups)
        most = max((len(g.items) for g in spec.groups), default=1)
        if arrange == "grid" or n >= 5:
            return "21:9" if most <= 1 else "16:9"  # 두 줄 — 칸마다 항목 1개면 낮게
        # 한 줄(묶음 4개 이하)에 칸마다 항목 2개 이하면 낮고 넓게 — 실물 양식 미리보기에서 16:9 는
        # 빈 칸이 컸다
        return "21:9" if most <= 2 else "16:9"
    if isinstance(spec, ConceptSpec):
        return "21:9" if sum(len(b.lines) for b in spec.boxes) <= 4 else "16:9"
    if isinstance(spec, ProcessSpec):
        return "21:9" if all(len(s.outputs) <= 1 for s in spec.stages) else "16:9"
    if isinstance(spec, ScheduleSpec):
        longest = _longest(s.name for s in spec.stages)
        return "4:1" if len(spec.stages) <= 4 and longest <= 12 else "21:9"
    if isinstance(spec, RoadmapSpec):
        return "21:9"
    if isinstance(spec, StatChartSpec):
        return "21:9" if len(spec.categories) > 6 else "16:9"
    if isinstance(spec, ComparisonSpec):
        return "21:9" if len(spec.aspects) <= 2 else "16:9"
    return "16:9"


# ── 본문 폭·높이 ─────────────────────────────────────────
@dataclass(frozen=True)
class BodyFrame:
    """그림이 들어갈 자리 — 본문 안쪽 폭과 쪽 높이(mm). 실물 양식에서 읽는다(adapters/rendering/
    hwpx_geometry), 못 읽으면 기본값(별지 제2호서식 실측)."""

    width_mm: float = DEFAULT_BODY_WIDTH_MM
    page_height_mm: float = DEFAULT_PAGE_HEIGHT_MM
    height_share: float = HEIGHT_SHARE

    @property
    def max_height_mm(self) -> float:
        return self.page_height_mm * self.height_share

    @classmethod
    def from_hwp(
        cls, width_hwp: float, page_height_hwp: float, height_share: float = HEIGHT_SHARE
    ) -> BodyFrame:
        return cls(width_hwp / HWPUNIT_PER_MM, page_height_hwp / HWPUNIT_PER_MM, height_share)


def mm_to_hwp(mm: float) -> int:
    return int(round(mm * HWPUNIT_PER_MM))


def height_for(width_mm: float, aspect: str | None = None, pixels: tuple[int, int] | None = None):
    """폭(mm)과 비율(또는 실제 픽셀 크기)로 높이(mm)."""
    if pixels and pixels[0] > 0 and pixels[1] > 0:
        return width_mm * pixels[1] / pixels[0]
    return width_mm / ratio_value(aspect or "16:9")


def fits(frame: BodyFrame, aspect: str) -> bool:
    return height_for(frame.width_mm, aspect) <= frame.max_height_mm + 1e-6


def fit_aspect_for_frame(kind: str, aspect: str, frame: BodyFrame) -> tuple[str, bool]:
    """높이 상한을 넘으면 넓은 비율로 바꾼다 → (비율, 바꿨는가). 가장 넓어도 넘으면 그 비율."""
    widened = False
    while not fits(frame, aspect):
        nxt = wider(kind, aspect)
        if nxt is None:
            break
        aspect, widened = nxt, True
    return aspect, widened


# ── 글자 크기 ─────────────────────────────────────────────
def font_pt(units: float, width_mm: float, viewbox_w: float = VIEWBOX_W) -> float:
    """밑그림 글자 크기(viewBox 단위) → 본문 폭 width_mm 로 넣었을 때 pt."""
    return float(units) * float(width_mm) / float(viewbox_w) * PT_PER_MM


def min_font_units(min_pt: float, width_mm: float, viewbox_w: float = VIEWBOX_W) -> float:
    """min_pt 를 지키는 가장 작은 밑그림 글자 크기(viewBox 단위)."""
    return float(min_pt) * float(viewbox_w) / (float(width_mm) * PT_PER_MM)


@dataclass(frozen=True)
class SvgMetrics:
    min_font: float | None  # 밑그림에 쓴 가장 작은 글자 (viewBox 단위)
    overflow: int  # 하한 크기로도 칸에 다 들어가지 않은 글자 수


def svg_metrics(svg: str) -> SvgMetrics:
    """밑그림 SVG(이 앱이 만든 것)에서 글자 크기 최솟값과 넘침 표시(root data-overflow)를 읽는다."""
    sizes = [float(m.group(1)) for m in _FONT_SIZE.finditer(svg or "")]
    over = _OVERFLOW.search(svg or "")
    return SvgMetrics(min(sizes) if sizes else None, int(over.group(1)) if over else 0)


def _norm(text: str) -> str:
    return _SPACES.sub("", text or "").casefold()


def estimate_ocr_pt(
    lines: Sequence[tuple[str, float]],
    height_mm: float,
    texts: Sequence[str],
    *,
    box_em: float,
) -> float | None:
    """Nano Banana 그림의 글자 크기 어림 — OCR 줄 상자 높이(그림 높이 대비 0~1)를 본문 폭으로 넣은
    그림 높이
    (mm)로 바꾸고 box_em(상자 높이 ÷ 글자 크기, 밑그림으로 잰 값)으로 나눈다. 명세 글자와 겹치는
    줄만 쓴다
    (아이콘·잡음 제외). 겹치는 줄이 없으면 None."""
    wanted = [_norm(t) for t in texts if len(_norm(t)) >= 2]
    pts: list[float] = []
    for text, h in lines:
        n = _norm(text)
        if len(n) < 2 or h <= 0 or not any(n in w or w in n for w in wanted):
            continue
        pts.append(h * height_mm * PT_PER_MM / max(box_em, 0.1))
    return round(min(pts), 1) if pts else None


def make_fit(
    frame: BodyFrame,
    aspect: str,
    *,
    min_pt: float | None,
    min_text_pt: float = MIN_TEXT_PT,
    pixels: tuple[int, int] | None = None,
    method: str = "svg",
    redraws: int = 0,
    shortened: int = 0,
    widened: bool = False,
    width_mm: float | None = None,
) -> FigureFit:
    w = float(width_mm if width_mm is not None else frame.width_mm)
    h = height_for(w, aspect, pixels)
    return FigureFit(
        width_mm=round(w, 1),
        height_mm=round(h, 1),
        ratio=aspect,
        fits=h <= frame.max_height_mm + 1e-6,
        min_text_pt=None if min_pt is None else round(float(min_pt), 1),
        text_ok=min_pt is None or float(min_pt) + PT_TOLERANCE >= float(min_text_pt),
        text_method=method,  # type: ignore[arg-type]
        redraws=redraws,
        shortened=shortened,
        widened=widened,
    )


# ── 글자 줄이기 ───────────────────────────────────────────
def clip_words(text: str, limit: int) -> str:
    """limit 자를 넘으면 띄어쓰기 자리에서만 자른다(글자 중간·숫자 중간은 자르지 않는다 — 앞부분이
    원문
    그대로라 출처 검사를 그대로 통과한다). 자를 자리가 없으면 그대로."""
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    cut = value[: limit + 1]
    i = cut.rfind(" ")
    if i < 2:
        return value
    return value[:i].rstrip(" ,·")


def _clip_all(items: list[Any], key: str, limit: int, counter: list[int]) -> None:
    for it in items:
        old = it[key]
        if isinstance(old, str):
            new = clip_words(old, limit)
            if new != old:
                it[key] = new
                counter[0] += 1


def shorten_spec(spec: BaseModel, level: int) -> tuple[BaseModel, int] | None:
    """글자 크기를 맞추려고 글자를 줄인 명세 → (새 명세, 줄인 칸 수). 줄일 것이 없으면 None.
    수치 그래프는 값·이름을 건드리지 않는다. 일정표는 단계 이름만 줄이고 단계·기간은 그대로."""
    if level not in SHORTEN_LEVELS or isinstance(spec, StatChartSpec):
        return None
    box, per_group, max_rows, stage_name = SHORTEN_LEVELS[level]
    data = spec.model_dump()
    n = [0]
    if isinstance(spec, AsIsToBeSpec):
        for side in ("as_is", "to_be"):
            if len(data[side]) > 3:
                n[0] += len(data[side]) - 3
                data[side] = data[side][:3]
            _clip_all(data[side], "text", box, n)
        new = clip_words(data["solution"], box)
        if new != data["solution"]:
            data["solution"], n[0] = new, n[0] + 1
    elif isinstance(spec, TechniqueSpec):
        for g in data["groups"]:
            if len(g["items"]) > per_group:
                n[0] += len(g["items"]) - per_group
                g["items"] = g["items"][:per_group]
            _clip_all(g["items"], "text", box, n)
        if len(data["rows"]) > max_rows:
            n[0] += len(data["rows"]) - max_rows
            data["rows"] = data["rows"][:max_rows]
        _clip_all(data["rows"], "name", box, n)
    elif isinstance(spec, ConceptSpec):
        for b in data["boxes"]:
            keep = 1 if level >= 2 else 2
            if len(b["lines"]) > keep:
                n[0] += len(b["lines"]) - keep
                b["lines"] = b["lines"][:keep]
            new_lines = [clip_words(x, box) for x in b["lines"]]
            n[0] += sum(1 for a, c in zip(b["lines"], new_lines, strict=True) if a != c)
            b["lines"] = new_lines
    elif isinstance(spec, ProcessSpec):
        for st in data["stages"]:
            keep = 1 if level >= 2 else 2
            if len(st["outputs"]) > keep:
                n[0] += len(st["outputs"]) - keep
                st["outputs"] = st["outputs"][:keep]
            new_out = [clip_words(x, box) for x in st["outputs"]]
            n[0] += sum(1 for a, c in zip(st["outputs"], new_out, strict=True) if a != c)
            st["outputs"] = new_out
        _clip_all(data["stages"], "name", stage_name + 6, n)
    elif isinstance(spec, ScheduleSpec):
        _clip_all(data["stages"], "name", stage_name, n)
    elif isinstance(spec, RoadmapSpec):
        _clip_all(data["metrics"], "target", box, n)
        for st in data["stages"]:
            if st.get("desc"):
                new = clip_words(st["desc"], box)
                if new != st["desc"]:
                    st["desc"], n[0] = new, n[0] + 1
    elif isinstance(spec, ComparisonSpec):
        for proj in [*data["projects"], data["proposal"]]:
            for k, v in list(proj["cells"].items()):
                new = clip_words(v, box)
                if new != v:
                    proj["cells"][k], n[0] = new, n[0] + 1
    if not n[0]:
        return None
    return type(spec).model_validate(data), n[0]


# ── [23] 글자 크기 어림: 밑그림 대비 (상대) ─────────────────────
_TEXT_EL = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_ARIA = re.compile(r'aria-label="([^"]*)"')
_TAG = re.compile(r"<[^>]+>")
_ENT = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&#x27;": "'", "&amp;": "&"}
BIGGER_TEXT = (
    "글자를 더 크게: 직전 그림은 본문 폭으로 넣으면 가장 작은 글자가 약 {pt}pt 였다. 모든 글자(칸 "
    "이름표·"
    "눈금 숫자·안내문 포함)를 본문 글자와 거의 같은 크기로, 높이가 그림 폭의 2.2% 이상이 되게 "
    "한다. 이름표를 "
    "작은 꼬리표로 줄이지 말고, 자리가 모자라면 아이콘·여백을 줄인다. 글자는 바꾸지 않는다."
)


def _unescape(text: str) -> str:
    for k, v in _ENT.items():
        text = text.replace(k, v)
    return text


def svg_text_pts(svg: str, width_mm: float, viewbox_w: float = VIEWBOX_W) -> dict[str, float]:
    """밑그림 SVG 의 글자 → 본문 폭에서의 크기(pt). 여러 줄 글자는 aria-label(원문) 기준."""
    out: dict[str, float] = {}
    for m in _TEXT_EL.finditer(svg or ""):
        attrs, body = m.group(1), m.group(2)
        size = _FONT_SIZE.search(attrs)
        if not size:
            continue
        aria = _ARIA.search(attrs)
        text = _unescape(aria.group(1) if aria else _TAG.sub("", body)).strip()
        if not text:
            continue
        pt = font_pt(float(size.group(1)), width_mm, viewbox_w)
        out[text] = min(pt, out.get(text, pt))
    return out


def _height_for(text: str, lines: Sequence[tuple[str, float]]) -> float | None:
    """명세 글자 하나가 OCR 줄 어디에 있는지 — 같은 줄이 먼저, 없으면 그 글자의 한
    부분인
    줄(줄바꿈)."""
    t = _norm(text)
    exact = [h for s, h in lines if _norm(s) == t]
    if exact:
        return max(exact)
    parts = [h for s, h in lines if len(_norm(s)) >= 2 and _norm(s) in t]
    return max(parts) if parts else None


def estimate_relative_pt(
    base_lines: Sequence[tuple[str, float]],
    image_lines: Sequence[tuple[str, float]],
    *,
    base_height_mm: float,
    image_height_mm: float,
    text_pts: dict[str, float],
) -> float | None:
    """Nano Banana 그림의 가장 작은 글자(pt) 어림 — 같은 글자를 밑그림(크기를 안다)과 그림에서
    OCR
    로 재어
    높이 비(mm 기준)를 밑그림 크기에 곱한다. OCR 상자 높이 ÷ 글자 크기 비(글자 모양마다 다르다)가
    서로
    지워진다. 두 그림에서 함께 찾은 글자가 없으면 None."""
    cands: list[float] = []
    for text, pt in text_pts.items():
        if len(_norm(text)) < 2:
            continue
        hb = _height_for(text, base_lines)
        hi = _height_for(text, image_lines)
        if not hb or not hi:
            continue
        cands.append(pt * (hi * image_height_mm) / (hb * base_height_mm))
    return round(min(cands), 1) if cands else None


def pixel_ratio_label(aspect: str, pixels: tuple[int, int]) -> str:
    """실제 픽셀 비율이 고른 비율과 2% 안이면 그 이름, 아니면 "2.62:1"."""
    w, h = pixels
    if h <= 0:
        return aspect
    r = w / h
    if abs(r - ratio_value(aspect)) / ratio_value(aspect) < 0.02:
        return aspect
    return f"{r:.2f}:1"
