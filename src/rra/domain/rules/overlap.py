"""2. 기관별 중복 판정.

own 티어 = 우리 기관(코레일) 문서이면서 부서가 설정의 own 부서 목록(철도연구원 소속)에 있는 것.
부서명 부분 문자열로 판정하지 않는다 — 목록(config/sources.yaml `own_unit`)이 기준이다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from rra.domain.models import Document, OverlapAlert, Tier

DEFAULT_THRESHOLDS: dict[Tier, float] = {"own": 0.80, "domestic_rail": 0.85, "external": 0.90}
DOMESTIC_RAIL_ORGS = ("korail", "kr")
_TOKEN_SEP = re.compile(r"[\s,/·()（）]+")


class OwnUnit(BaseModel):
    """own 티어 기준: 기관 태그 + 그 기관 안의 own 부서 목록."""

    model_config = ConfigDict(frozen=True)

    org: str = "korail"
    departments: frozenset[str] = frozenset()


def _squash(text: str) -> str:
    return "".join(text.split())


def department_listed(department: str | None, own: OwnUnit) -> bool:
    """부서명 전체 또는 그 안의 토큰 하나가 목록과 정확히 같으면 True.

    "경영연구처"·"철도연구원 경영연구처"·"경영연구처(자산개발)" → 목록에 경영연구처가 있으면 True.
    "경영연구처분실" 처럼 목록 이름을 포함만 하는 경우는 False.
    """
    if not department:
        return False
    listed = {_squash(d) for d in own.departments}
    if _squash(department) in listed:
        return True
    return any(tok in listed for tok in _TOKEN_SEP.split(department) if tok)


def unlisted_department(doc: Document, own: OwnUnit) -> str | None:
    """own 기관 문서인데 부서가 목록에 없으면 그 부서명 (목록 보완이 필요한지 경고용)."""
    if own.org in doc.orgs and doc.department and not department_listed(doc.department, own):
        return doc.department
    return None


def tier_of(doc: Document, own: OwnUnit | None = None) -> Tier:
    if own is not None and own.org in doc.orgs and department_listed(doc.department, own):
        return "own"
    if any(o in DOMESTIC_RAIL_ORGS for o in doc.orgs):
        return "domestic_rail"
    return "external"


def judge(
    hits: list[tuple[Document, float]],
    thresholds: dict[Tier, float] | None = None,
    *,
    own: OwnUnit | None = None,
) -> list[OverlapAlert]:
    th = thresholds or DEFAULT_THRESHOLDS
    alerts = []
    for doc, sim in hits:
        t = tier_of(doc, own)
        alerts.append(
            OverlapAlert(
                doc_id=doc.doc_id,
                title=doc.title,
                tier=t,
                similarity=sim,
                blocking=sim >= th[t],
                basis=doc.text_basis,
            )
        )
    return sorted(alerts, key=lambda a: (-int(a.blocking), -a.similarity))
