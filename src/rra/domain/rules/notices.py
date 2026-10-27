"""정부 R&D 사업공고 규칙 (순수, P2-7).

- `notice_key(title, agency, posted)`: 같은 공고가 KAIA·IRIS 두 사이트에 실려도 한 문서가 되도록
  제목(공고번호·괄호·
  공백·기호 제거)+기관+공고일로 만든 16자 해시. 기관이 비면 제목+공고일만.
- `parse_period("2026-07-16 ~ 2026-08-18")` → (시작, 마감). 마감일은 `Document.valid_until` 이 되어
  저장소의
  만료 규칙으로 검색·precheck 에서 빠진다.
- `is_open(deadline, today)`: 마감일 당일까지 접수 중.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

_DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_NOTICE_NO = re.compile(r"[(\[][^)\]]*(?:공고|제\s*\d+\s*호)[^)\]]*[)\]]")
_NOISE = re.compile(r"[\s\-_·‧ㆍ,.:;'\"“”‘’()\[\]<>《》〈〉/~∼]+")
_AGENCY_NOISE = re.compile(r"\s+|\(.*?\)")


def parse_date(text: str | None) -> date | None:
    m = _DATE.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_period(text: str | None) -> tuple[date | None, date | None]:
    """'2026-07-16 ~ 2026-08-18' → (시작, 마감). 날짜가 하나면 (그 날, None)."""
    found = [parse_date(m.group(0)) for m in _DATE.finditer(text or "")]
    found = [d for d in found if d is not None]
    if not found:
        return (None, None)
    if len(found) == 1:
        return (found[0], None)
    return (found[0], found[1])


def normalize_title(title: str) -> str:
    t = _NOTICE_NO.sub("", title or "")
    t = re.sub(r"재공고|공고|시행|안내", "", t)
    return _NOISE.sub("", t).lower()


def notice_key(title: str, agency: str | None, posted: date | str | None) -> str:
    agency_norm = _AGENCY_NOISE.sub("", agency or "")
    day = posted.isoformat() if isinstance(posted, date) else str(posted or "")[:10]
    raw = "\x1f".join([normalize_title(title), agency_norm, day])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_open(deadline: date | None, today: date) -> bool:
    return deadline is None or deadline >= today


def days_left(deadline: date | None, today: date) -> int | None:
    return None if deadline is None else (deadline - today).days
