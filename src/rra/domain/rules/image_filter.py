"""장식 이미지 거르기 — 순수 규칙 (P3 ① 거르기).

로고·배너·아이콘·버튼·글자 없는 홍보 사진을 Argon 에 보내지 않는다. 판정 근거:
- 크기: 너무 작은 것(아이콘), 너무 가로로 긴 것(배너), 너무 세로로 긴 것(사이드 띠)
- 파일 이름·URL 경로 패턴: logo, icon, btn, banner, bg, sprite, bullet, arrow, dot, blank …
- alt 텍스트 패턴: "로고", "배너", "아이콘", "버튼" …
- 반복: 같은 sha256 이 여러 페이지에 실리면(머리글·바닥글·공통 띠) 제외
- 형식: svg·gif 는 판독 대상이 아니다 (svg 는 텍스트라 크롤 쪽에서 따로 다룬다)

판정은 이유 코드와 함께 돌려주고, 보고서는 제외/유지 건수를 이유별로 센다.
크기를 모르는 항목(width·height 없음)은 크기 규칙을 건너뛴다 — 보수적으로 유지한다.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from rra.domain.models.vision import ImageItem

DEFAULT_NAME_PATTERNS: tuple[str, ...] = (
    "logo",
    "icon",
    "ico_",
    "btn",
    "button",
    "banner",
    "bnr",
    "bg_",
    "_bg",
    "background",
    "sprite",
    "bullet",
    "blt_",
    "arrow",
    "arr_",
    "dot",
    "blank",
    "spacer",
    "line",
    "divider",
    "sns",
    "facebook",
    "instagram",
    "youtube",
    "twitter",
    "kakao",
    "favicon",
    "loading",
    "pixel",
    "tracking",
    "qr",
)
DEFAULT_ALT_PATTERNS: tuple[str, ...] = (
    "로고",
    "배너",
    "아이콘",
    "버튼",
    "바로가기",
    "logo",
    "banner",
    "icon",
    "button",
    "사진",  # 글자 없는 홍보 사진: alt 가 "~사진" 이면 제외 (표·그래프 alt 는 다르다)
    "이미지 없음",
)
DEFAULT_SKIP_MIME: tuple[str, ...] = ("image/svg+xml", "image/gif")
DEFAULT_SKIP_EXT: tuple[str, ...] = (".svg", ".gif", ".ico")


@dataclass(frozen=True)
class ImageFilterConfig:
    min_width: int = 120
    min_height: int = 80
    min_pixels: int = 20_000  # 가로×세로
    max_aspect: float = 5.0  # 가로/세로 또는 세로/가로가 이 값을 넘으면 띠·배너
    max_repeat_pages: int = 3  # 같은 해시가 이보다 많은 페이지에 실리면 공통 장식
    max_bytes: int = 15 * 1024 * 1024  # 판독에 보낼 최대 바이트 (DoS)
    name_patterns: tuple[str, ...] = DEFAULT_NAME_PATTERNS
    alt_patterns: tuple[str, ...] = DEFAULT_ALT_PATTERNS
    skip_mime: tuple[str, ...] = DEFAULT_SKIP_MIME
    skip_ext: tuple[str, ...] = DEFAULT_SKIP_EXT

    @classmethod
    def from_dict(cls, raw: dict | None) -> ImageFilterConfig:
        raw = raw or {}

        def strs(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = raw.get(key)
            if not isinstance(value, list):
                return default
            return tuple(str(v).lower() for v in value if str(v).strip())

        return cls(
            min_width=int(raw.get("min_width", cls.min_width)),
            min_height=int(raw.get("min_height", cls.min_height)),
            min_pixels=int(raw.get("min_pixels", cls.min_pixels)),
            max_aspect=float(raw.get("max_aspect", cls.max_aspect)),
            max_repeat_pages=int(raw.get("max_repeat_pages", cls.max_repeat_pages)),
            max_bytes=int(raw.get("max_bytes", cls.max_bytes)),
            name_patterns=strs("name_patterns", DEFAULT_NAME_PATTERNS),
            alt_patterns=strs("alt_patterns", DEFAULT_ALT_PATTERNS),
            skip_mime=strs("skip_mime", DEFAULT_SKIP_MIME),
            skip_ext=strs("skip_ext", DEFAULT_SKIP_EXT),
        )


@dataclass(frozen=True)
class FilterDecision:
    item: ImageItem
    reason: str | None  # None = 유지. 그 외 제외 이유 코드


@dataclass
class FilterReport:
    kept: list[ImageItem] = field(default_factory=list)
    excluded: list[FilterDecision] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out = {"kept": len(self.kept), "excluded": len(self.excluded)}
        out.update(Counter(d.reason or "" for d in self.excluded))
        return out


_NAME_SPLIT = re.compile(r"[^a-z0-9가-힣]+")


def _name_tokens(item: ImageItem) -> str:
    """경로·URL 의 파일 이름 부분(소문자). 쿼리는 뗀다."""
    parts = []
    for value in (item.path, item.url or ""):
        tail = value.rsplit("/", 1)[-1].split("?", 1)[0].lower()
        parts.append(tail)
    return " ".join(parts)


def _ext(item: ImageItem) -> str:
    name = (item.url or item.path).split("?", 1)[0].rsplit("/", 1)[-1].lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def classify(item: ImageItem, cfg: ImageFilterConfig | None = None) -> str | None:
    """None 이면 판독 대상. 아니면 제외 이유 코드."""
    cfg = cfg or ImageFilterConfig()
    if item.mime and item.mime.lower() in cfg.skip_mime:
        return "format"
    if _ext(item) in cfg.skip_ext:
        return "format"
    if item.bytes is not None and item.bytes > cfg.max_bytes:
        return "too_large"
    if item.bytes is not None and item.bytes <= 0:
        return "empty"
    if item.repeat_pages > cfg.max_repeat_pages:
        return "repeated"
    name = _name_tokens(item)
    if any(p in name for p in cfg.name_patterns):
        return "name_pattern"
    alt = f"{item.alt or ''} {item.caption or ''}".strip().lower()
    if alt and any(p in alt for p in cfg.alt_patterns):
        return "alt_pattern"
    if item.width is not None and item.height is not None:
        w, h = item.width, item.height
        if w <= 0 or h <= 0:
            return "empty"
        if w < cfg.min_width or h < cfg.min_height or w * h < cfg.min_pixels:
            return "tiny"
        ratio = max(w / h, h / w)
        if ratio > cfg.max_aspect:
            return "aspect"
    return None


def count_repeats(items: Iterable[ImageItem]) -> dict[str, int]:
    """sha256 → 실린 페이지 수 (page_url 기준, 없으면 항목 수)."""
    pages: dict[str, set[str]] = {}
    for it in items:
        pages.setdefault(it.sha256, set()).add(it.page_url or f"#{len(pages.get(it.sha256, ()))}")
    return {k: len(v) for k, v in pages.items()}


def filter_images(items: Sequence[ImageItem], cfg: ImageFilterConfig | None = None) -> FilterReport:
    """같은 해시는 한 번만 판독한다(첫 항목 기준). 반복 수는 전체에서 센 뒤 판정한다."""
    cfg = cfg or ImageFilterConfig()
    repeats = count_repeats(items)
    report = FilterReport()
    seen: set[str] = set()
    for it in items:
        if it.sha256 in seen:
            report.excluded.append(FilterDecision(it, "duplicate"))
            continue
        seen.add(it.sha256)
        candidate = it.model_copy(update={"repeat_pages": max(it.repeat_pages, repeats[it.sha256])})
        reason = classify(candidate, cfg)
        if reason is None:
            report.kept.append(candidate)
        else:
            report.excluded.append(FilterDecision(candidate, reason))
    return report
