"""U4 차별성 비교표의 순수 규칙.

- section_sentences: 요약·초록 본문에서 머리말(연구목적·연구내용·기대효과·활용계획 …) 아래 문장을
  뽑는다. 머리말 없는 본문은 첫 문장들로 연구목표 칸만 채운다.
- comparison_table: 넘겨받은 유사과제(② 에서 [유사함] 으로 고른 행 — 호출자가 거른다) 상위 5건 ×
  항목. 문서에 요약·초록이 없으면 "정보 없음(제목 기준)". 제안 쪽은 제안자 입력(가제·연구목표·
  연구방법·적용범위·차별화 방향)에서, 초안이 있으면 초안 섹션에서 온다 (2026-10-28 레인 A).
- 기존 과제 칸은 Argon 이 원문에서 뽑은 1~2문장(cell_from_llm 검증 통과분)을 우선 쓰고, 없으면 규칙
  추출 — 기호·잘린 문장 없이 온전한 문장만(clean_cell). 적용범위가 원문에 없으면 "정보 없음".
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.comparison import (
    MAX_CELL_CHARS,
    NO_INFO,
    NO_INFO_TITLE_ONLY,
    ComparisonColumn,
    ComparisonTable,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.keywords import tokens
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted
from rra.domain.rules.versions import split_sentences

MAX_PROJECTS = 5
CELL_KEYS: tuple[str, ...] = ("objective", "method", "scope", "outcome")
CELL_MAX_SENTENCES = 2
# 제안 행 — 입력에 없는 칸의 안내 (내부 코드·필드 이름을 보이지 않는다)
PROPOSAL_NO_TITLE = "(가제 미정)"
PROPOSAL_NO_METHOD = "정보 없음 — 과제안을 고르거나 직접 적으면 채워집니다"
PROPOSAL_NO_OUTCOME = "정보 없음 — 초안이 만들어지면 채워집니다"
PROPOSAL_NO_DIRECTION = "(차별화 방향 미정 — 아래 차별화 과제안에서 고르거나 직접 적으십시오)"
EMPTY_NO_SIMILAR = "유사한 과제를 고르면 비교표가 만들어집니다"
# 초안 섹션 → 비교 항목 (초안이 있으면 제안 행을 초안으로 다시 채운다)
DRAFT_SECTIONS: dict[str, tuple[str, ...]] = {
    "title": ("title",),
    "objective": ("objective",),
    "method": ("method",),
    "outcome": ("expected_technology", "expected_management", "expected_standing"),
}
# aspect → 본문 머리말 후보 (공시 요약·과제 요약·초록의 흔한 표기)
HEADINGS: dict[str, tuple[str, ...]] = {
    "objective": ("연구목적", "연구 목적", "연구목표", "연구 목표", "목적", "목표", "Objective"),
    "method": ("연구내용", "연구 내용", "연구방법", "연구 방법", "주요내용", "추진내용", "Method"),
    "scope": ("적용범위", "적용 범위", "연구범위", "연구 범위", "대상", "Scope"),
    "outcome": ("기대효과", "기대 효과", "활용계획", "활용 계획", "성과", "Results", "Conclusion"),
}
_HEAD = re.compile(r"^\s*[■◦○●□\-\*·\d\.\)\(]*\s*([가-힣A-Za-z ]{2,12})\s*[:：]?\s*(.*)$")
# 앞 기호와 목록 번호("1." "2)" "(3)")만 — "350km/h급" 같은 수치는 지우지 않는다
_LEAD_SYMBOLS = re.compile(r"^(?:[\s■□◦○●◎◆◇▶▷►•·※\-\*‣▪▫]+|\(?\d{1,2}[.)]\s+)+")
_INNER_SYMBOLS = re.compile(r"[■□◦○●◎◆◇▶▷►•※]+")
# LLM 이 원문에서 뽑은 칸: 칸 토큰 중 원문에 있는 비율 하한 — 원문 밖 내용을 막는다
MIN_SOURCE_OVERLAP = 0.6


def _cut(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_CELL_CHARS else text[: MAX_CELL_CHARS - 1] + "…"


def tidy_sentence(text: str) -> str:
    """앞 기호(■·◦·1.·- …)와 가운데 장식 기호를 지우고 공백을 정리한다."""
    text = _LEAD_SYMBOLS.sub("", " ".join((text or "").split()))
    return _INNER_SYMBOLS.sub(" ", text).strip(" ,;")


def clean_cell(sentences: Iterable[str], limit: int = MAX_CELL_CHARS) -> str:
    """온전한 문장 최대 2개를 상한 안에서 잇는다. 첫 문장 하나가 상한을 넘을 때만 어절 경계에서
    줄이고
    "…" 를 붙인다 (잘린 문장을 그대로 붙이지 않는다)."""
    picked: list[str] = []
    for raw in sentences:
        s = tidy_sentence(raw)
        if len(s) < 4:
            continue
        candidate = " ".join([*picked, s])
        if len(candidate) > limit:
            if not picked:
                cut = s[: limit - 1]
                cut = cut[: cut.rfind(" ")] if " " in cut else cut
                picked.append(cut.rstrip(" ,") + "…")
            break
        picked.append(s)
        if len(picked) >= CELL_MAX_SENTENCES:
            break
    return " ".join(picked)


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


def source_text(doc: Document | None) -> str:
    """기존 과제 칸의 원문 — 초록 또는 본문(요약)."""
    if doc is None:
        return ""
    return doc.abstract or doc.body or ""


def rule_cells(body: str) -> dict[str, str]:
    """규칙 추출 칸 {aspect: 글} — 머리말 아래 온전한 문장 1~2개. 머리말이 없으면 첫 문장들을
    연구목표에."""
    parts = section_sentences(body)
    if not parts:
        parts = {"objective": split_sentences(body)[:CELL_MAX_SENTENCES]}
    out: dict[str, str] = {}
    for key in CELL_KEYS:
        text = clean_cell(parts.get(key) or [])
        out[key] = text or NO_INFO
    return out


def _source_overlap(cell: str, source: str) -> float:
    cell_tokens = [t for t in tokens(cell) if len(t) >= 2]
    if not cell_tokens:
        return 0.0
    src = tokens(source)
    hit = sum(1 for t in cell_tokens if any(s.startswith(t) or t.startswith(s) for s in src))
    return hit / len(cell_tokens)


def cell_from_llm(value: Any, source: str) -> str | None:
    """LLM 이 원문에서 뽑은 칸 하나를 검증 — 통과하면 정리한 글, 빈 값이면 "", 어긋나면 None.

    원문 밖 수치·고유명, 한자·가나, 원문 토큰과 겹침이 적은 글(지어낸 요약)은 버린다 (보안 A)."""
    if not isinstance(value, str):
        return None
    text = clean_sentence(escape_untrusted(value)).replace("\n", " ").strip()
    if not text or text in (NO_INFO, "없음", "정보 없음", "-"):
        return ""
    text = clean_cell(split_sentences(text) or [text])
    if not text or has_foreign_script(text):
        return None
    if unsupported_numbers(text, [source]) or ungrounded(text, [source]):
        return None
    if _source_overlap(text, source) < MIN_SOURCE_OVERLAP:
        return None
    return text


def project_column(
    alert: OverlapAlert, doc: Document | None, extracted: Mapping[str, str] | None = None
) -> ComparisonColumn:
    body = source_text(doc)
    basis = alert.basis
    if doc is not None:
        basis = basis or doc.text_basis
    title_only = not body.strip()
    if title_only:
        cells = {k: NO_INFO_TITLE_ONLY for k in CELL_KEYS}
    else:
        cells = rule_cells(body)
        for key, value in (extracted or {}).items():
            if key in CELL_KEYS:
                cells[key] = value or NO_INFO
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


def proposal_column(
    req: ProposalRequest,
    differentiation: str = "",
    draft: Mapping[str, str] | None = None,
) -> ComparisonColumn:
    """제안 행 — 입력 칸에서: 가제(title_hint), 연구목표(goal), 연구방법(method — ② 과제안),
    적용범위
    (scope, 없으면 활용 주체·제약), 기대성과(초안 뒤), 차별화 방향. draft({aspect: 글}, 초안 섹션)가
    있으면 그 칸을 초안으로 바꾼다."""
    scope = req.scope or " ".join(x for x in (req.beneficiaries, req.constraints) if x).strip()
    direction = (differentiation or req.differentiation or "").strip()
    draft = {k: v for k, v in (draft or {}).items() if v and v.strip()}
    title = draft.get("title") or req.title_hint or PROPOSAL_NO_TITLE
    cells = {
        "objective": _cut(draft.get("objective") or req.goal) or NO_INFO,
        "method": _cut(draft.get("method") or req.method) or PROPOSAL_NO_METHOD,
        "scope": _cut(scope) or NO_INFO,
        "outcome": _cut(draft.get("outcome") or "") or PROPOSAL_NO_OUTCOME,
        "differentiation": _cut(direction) or PROPOSAL_NO_DIRECTION,
    }
    return ComparisonColumn(doc_id=None, title=title, cells=cells)


def draft_cells(sections: Iterable[Any]) -> dict[str, str]:
    """초안 섹션(Section: key·sentences[].text) → 제안 행 칸 {title·objective·method·outcome}."""
    by_key: dict[str, list[str]] = {}
    for sec in sections:
        texts = [s.text for s in getattr(sec, "sentences", []) if getattr(s, "text", "")]
        if texts:
            by_key[getattr(sec, "key", "")] = texts
    out: dict[str, str] = {}
    for aspect, keys in DRAFT_SECTIONS.items():
        texts = [t for k in keys for t in by_key.get(k, [])]
        if texts:
            out[aspect] = texts[0] if aspect == "title" else clean_cell(texts)
    return out


def comparison_table(
    req: ProposalRequest,
    alerts: Iterable[OverlapAlert],
    docs: Mapping[str, Document | None],
    *,
    differentiation: str = "",
    extracted: Mapping[str, Mapping[str, str]] | None = None,
    draft: Mapping[str, str] | None = None,
    empty_reason: str | None = None,
) -> ComparisonTable:
    ranked = sorted(alerts, key=lambda a: (-a.similarity, a.doc_id))
    seen: set[str] = set()
    projects: list[ComparisonColumn] = []
    for alert in ranked:
        if alert.doc_id in seen:
            continue
        seen.add(alert.doc_id)
        projects.append(
            project_column(alert, docs.get(alert.doc_id), (extracted or {}).get(alert.doc_id))
        )
        if len(projects) >= MAX_PROJECTS:
            break
    return ComparisonTable(
        proposal=proposal_column(req, differentiation, draft),
        projects=projects,
        empty_reason=empty_reason if not projects else None,
        proposal_source="draft" if draft else "input",
    )
