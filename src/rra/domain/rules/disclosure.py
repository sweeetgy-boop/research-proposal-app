"""알리오 원문 공개 상태. 순수 함수."""

from __future__ import annotations

from datetime import date

from rra.domain.models import Document


def original_obtainable(doc: Document, today: date) -> bool:
    """공개 요약만 있는 문서인데 원문을 받을 수 있게 됐는가 (공개 표기 또는 공개예정일 경과)."""
    if doc.text_basis != "summary":
        return False
    disclosure = doc.raw.get("disclosure") or {}
    if disclosure.get("status") == "공개":
        return True
    try:
        open_date = date.fromisoformat(str(disclosure.get("open_date") or ""))
    except ValueError:
        return False
    return open_date <= today
