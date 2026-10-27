"""OCR 결과로 '사진' 거르기 — Argon 판독 전에 호출을 아낀다 (2026-10-27 지시).

규칙(순수): OCR 이 성공했고, 글자 수가 적고(max_chars 미만), 숫자·표·도형 구조 신호(숫자, %,
괄호·구분선·화살표 같은 기호, 짧은 라벨 줄 여러 개)가 없으면 사진으로 본다. 사진은 Argon 에 보내지
않고 alt·캡션·페이지 제목만 메타로 남긴다. OCR 이 실패했거나 없으면 사진으로 보지 않는다(보수적 —
체계도는 OCR 이 못 읽을 수 있다). exempt_groups(전략·ESG·통계)는 규칙을 적용하지 않는다.

기준값은 2026-10-27 OCR 표본 2,062장 분포로 정했다: 글자 0 이 46%, 20자 미만·숫자 없음·줄 3개
미만이 55%(1,138장). config/vision.yaml photo 구역에서 조정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MAX_CHARS = 20
DEFAULT_MAX_LINES = 2
DEFAULT_EXEMPT_GROUPS = ("strategy", "esg_policy", "statistics")
_DIGIT = re.compile(r"\d")
_STRUCT = re.compile(r"[%|│┃┆→←↑↓▶▷■□○●◇◆△▲▽▼=+×÷/:\[\]()]")


@dataclass(frozen=True)
class PhotoRule:
    enabled: bool = True
    max_chars: int = DEFAULT_MAX_CHARS  # 이 미만이면 "글자가 적다"
    max_lines: int = DEFAULT_MAX_LINES  # 줄 수가 이보다 많으면 라벨·표일 수 있다
    exempt_groups: tuple[str, ...] = DEFAULT_EXEMPT_GROUPS
    short_label_lines: int = 3  # 6자 이하 짧은 줄이 이 수 이상이면 도형 라벨로 본다

    @classmethod
    def from_dict(cls, raw: dict | None) -> PhotoRule:
        raw = raw or {}
        groups = raw.get("exempt_groups")
        return cls(
            enabled=bool(raw.get("enabled", True)),
            max_chars=int(raw.get("max_chars", DEFAULT_MAX_CHARS)),
            max_lines=int(raw.get("max_lines", DEFAULT_MAX_LINES)),
            exempt_groups=tuple(str(g) for g in groups)
            if isinstance(groups, list)
            else DEFAULT_EXEMPT_GROUPS,
            short_label_lines=int(raw.get("short_label_lines", 3)),
        )


@dataclass(frozen=True)
class OcrSignals:
    ok: bool
    chars: int = 0
    lines: int = 0
    digits: int = 0
    structure: int = 0
    short_labels: int = 0
    texts: tuple[str, ...] = field(default_factory=tuple)


def ocr_signals(payload: Any) -> OcrSignals:
    """OCR 저장 형식({"ok", "result": {"lines": [{"text"}]}}) 또는 OcrResult 비슷한 객체 → 신호."""
    if payload is None:
        return OcrSignals(ok=False)
    if isinstance(payload, dict):
        if not payload.get("ok", True):
            return OcrSignals(ok=False)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        raw_lines = result.get("lines") or []
    else:
        raw_lines = getattr(payload, "lines", None) or []
    texts: list[str] = []
    for line in raw_lines:
        text = line.get("text") if isinstance(line, dict) else getattr(line, "text", line)
        text = str(text or "").strip()
        if text:
            texts.append(text)
    joined = " ".join(texts)
    return OcrSignals(
        ok=True,
        chars=len(joined.replace(" ", "")),
        lines=len(texts),
        digits=len(_DIGIT.findall(joined)),
        structure=len(_STRUCT.findall(joined)),
        short_labels=sum(1 for t in texts if len(t) <= 6),
        texts=tuple(texts),
    )


def is_photo(signals: OcrSignals, group: str | None, rule: PhotoRule | None = None) -> bool:
    rule = rule or PhotoRule()
    if not rule.enabled or not signals.ok:
        return False
    if group in rule.exempt_groups:
        return False
    if signals.chars >= rule.max_chars:
        return False
    if signals.digits or signals.structure:
        return False
    if signals.lines > rule.max_lines or signals.short_labels >= rule.short_label_lines:
        return False
    return True


def photo_meta(item: Any, signals: OcrSignals) -> dict[str, Any]:
    """사진으로 분류한 이미지에 남기는 메타 — alt·캡션·페이지 제목·OCR 글자 수만 (본문 없음)."""
    return {
        "alt": (getattr(item, "alt", None) or "")[:200],
        "caption": (getattr(item, "caption", None) or "")[:200],
        "page_title": (getattr(item, "page_title", None) or "")[:200],
        "ocr_chars": signals.chars,
        "ocr_lines": signals.lines,
    }
