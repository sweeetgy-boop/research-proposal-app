"""2. 기관별 중복 판정."""

from __future__ import annotations

from rra.domain.models import Document, OverlapAlert, Tier

DEFAULT_THRESHOLDS: dict[Tier, float] = {"own": 0.80, "domestic_rail": 0.85, "external": 0.90}


def tier_of(doc: Document) -> Tier:
    if doc.department and "철도연구원" in doc.department:
        return "own"
    if any(o in ("korail", "kr") for o in doc.orgs):
        return "domestic_rail"
    return "external"


def judge(
    hits: list[tuple[Document, float]], thresholds: dict[Tier, float] | None = None
) -> list[OverlapAlert]:
    th = thresholds or DEFAULT_THRESHOLDS
    alerts = []
    for doc, sim in hits:
        t = tier_of(doc)
        alerts.append(
            OverlapAlert(
                doc_id=doc.doc_id, title=doc.title, tier=t, similarity=sim, blocking=sim >= th[t]
            )
        )
    return sorted(alerts, key=lambda a: (-int(a.blocking), -a.similarity))
