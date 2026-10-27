"""U4 차별성 비교표의 순수 규칙.

- section_sentences: 요약·초록 본문에서 머리말(연구목적·연구내용·기대효과·활용계획 …) 아래 문장을
  뽑는다. 머리말 없는 본문은 첫 문장들로 연구목표 칸만 채운다.
- comparison_table: precheck 알림 상위 5건(유사도순) × 항목. 문서에 요약·초록이 없으면
  "정보 없음(제목 기준)". 제안 쪽은 제안자 입력(goal·current_state·constraints·beneficiaries·
  differentiation)에서 온다. LLM 없음.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.comparison import (
    MAX_CELL_CHARS,
    NO_INFO,
    NO_INFO_TITLE_ONLY,
    ComparisonColumn,
    ComparisonTable,
)
from rra.domain.rules.versions import split_sentences

MAX_PROJECTS = 5
# aspect → 본문 머리말 후보 (공시 요약·과제 요약·초록의 흔한 표기)
HEADINGS: dict[str, tuple[str, ...]] = {
    "objective": ("연구목적", "연구 목적", "연구목표", "연구 목표", "목적", "목표", "Objective"),
    "method": ("연구내용", "연구 내용", "연구방법", "연구 방법", "주요내용", "추진내용", "Method"),
    "scope": ("적용범위", "적용 범위", "연구범위", "연구 범위", "대상", "Scope"),
    "outcome": ("기대효과", "기대 효과", "활용계획", "활용 계획", "성과", "Results", "Conclusion"),
}
_HEAD = re.compile(r"^\s*[■◦○●□\-\*·\d\.\)\(]*\s*([가-힣A-Za-z ]{2,12})\s*[:：]?\s*(.*)$")


def _cut(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_CELL_CHARS else text[: MAX_CELL_CHARS - 1] + "…"


def section_sentences(body: str) -> dict[str, list[str]]:
    """머리말 기반 추출 — {aspect: [문장…]}. "연구목적: …" 처럼 한 줄이면 뒤 글도 받는다."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _HEAD.match(line)
        found: str | None = None
        rest = ""
        if m:
            head = m.group(1).replace(" ", "")
            for aspect, names in HEADINGS.items():
                if any(head.startswith(n.replace(" ", "")) for n in names):
                    found = aspect
                    rest = m.group(2).strip()
                    break
        if found is not None:
            current = found
            out.setdefault(current, [])
            if rest:
                out[current].extend(split_sentences(rest))
            continue
        if current is not None:
            out[current].extend(split_sentences(line))
    return {k: v for k, v in out.items() if v}


def project_column(alert: OverlapAlert, doc: Document | None) -> ComparisonColumn:
    body = ""
    basis = alert.basis
    if doc is not None:
        body = doc.abstract or doc.body or ""
        basis = basis or doc.text_basis
    cells: dict[str, str] = {}
    title_only = not body.strip()
    if title_only:
        cells = {k: NO_INFO_TITLE_ONLY for k in ("objective", "method", "scope", "outcome")}
    else:
        parts = section_sentences(body)
        if not parts:  # 머리말 없는 초록 → 첫 문장들을 연구목표 칸에
            parts = {"objective": split_sentences(body)[:2]}
        for key in ("objective", "method", "scope", "outcome"):
            sentences = parts.get(key)
            cells[key] = _cut(" ".join(sentences[:3])) if sentences else NO_INFO
    cells["differentiation"] = "—"  # 제안 쪽에서 적는다
    return ComparisonColumn(
        doc_id=alert.doc_id,
        title=alert.title,
        tier=alert.tier,
        similarity=round(alert.similarity, 4),
        blocking=alert.blocking,
        basis=basis,
        title_only=title_only,
        cells=cells,
    )


def proposal_column(req: ProposalRequest, differentiation: str = "") -> ComparisonColumn:
    scope = " ".join(x for x in (req.beneficiaries, req.constraints) if x).strip()
    direction = (differentiation or req.differentiation or "").strip()
    return ComparisonColumn(
        doc_id=None,
        title=req.title_hint or "(가제 없음)",
        cells={
            "objective": _cut(req.goal),
            "method": _cut(req.limitation and f"현행 한계: {req.limitation}") or NO_INFO,
            "scope": _cut(scope) or NO_INFO,
            "outcome": _cut(req.remarks) or NO_INFO,
            "differentiation": _cut(direction)
            or "(차별화 방향 미정 — 차별화 제안·추천에서 고를 것)",
        },
    )


def comparison_table(
    req: ProposalRequest,
    alerts: Iterable[OverlapAlert],
    docs: Mapping[str, Document | None],
    *,
    differentiation: str = "",
) -> ComparisonTable:
    ranked = sorted(alerts, key=lambda a: (-a.similarity, a.doc_id))
    seen: set[str] = set()
    projects: list[ComparisonColumn] = []
    for alert in ranked:
        if alert.doc_id in seen:
            continue
        seen.add(alert.doc_id)
        projects.append(project_column(alert, docs.get(alert.doc_id)))
        if len(projects) >= MAX_PROJECTS:
            break
    return ComparisonTable(proposal=proposal_column(req, differentiation), projects=projects)
