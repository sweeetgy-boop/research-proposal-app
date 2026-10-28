"""과제 제목 표시·내려받기 파일 이름 (항목 2) — 순수 규칙.

- 화면 머리·run 목록의 제목: 현재 버전의 1-가 연구과제명 문장, 없으면 제안자가 적은
  가제(title_hint). 둘 다 없으면 빈 문자열(화면이 "제목 미정" 으로 보인다). 자료 태그 조각은
  지운다(clean_sentence).
- HWPX 파일 이름: "<과제 제목>_v<번호>.hwpx". 파일 이름에 쓸 수 없는 글자(\\ / : * ? " < > | 와
  제어 문자)는 지우고, 공백은 하나로, 앞뒤 점·공백은 뗀다. 제목 부분은 MAX_TITLE_CHARS 글자까지
  (넘으면 자르고 "…"). 제목이 비면 "연구과제제안서". ASCII 대체 이름(옛 브라우저용)은
  "proposal-<run>-v<n>.hwpx".
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from rra.domain.rules.llm_output import clean_sentence

MAX_TITLE_CHARS = 60
FALLBACK_TITLE = "연구과제제안서"
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")
# Windows 예약 이름 — 제목이 이것뿐이면 대체 이름
_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)$", re.I)


def draft_title(sections: Iterable[Any], request: Any | None = None) -> str:
    """현재 버전 섹션 목록(Section 또는 dict)에서 연구과제명. 없으면 가제, 그것도 없으면 ""."""
    for sec in sections or []:
        key = sec.get("key") if isinstance(sec, dict) else getattr(sec, "key", None)
        if key != "title":
            continue
        sentences = sec.get("sentences") if isinstance(sec, dict) else getattr(sec, "sentences", [])
        texts = [
            clean_sentence(s.get("text", "") if isinstance(s, dict) else getattr(s, "text", ""))
            for s in sentences or []
        ]
        joined = " ".join(t for t in texts if t).strip()
        if joined:
            return joined
    hint = getattr(request, "title_hint", "") if request is not None else ""
    return clean_sentence(hint or "").strip()


def safe_title(title: str, *, limit: int = MAX_TITLE_CHARS) -> str:
    """파일 이름에 넣을 제목 — 금지 글자 제거·공백 정리·길이 제한. 비면 FALLBACK_TITLE."""
    text = unicodedata.normalize("NFC", title or "")
    text = _INVALID.sub(" ", text)
    text = _SPACES.sub(" ", text).strip().strip(".").strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    if not text or _RESERVED.match(text):
        return FALLBACK_TITLE
    return text


def hwpx_filename(title: str, version: int) -> str:
    """내려받기 파일 이름 "<제목>_v<번호>.hwpx"."""
    return f"{safe_title(title)}_v{int(version)}.hwpx"


def ascii_filename(run_id: str, version: int) -> str:
    """RFC 5987 을 모르는 클라이언트용 ASCII 이름."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", run_id)[:40] or "run"
    return f"proposal-{safe}-v{int(version)}.hwpx"
