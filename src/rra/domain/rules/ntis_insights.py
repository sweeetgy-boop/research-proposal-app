"""NTIS 부가 조회(성과검색·연관콘텐츠 추천)의 판단 규칙. 순수 함수.

② 유사과제 알림 중 NTIS 과제(doc_id `ntis:<과제번호>`, 티어 national_rnd)의 과제번호로
- 주요 성과(논문·특허)를 조회해 과제 카드에 **참고용**으로 붙인다 (양식 본문 근거로는 쓰지
  않는다),
- 연관 과제를 받아 우리 검색(알림·저장소)에 없던 것만 "NTIS 추천" 으로 보인다. API 응답은 비신뢰 —
  항목 수·길이·과제번호 형식을 여기서 제한한다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models import OverlapAlert

PROJECT_NO = re.compile(r"^[0-9A-Za-z_-]{4,40}$")
MAX_PROJECTS = 3  # 알림 상위 몇 과제까지 조회하는가
MAX_ITEMS = 10  # 과제당 성과·추천 최대 수
MAX_TITLE_CHARS = 300
MAX_RECOMMENDED = 10
OUTCOME_KINDS: tuple[str, ...] = ("paper", "patent")


class Outcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str  # paper | patent
    title: str
    year: str | None = None
    venue: str | None = None  # 논문: 학술지명 / 특허: 등록(출원)기관 또는 국가
    result_id: str | None = None
    registration_no: str | None = None  # 특허 등록·출원번호


class RelatedProject(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_no: str
    title: str
    score: float | None = None
    rank: int | None = None
    source_project_no: str  # 어느 알림 과제에서 추천됐는가


def project_no_of(doc_id: str) -> str | None:
    """`ntis:1415117501` → `1415117501`. NTIS 과제가 아니거나 형식이 다르면 None."""
    prefix, _, native = doc_id.partition(":")
    if prefix != "ntis" or not PROJECT_NO.match(native):
        return None
    return native


def target_projects(
    alerts: Iterable[OverlapAlert], limit: int = MAX_PROJECTS
) -> list[OverlapAlert]:
    """조회 대상 = 알림 중 national_rnd 티어 NTIS 과제, 차단 → 유사도 순 상위 limit."""
    picked: list[OverlapAlert] = []
    seen: set[str] = set()
    for a in sorted(alerts, key=lambda a: (-int(a.blocking), -a.similarity)):
        no = project_no_of(a.doc_id)
        if a.tier != "national_rnd" or no is None or no in seen:
            continue
        seen.add(no)
        picked.append(a)
        if len(picked) >= limit:
            break
    return picked


def _text(value: Any, limit: int = MAX_TITLE_CHARS) -> str:
    return " ".join(str(value).split())[:limit] if isinstance(value, str | int | float) else ""


def validate_outcomes(items: Iterable[Mapping[str, Any]], limit: int = MAX_ITEMS) -> list[Outcome]:
    """어댑터가 정규화한 dict 목록 → Outcome (종류·제목 없는 것 제외, 중복 제목 제거, 상한)."""
    out: list[Outcome] = []
    seen: set[tuple[str, str]] = set()
    for it in items:
        kind, title = _text(it.get("kind"), 20), _text(it.get("title"))
        if kind not in OUTCOME_KINDS or not title or (kind, title) in seen:
            continue
        seen.add((kind, title))
        out.append(
            Outcome(
                kind=kind,
                title=title,
                year=_text(it.get("year"), 4) or None,
                venue=_text(it.get("venue"), 120) or None,
                result_id=_text(it.get("result_id"), 60) or None,
                registration_no=_text(it.get("registration_no"), 40) or None,
            )
        )
        if len(out) >= limit:
            break
    return out


def validate_related(
    items: Iterable[Mapping[str, Any]],
    *,
    source_project_no: str,
    known: Iterable[str],
    limit: int = MAX_ITEMS,
) -> list[RelatedProject]:
    """연관 과제 → 우리 검색에 없던 것(known 제외)만, 과제번호 형식 검증, 상한."""
    known_set = set(known) | {source_project_no}
    out: list[RelatedProject] = []
    for it in items:
        no, title = _text(it.get("project_no"), 40), _text(it.get("title"))
        if not PROJECT_NO.match(no) or not title or no in known_set:
            continue
        known_set.add(no)
        score = it.get("score")
        rank = it.get("rank")
        out.append(
            RelatedProject(
                project_no=no,
                title=title,
                score=float(score) if isinstance(score, int | float) and 0 <= score <= 1 else None,
                rank=int(rank) if isinstance(rank, int) and 0 < rank < 1000 else None,
                source_project_no=source_project_no,
            )
        )
        if len(out) >= limit:
            break
    return out


class ProjectInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_no: str
    doc_id: str
    title: str
    tier: str
    similarity: float
    blocking: bool
    outcomes: list[Outcome] = Field(default_factory=list)
    cached: bool = False
    error: str | None = None  # 조회 실패 — 예외 클래스명만


class NtisInsights(BaseModel):
    model_config = ConfigDict(frozen=True)

    projects: list[ProjectInsight] = Field(default_factory=list)
    recommended: list[RelatedProject] = Field(default_factory=list)


def merge_recommended(
    groups: Iterable[list[RelatedProject]], limit: int = MAX_RECOMMENDED
) -> list[RelatedProject]:
    """여러 알림 과제의 추천을 합친다 — 과제번호 중복 제거, 점수 내림차순, 상한."""
    best: dict[str, RelatedProject] = {}
    for group in groups:
        for r in group:
            cur = best.get(r.project_no)
            if cur is None or (r.score or 0) > (cur.score or 0):
                best[r.project_no] = r
    return sorted(best.values(), key=lambda r: (-(r.score or 0), r.rank or 999, r.project_no))[
        :limit
    ]
