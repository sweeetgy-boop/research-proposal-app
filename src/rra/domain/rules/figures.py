"""그림(인포그래픽) 규칙 — 순수 함수 ([G] 2026-10-28, architecture §4.16).

- `text_pool`: 명세에 쓸 수 있는 글자·수치의 출처 = 초안 본문 + 제안자 입력 + 근거 청크 + 검증된
  table_facts.
- `validate_spec`: 명세의 모든 글자가 pool 에 있는지(고정 라벨·"정보 없음"·"목표치 확인 필요" 는
  허용),
  모든 수치가 pool 의 수치와 같은지, stat_chart 는 출처 문서의 table_facts 값만 쓰는지, schedule 은
  연구기간 안인지 검사한다. 위반은 코드 목록 — 하나라도 있으면 명세를 폐기한다(그리지 않는다).
- `choose_default`: 초안·입력에서 기본으로 그릴 (종류, 섹션) 2~3개.
- `texts_of`·`alt_text`·`image_prompt`: 명세의 글자 목록, 대체 텍스트, Nano Banana Pro 프롬프트.
- `figure_diff`: 두 버전의 그림 목록 차이 (버전 비교 화면).
- `apply_text_edits`: [글자 고치기] 폼 값(경로 → 글자)을 명세에 반영.
- `internal_only_texts`: 공용 계정용 — internal 근거에서만 나온 글자 목록(명세를 폐기하거나 뺀다).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from rra.domain.models.draft import Section
from rra.domain.models.figure import (
    FIGURE_KINDS,
    KIND_LABEL,
    KIND_SECTION,
    ComparisonSpec,
    ConceptSpec,
    Figure,
    ProcessSpec,
    RoadmapSpec,
    ScheduleSpec,
    StatChartSpec,
    parse_spec,
)
from rra.domain.models.request import ProposalRequest
from rra.domain.models.table_fact import TableFact
from rra.domain.rules.numbers import numbers
from rra.domain.rules.schedule import TARGET_UNKNOWN, research_period_months

NO_INFO = "정보 없음"
# 명세에 항상 허용되는 고정 글자 (템플릿 라벨·안내문)
FIXED_TEXTS: frozenset[str] = frozenset(
    {
        NO_INFO,
        TARGET_UNKNOWN,
        "현황",
        "문제",
        "근본 원인",
        "해결 방안",
        "기대효과",
        "연구목표",
        "연구방법",
        "적용범위",
        "기대성과",
        "차별화 방향",
        "제안 과제",
        "기존 과제",
        "성과지표",
        "목표치",
        "활용 단계",
        "단계",
        "산출물",
        "개월",
        "연도",
        "현재",
        "제안",
    }
)
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
_SPACES = re.compile(r"\s+")
# 위반 코드
TEXT_NOT_IN_SOURCES = "figure_text_not_in_sources"
NUMBER_NOT_IN_SOURCES = "figure_number_not_in_sources"
FACT_NOT_FOUND = "figure_fact_not_found"
SCHEDULE_EXCEEDS = "figure_schedule_exceeds_period"
SOURCE_MISSING = "figure_source_missing"


def _norm(text: str) -> str:
    return _SPACES.sub("", (text or "")).casefold()


@dataclass(frozen=True)
class TextPool:
    """명세 검사용 — 합친 본문(공백 제거)·단어 집합·수치 집합·문서별 facts."""

    text: str
    words: frozenset[str]
    nums: frozenset[tuple]
    facts: Mapping[str, Sequence[TableFact]] = field(default_factory=dict)
    internal_text: str = ""  # internal 근거에서만 온 본문 (공용 계정 제외용)

    def has_text(self, value: str) -> bool:
        """문장 그대로 있거나, 내용 단어(2자 이상)가 모두 있으면 통과."""
        v = _norm(value)
        if not v or value in FIXED_TEXTS:
            return True
        if v in self.text:
            return True
        words = [w.casefold() for w in _WORD.findall(value) if len(w) >= 2]
        return bool(words) and all(w in self.words or w in self.text for w in words)

    def has_number(self, canonical: tuple) -> bool:
        return canonical in self.nums


def text_pool(
    sections: Sequence[Section],
    request: ProposalRequest | None,
    chunk_texts: Iterable[str] = (),
    facts: Mapping[str, Sequence[TableFact]] | None = None,
    *,
    internal_chunk_texts: Iterable[str] = (),
) -> TextPool:
    parts: list[str] = [s.text for s in sections]
    if request is not None:
        parts.extend(str(v) for v in request.prompt_view().values() if isinstance(v, str))
    parts.extend(chunk_texts)
    internal = list(internal_chunk_texts)
    parts.extend(internal)
    for items in (facts or {}).values():
        for f in items:
            parts.append(f.as_text())
            parts.append(f"{f.item} {f.value_text}{f.unit or ''}")
    joined = "\n".join(parts)
    words = {w.casefold() for w in _WORD.findall(joined)}
    nums = {c for _, c in numbers(joined)}
    for items in (facts or {}).values():
        for f in items:
            for _, c in numbers(f"{f.value_text}{f.unit or ''}"):
                nums.add(c)
            for _, c in numbers(str(f.value)):
                nums.add(c)
    return TextPool(
        text=_norm(joined),
        words=frozenset(words),
        nums=frozenset(nums),
        facts=dict(facts or {}),
        internal_text=_norm("\n".join(internal)),
    )


# ── 글자 목록 ────────────────────────────────────────────
def texts_of(spec: BaseModel) -> list[str]:
    """명세에 그려질 글자 전부(순서 유지, 중복 제거). 검사·프롬프트·대체 텍스트에 쓴다."""
    out: list[str] = []
    if isinstance(spec, ConceptSpec):
        for b in spec.boxes:
            out.append(b.label)
            out.extend(b.lines)
    elif isinstance(spec, ProcessSpec):
        for s in spec.stages:
            out.append(s.name)
            out.extend(s.outputs)
    elif isinstance(spec, ScheduleSpec):
        out.extend(s.name for s in spec.stages)
        out.extend(f"{s.start_month}~{s.end_month}개월" for s in spec.stages)
    elif isinstance(spec, StatChartSpec):
        out.append(spec.title)
        out.extend(spec.categories)
        out.extend(s.name for s in spec.series)
        out.extend(spec.value_texts)
        if spec.unit:
            out.append(spec.unit)
        out.append(spec.source.caption())
    elif isinstance(spec, ComparisonSpec):
        out.extend(spec.aspects)
        for p in [*spec.projects, spec.proposal]:
            out.append(p.title)
            out.extend(v for v in p.cells.values() if v)
    elif isinstance(spec, RoadmapSpec):
        for m in spec.metrics:
            out.extend([m.name, m.target])
        for s in spec.stages:
            out.append(s.name)
            if s.desc:
                out.append(s.desc)
    seen: dict[str, None] = {}
    for t in out:
        if t and t not in seen:
            seen[t] = None
    return list(seen)


def alt_text(spec: BaseModel) -> str:
    """대체 텍스트 — 명세를 한 문단으로."""
    label = KIND_LABEL.get(getattr(spec, "kind", ""), "그림")
    if isinstance(spec, ConceptSpec):
        body = " → ".join(
            b.label + (f"({' / '.join(b.lines)})" if b.lines else "") for b in spec.boxes
        )
    elif isinstance(spec, ProcessSpec):
        body = " → ".join(
            s.name + (f"(산출물: {', '.join(s.outputs)})" if s.outputs else "") for s in spec.stages
        )
    elif isinstance(spec, ScheduleSpec):
        body = f"총 {spec.total_months}개월. " + ", ".join(
            f"{s.name} {s.start_month}~{s.end_month}개월" for s in spec.stages
        )
    elif isinstance(spec, StatChartSpec):
        rows = []
        for s in spec.series:
            pairs = ", ".join(
                f"{c} {v:g}{spec.unit}" for c, v in zip(spec.categories, s.values, strict=False)
            )
            rows.append(f"{s.name}: {pairs}")
        body = f"{spec.title}. " + "; ".join(rows) + f". {spec.source.caption()}"
    elif isinstance(spec, ComparisonSpec):
        cols = [*spec.projects, spec.proposal]
        body = "; ".join(
            f"{c.title}: " + ", ".join(f"{a} {c.cells.get(a) or NO_INFO}" for a in spec.aspects)
            for c in cols
        )
    elif isinstance(spec, RoadmapSpec):
        body = (
            "성과지표 "
            + ", ".join(f"{m.name} {m.target}" for m in spec.metrics)
            + "; 활용 단계 "
            + " → ".join(s.name + (f"({s.desc})" if s.desc else "") for s in spec.stages)
        )
    else:
        body = ""
    return f"{label}: {body}"[:600]


# ── 검사 ─────────────────────────────────────────────────
def validate_spec(
    spec: BaseModel,
    pool: TextPool,
    *,
    period_months: int | None = None,
) -> list[str]:
    """위반 코드 목록(중복 제거). 비어 있으면 통과."""
    problems: list[str] = []
    texts = texts_of(spec)
    for t in texts:
        if isinstance(spec, ScheduleSpec) and t.endswith("개월"):
            continue  # 일정 숫자는 아래 기간 검사로
        if isinstance(spec, StatChartSpec) and t == spec.source.caption():
            continue  # 출처 캡션은 문서 메타
        if not pool.has_text(t):
            problems.append(TEXT_NOT_IN_SOURCES)
            break
    if isinstance(spec, StatChartSpec):
        facts = pool.facts.get(spec.source.doc_id) or []
        if not facts:
            problems.append(SOURCE_MISSING)
        values = {Decimal(str(f.value)) for f in facts}
        value_texts = {f.value_text for f in facts}
        for s in spec.series:
            for v in s.values:
                if Decimal(str(v)) not in values:
                    problems.append(FACT_NOT_FOUND)
                    break
        for vt in spec.value_texts:
            if vt not in value_texts:
                problems.append(FACT_NOT_FOUND)
                break
    elif isinstance(spec, ScheduleSpec):
        if period_months is None or spec.total_months > period_months:
            problems.append(SCHEDULE_EXCEEDS)
        elif any(s.end_month > period_months for s in spec.stages):
            problems.append(SCHEDULE_EXCEEDS)
    else:
        for t in texts:
            if t in FIXED_TEXTS:
                continue
            for _, canonical in numbers(t):
                if not pool.has_number(canonical):
                    problems.append(NUMBER_NOT_IN_SOURCES)
                    break
            if NUMBER_NOT_IN_SOURCES in problems:
                break
    return list(dict.fromkeys(problems))


def missing_texts(spec: BaseModel, pool: TextPool, *, limit: int = 5) -> list[str]:
    """출처(pool)에 없는 글자·수치가 든 명세 글자 — 교정 재요청에 알려 준다(최대 limit 개)."""
    out: list[str] = []
    for t in texts_of(spec):
        if t in FIXED_TEXTS:
            continue
        if isinstance(spec, ScheduleSpec) and t.endswith("개월"):
            continue
        if isinstance(spec, StatChartSpec) and t == spec.source.caption():
            continue
        bad_number = any(not pool.has_number(c) for _, c in numbers(t))
        if not pool.has_text(t) or (not isinstance(spec, StatChartSpec) and bad_number):
            out.append(t)
        if len(out) >= limit:
            break
    return out


def internal_only_texts(spec: BaseModel, pool: TextPool) -> list[str]:
    """internal 근거에만 있고(공개 본문·입력에는 없는) 글자 — 공용 계정이면 명세에서 뺀다."""
    if not pool.internal_text:
        return []
    public = pool.text.replace(pool.internal_text, "")
    out = []
    for t in texts_of(spec):
        v = _norm(t)
        if v and v in pool.internal_text and v not in public and t not in FIXED_TEXTS:
            out.append(t)
    return out


# ── 기본 선택 ─────────────────────────────────────────────
def choose_default(
    sections: Sequence[Section],
    request: ProposalRequest | None,
    *,
    max_default: int = 3,
    has_facts: bool = False,
    has_overlap: bool = False,
    kinds: Sequence[str] = FIGURE_KINDS,
) -> list[tuple[str, str]]:
    """(종류, 섹션) 목록 — 섹션에 문장이 있을 때만. 우선순위: 개념도 → 체계도 → 수치 그래프(facts
    있을 때) → 일정표(연구기간 있을 때) → 로드맵 → 비교(유사과제 있을 때)."""
    present = {s.key for s in sections if s.sentences}
    period = research_period_months(request.constraints) if request else None
    order: list[tuple[str, bool]] = [
        ("concept", "objective" in present),
        ("process", "method" in present),
        ("stat_chart", has_facts and "tech_importance" in present),
        ("schedule", period is not None and "method" in present),
        ("roadmap", any(k in present for k in ("expected_technology", "expected_management"))),
        ("comparison", has_overlap and "tech_importance" in present),
    ]
    out = [(k, KIND_SECTION[k]) for k, ok in order if ok and k in kinds]
    return out[: max(0, int(max_default))]


# ── 프롬프트 ─────────────────────────────────────────────
def image_prompt(spec: BaseModel, *, caption: str = "") -> str:
    """Nano Banana Pro 프롬프트 — 배치·순서 유지, 글자 목록 그대로, 금지 목록. 명세 글자만
    보낸다."""
    label = KIND_LABEL.get(getattr(spec, "kind", ""), "그림")
    layout = _layout_hint(spec)
    lines = [
        f"공공기관 연구과제 제안서에 넣을 깔끔한 인포그래픽({label})을 그려라.",
        "흰 배경, 보고서용 단정한 도형, 흑백 인쇄에서도 구분되는 색(명도 차와 선 모양).",
        "참고 이미지의 배치·순서·화살표 방향·막대 길이와 기간 비율을 그대로 유지하라.",
        "아래 글자 목록의 글자를 한 글자도 바꾸지 말고 그대로 써라. "
        "목록에 없는 글자·숫자·로고·사람 얼굴·실제 기관 상표는 넣지 마라.",
        layout,
        "글자 목록:",
        *[f"- {t}" for t in texts_of(spec)],
    ]
    if caption:
        lines.append(f"그림 제목(그림 안에 넣지 않는다): {caption}")
    return "\n".join(x for x in lines if x)


def edit_prompt(request: str, texts: Sequence[str] = ()) -> str:
    """[말로 고치기] — 현재 그림을 입력으로 넣고 제안자 요청만 반영. 명세 글자 목록을 함께 넣어
    다시 그릴 때 글자가 바뀌지 않게 한다(2026-10-28 실측: 목록 없이 편집하면 "상태→샹태" 변형)."""
    lines = [
        "첨부한 그림을 아래 요청대로만 고쳐라. 요청에 없는 부분(배치·글자·색)은 그대로 두고, "
        "새 글자·숫자·로고·사람 얼굴·실제 기관 상표를 넣지 마라. 흰 배경을 유지하라.",
        f"요청: {request.strip()}",
    ]
    if texts:
        lines.append(
            "그림 속 글자는 아래 목록과 한 글자도 다르지 않게 유지하라(맞춤법을 고치지 마라):"
        )
        lines.extend(f"- {t}" for t in texts)
    return "\n".join(lines)


def _layout_hint(spec: BaseModel) -> str:
    if isinstance(spec, ConceptSpec):
        return (
            "배치: 상자 4개를 왼쪽에서 오른쪽으로 화살표로 잇는다 "
            "(현황 → 문제 → 해결 방안 → 기대효과)."
        )
    if isinstance(spec, ProcessSpec):
        return (
            f"배치: 단계 상자 {len(spec.stages)}개를 왼쪽에서 오른쪽으로 화살표로 잇고, "
            "상자 아래에 산출물을 적는다."
        )
    if isinstance(spec, ScheduleSpec):
        return (
            f"배치: 간트 차트. 가로축 1~{spec.total_months}개월, 단계마다 가로 막대 하나. "
            "막대 길이 비율을 지켜라."
        )
    if isinstance(spec, StatChartSpec):
        kind = "막대 그래프" if spec.chart == "bar" else "꺾은선 그래프"
        return (
            f"배치: {kind}. 가로축 {len(spec.categories)}개 구분, 값 글자를 막대 위에 표시. "
            "값 비율을 지켜라."
        )
    if isinstance(spec, ComparisonSpec):
        return (
            f"배치: 표. 행은 비교 항목 {len(spec.aspects)}개, 열은 기존 과제 "
            f"{len(spec.projects)}개와 제안 과제(마지막 열 강조)."
        )
    if isinstance(spec, RoadmapSpec):
        return "배치: 위쪽에 성과지표 상자들, 아래쪽에 활용 단계를 왼쪽에서 오른쪽 화살표로."
    return ""


# ── 버전 비교·편집 ─────────────────────────────────────────
def figure_diff(old: Sequence[Figure], new: Sequence[Figure]) -> list[dict[str, Any]]:
    """[{figure_id, kind, section, change}] — added | removed | redrawn | texts | included |
    excluded | confirmed | baseline."""
    before = {f.id: f for f in old}
    after = {f.id: f for f in new}
    out: list[dict[str, Any]] = []
    for fid, f in after.items():
        o = before.get(fid)
        if o is None:
            out.append(_row(f, "added"))
            continue
        if o.spec.model_dump() != f.spec.model_dump():
            out.append(_row(f, "texts"))
        elif o.image_sha != f.image_sha:
            out.append(_row(f, "baseline" if f.renderer == "baseline" else "redrawn"))
        if o.included != f.included:
            out.append(_row(f, "included" if f.included else "excluded"))
        if o.confirmed != f.confirmed and f.confirmed:
            out.append(_row(f, "confirmed"))
    for fid, o in before.items():
        if fid not in after:
            out.append(_row(o, "removed"))
    return out


def _row(f: Figure, change: str) -> dict[str, Any]:
    return {"figure_id": f.id, "kind": f.kind, "section": f.section, "change": change}


def editable_texts(spec: BaseModel) -> list[dict[str, str]]:
    """[글자 고치기] 폼 — [{path, label, value}]. path 는 model_dump 경로('boxes.0.label')."""
    rows: list[dict[str, str]] = []
    if isinstance(spec, ConceptSpec):
        for i, b in enumerate(spec.boxes):
            rows.append(
                {"path": f"boxes.{i}.label", "label": f"상자 {i + 1} 제목", "value": b.label}
            )
            for j, line in enumerate(b.lines):
                rows.append(
                    {
                        "path": f"boxes.{i}.lines.{j}",
                        "label": f"상자 {i + 1} 줄 {j + 1}",
                        "value": line,
                    }
                )
    elif isinstance(spec, ProcessSpec):
        for i, s in enumerate(spec.stages):
            rows.append({"path": f"stages.{i}.name", "label": f"단계 {i + 1}", "value": s.name})
            for j, o in enumerate(s.outputs):
                rows.append(
                    {
                        "path": f"stages.{i}.outputs.{j}",
                        "label": f"단계 {i + 1} 산출물 {j + 1}",
                        "value": o,
                    }
                )
    elif isinstance(spec, ScheduleSpec):
        for i, s in enumerate(spec.stages):
            rows.append({"path": f"stages.{i}.name", "label": f"단계 {i + 1}", "value": s.name})
    elif isinstance(spec, StatChartSpec):
        rows.append({"path": "title", "label": "제목", "value": spec.title})
        for i, c in enumerate(spec.categories):
            rows.append({"path": f"categories.{i}", "label": f"구분 {i + 1}", "value": c})
        for i, s in enumerate(spec.series):
            rows.append({"path": f"series.{i}.name", "label": f"계열 {i + 1}", "value": s.name})
    elif isinstance(spec, ComparisonSpec):
        for i, a in enumerate(spec.aspects):
            rows.append({"path": f"aspects.{i}", "label": f"항목 {i + 1}", "value": a})
        for i, p in enumerate(spec.projects):
            rows.append(
                {"path": f"projects.{i}.title", "label": f"기존 과제 {i + 1}", "value": p.title}
            )
            for a, v in p.cells.items():
                rows.append(
                    {
                        "path": f"projects.{i}.cells.{a}",
                        "label": f"기존 과제 {i + 1} · {a}",
                        "value": v,
                    }
                )
        rows.append({"path": "proposal.title", "label": "제안 과제", "value": spec.proposal.title})
        for a, v in spec.proposal.cells.items():
            rows.append({"path": f"proposal.cells.{a}", "label": f"제안 과제 · {a}", "value": v})
    elif isinstance(spec, RoadmapSpec):
        for i, m in enumerate(spec.metrics):
            rows.append({"path": f"metrics.{i}.name", "label": f"지표 {i + 1}", "value": m.name})
            rows.append(
                {"path": f"metrics.{i}.target", "label": f"지표 {i + 1} 목표치", "value": m.target}
            )
        for i, s in enumerate(spec.stages):
            rows.append(
                {"path": f"stages.{i}.name", "label": f"활용 단계 {i + 1}", "value": s.name}
            )
            if s.desc:
                rows.append(
                    {
                        "path": f"stages.{i}.desc",
                        "label": f"활용 단계 {i + 1} 설명",
                        "value": s.desc,
                    }
                )
    return rows


def apply_text_edits(spec: BaseModel, edits: Mapping[str, str]) -> BaseModel:
    """폼 값(path → 글자)을 반영한 새 명세. 허용된 경로(editable_texts)만, 빈 값은 무시.
    검증 실패면 ValueError."""
    allowed = {r["path"] for r in editable_texts(spec)}
    data = spec.model_dump()
    for path, value in edits.items():
        if path not in allowed or not isinstance(value, str) or not value.strip():
            continue
        _set_path(data, path.split("."), value.strip())
    try:
        return parse_spec(str(data.get("kind")), data)
    except ValueError as exc:
        raise ValueError("고친 글자가 명세 형식에 맞지 않습니다 (길이·개수).") from exc


def _set_path(node: Any, parts: list[str], value: str) -> None:
    head, rest = parts[0], parts[1:]
    key: Any = int(head) if isinstance(node, list) else head
    if not rest:
        node[key] = value
        return
    _set_path(node[key], rest, value)


def next_figure_id(section: str, existing: Iterable[str]) -> str:
    taken = set(existing)
    n = 1
    while f"f:{section}:{n}" in taken:
        n += 1
    return f"f:{section}:{n}"


def unconfirmed(figures: Iterable[Figure]) -> list[Figure]:
    return [f for f in figures if f.included and not f.confirmed]
