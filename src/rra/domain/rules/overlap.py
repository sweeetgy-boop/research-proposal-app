"""2. 기관별 중복 판정.

own 티어 = 우리 기관(코레일) 문서이면서 부서가 설정의 own 부서 목록(철도연구원 소속)에 있는 것.
부서명 부분 문자열로 판정하지 않는다 — 목록(config/sources.yaml `own_unit`)이 기준이다.
"""

from __future__ import annotations

import re
from typing import get_args

from pydantic import BaseModel, ConfigDict

from rra.domain.models import Document, OverlapAlert, SourceType, Tier
from rra.domain.models.gap import OwnDetail
from rra.domain.rules.keywords import KeywordRule, enough, keyword_overlap

# national_rnd(NTIS 과제검색)·procurement(발주 용역 공고, P2-6)는 own 과 같은 0.80 으로 시작 —
# 표본이 쌓이면 config/overlap.yaml 설명대로 조정 (2026-10-27, ADR 0020·0021)
DEFAULT_THRESHOLDS: dict[Tier, float] = {
    "own": 0.80,
    "national_rnd": 0.80,
    "domestic_rail": 0.85,
    "external": 0.90,
    "procurement": 0.80,
}
# 발주 용역 공고 문서의 raw.status 값 — 알림에는 "용역으로 진행 중/예정" 으로 보인다
PROCURING_STATUS = "procuring"
STATUS_LABELS: dict[str, str] = {
    "completed": "완료",
    "ongoing": "진행중",
    "stopped": "중단",
    "rejected": "미채택 — 보완 재제안 검토",
    "proposed": "제안·검토 중",
    PROCURING_STATUS: "용역으로 진행 중/예정",
}
# 국가R&D 과제 티어 = NTIS 과제검색 문서(source ntis, doc_type rnd_project). 수행기관이 코레일이어도
# 부서가 없어 own 이 될 수 없으므로 own 다음 순서로 본다
NATIONAL_RND_SOURCES: frozenset[str] = frozenset({"ntis"})
# 사내 과제 기록(엑셀 4개) 출처 — 부서와 관계없이 own 티어. 알림은 철도연구원/공사 부서를 구분한다
OWN_RECORD_SOURCES: frozenset[str] = frozenset({"own"})
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
    """own 기관 문서인데 부서가 목록에 없으면 그 부서명 (목록 보완이 필요한지 경고용).

    사내 과제 기록(source own)은 공사 전 부서의 제안·수행 기록이라 경고하지 않는다."""
    if doc.source in OWN_RECORD_SOURCES:
        return None
    if own.org in doc.orgs and doc.department and not department_listed(doc.department, own):
        return doc.department
    return None


def tier_of(doc: Document, own: OwnUnit | None = None) -> Tier:
    """사내 과제 기록(source own)은 부서와 관계없이 own. 발주 용역 공고(doc_type procurement)는
    기관과 관계없이 procurement. 그 밖은 기관 태그 + own 부서 목록으로."""
    if doc.doc_type == "procurement":
        return "procurement"
    if doc.source in OWN_RECORD_SOURCES:
        return "own"
    if own is not None and own.org in doc.orgs and department_listed(doc.department, own):
        return "own"
    if is_national_rnd(doc):
        return "national_rnd"
    if any(o in DOMESTIC_RAIL_ORGS for o in doc.orgs):
        return "domestic_rail"
    return "external"


def is_national_rnd(doc: Document) -> bool:
    """NTIS 과제검색으로 수집한 국가R&D 과제 (보고서·성과는 아님)."""
    return doc.source in NATIONAL_RND_SOURCES and doc.doc_type == "rnd_project"


def own_detail_of(doc: Document, own: OwnUnit | None) -> OwnDetail | None:
    """own 티어의 세부 구분: 철도연구원 부서면 institute, 그 외(공사 부서·부서 없음)면 company."""
    if tier_of(doc, own) != "own":
        return None
    if own is not None and department_listed(doc.department, own):
        return "institute"
    return "company" if doc.source in OWN_RECORD_SOURCES else "institute"


def document_text(doc: Document) -> str:
    """키워드 대조에 쓰는 문서 텍스트 (비신뢰 — 토큰 비교에만 쓴다)."""
    return " ".join(p for p in (doc.title, doc.abstract, doc.body) if p)


def judge(
    hits: list[tuple[Document, float]],
    thresholds: dict[Tier, float] | None = None,
    *,
    own: OwnUnit | None = None,
    query: str | None = None,
    keywords: KeywordRule | None = None,
) -> list[OverlapAlert]:
    """임계치 초과 문서를 경보로. `keywords` 가 있으면 차단에는 질의 키워드가 문서에도
    `min_hits` 개 이상 등장해야 한다 (e5 유사도만으로는 무관한 한국어 문서도 임계치를 넘는다).
    `keywords` 가 없으면 종전처럼 유사도만 본다."""
    th = thresholds or DEFAULT_THRESHOLDS
    alerts = []
    for doc, sim in hits:
        t = tier_of(doc, own)
        shared = keyword_overlap(query or "", document_text(doc), keywords) if keywords else []
        over = sim >= th[t]
        blocking = over and (keywords is None or enough(shared, keywords))
        status = doc.raw.get("status")
        alerts.append(
            OverlapAlert(
                doc_id=doc.doc_id,
                title=doc.title,
                tier=t,
                similarity=sim,
                blocking=blocking,
                basis=doc.text_basis,
                keywords=shared,
                status=status if isinstance(status, str) and status else None,
                own_detail=own_detail_of(doc, own),
            )
        )
    return sorted(alerts, key=lambda a: (-int(a.blocking), -a.similarity))


_TIER_LABEL: dict[Tier, str] = {
    "own": "사내",
    "national_rnd": "국가R&D 과제",
    "domestic_rail": "국내 철도기관",
    "external": "외부",
    "procurement": "발주 용역",
}
OWN_DETAIL_LABEL: dict[str, str] = {"institute": "사내(철도연구원)", "company": "사내(공사)"}


def tier_label(tier: Tier, own_detail: str | None = None) -> str:
    """알림 표시용 — own 은 철도연구원/공사 부서를 구분한다."""
    if tier == "own":
        return OWN_DETAIL_LABEL.get(own_detail or "institute", "사내")
    return _TIER_LABEL[tier]


# 자료원 → 검토 범위 문장에 쓰는 이름. 순서 = 문장에 나열하는 순서
SOURCE_LABELS: dict[str, str] = {
    "own": "사내 과제 현황",
    "alio": "알리오 공시 연구보고서",
    "ntis": "NTIS 국가R&D 과제",
    "scienceon": "ScienceON 국내 논문·보고서",
    "openalex": "OpenAlex 해외 논문",
    "kipris_kr": "KIPRIS 국내 특허",
    "kipris_intl": "KIPRIS 해외 특허",
    "korail_web": "공사 홈페이지 정책·보도자료",
    "molit": "국토교통부 철도 계획·정책",
    "g2b": "나라장터 발주 용역 공고",
    "bai": "감사원 감사결과",
    "mofe": "기획재정부 공공기관 경영평가",
    "datago": "공공데이터포털 철도 통계",
}
ALL_SOURCES: tuple[str, ...] = tuple(get_args(SourceType))
# 유사과제 판정에 쓰지 않는 자료원 — 검토 범위·미수집 문장에 넣지 않는다 (정책·보도자료·감사·통계는
# 근거
# 전용).
# g2b(발주 용역 공고)는 판정에 들어간다(procurement 티어).
NON_OVERLAP_SOURCES: frozenset[str] = frozenset({"korail_web", "molit", "bai", "mofe", "datago"})
OVERLAP_SOURCES: tuple[str, ...] = tuple(s for s in ALL_SOURCES if s not in NON_OVERLAP_SOURCES)


def uncollected_sources(counts: dict[str, int]) -> list[str]:
    """유사과제 판정 자료원 중 적재 문서가 한 건도 없는 것 (SourceType 순서)."""
    return [s for s in OVERLAP_SOURCES if not counts.get(s)]


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _ordered(sources) -> list[str]:
    order = list(SOURCE_LABELS)
    return sorted(sources, key=lambda s: (order.index(s) if s in order else len(order), s))


def no_overlap_statement(
    scope: dict[str, int],
    uncollected: list[str] | None,
    thresholds: dict[Tier, float] | None = None,
) -> list[str]:
    """5. 특이사항 — 중복 기준을 넘는 유사과제가 없을 때 앱이 쓰는 확정 문장 (LLM 미사용).

    실제로 본 범위(자료원별 문서 수)와 아직 수집되지 않은 자료원을 함께 적는다.
    사내 과제·국가R&D 를 모두 찾아본 것처럼 읽히지 않게 하기 위함이다.
    """
    if not scope:
        return ["비교할 수집 자료가 없어 기수행 유사과제 검토를 수행하지 못함."]
    th = thresholds or DEFAULT_THRESHOLDS
    tiers: tuple[Tier, ...] = ("own", "national_rnd", "domestic_rail", "external", "procurement")
    criteria = ", ".join(f"{_TIER_LABEL[t]} {th[t]:.2f}" for t in tiers if t in th)
    searched = ", ".join(f"{_label(s)} {scope[s]}건" for s in _ordered(scope))
    out = [f"유사과제 검토 범위는 수집 자료 중 본 제안과 관련도가 높은 {searched}임."]
    if uncollected:
        missing = ", ".join(_label(s) for s in _ordered(uncollected))
        out.append(f"미수집 자료원({missing})은 검토 범위에서 제외됨.")
    out.append(f"위 범위에서 중복 판정 기준(유사도 {criteria}) 이상의 유사과제는 확인되지 않음.")
    return out
