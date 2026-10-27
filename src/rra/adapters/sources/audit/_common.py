"""audit 공용 순수 함수 — 제목에서 기관 태그, 파일 이름 정리."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from rra.adapters.sources._orgs import org_tags

_SIZE = re.compile(r"\s*\(\s*[\d.,]+\s*(?:KB|MB|GB|bytes?)\s*\)\s*$", re.IGNORECASE)
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")


def strip_size(name: str) -> str:
    """'공개문_전문.pdf (2.49 MB)' → '공개문_전문.pdf'."""
    return _SIZE.sub("", name.strip())


def ext_of(name: str) -> str:
    m = _EXT.search(strip_size(name))
    return m.group(1).lower() if m else ""


def orgs_in_title(title: str, institutions: Sequence[Mapping[str, Any]]) -> list[str]:
    """제목에 든 철도 기관명 → 태그 (한국철도공사 정기감사 → korail)."""
    return org_tags([title], institutions)
