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
- `spec_change_summary`: 명세 두 개의 "바뀐 내용" 한 줄씩 (카드 표시, [2] 말로 고치기).
- `with_texts`: 이미 받아들인 글자(현재 명세·제안자 요청)를 pool 에 더한다 — [말로 고치기] 검사용.
- `internal_only_texts`: 공용 계정용 — internal 근거에서만 나온 글자 목록(명세를 폐기하거나 뺀다).
- v2(2026-10-28, ADR 0033): `choose_default` = As-Is/To-Be 1 (+ 검증 수치 그래프·
  일정표), 분석 기법은 `technique_slots` 만큼(0~2) — 합쳐 최대 4장. 개념도·체계도·로드맵·
  비교는 [다른 그림 추가]에서만. `image_prompt` 는 "밑그림 배치 그대로" 대신 인포그래픽
  (색 강조·아이콘·제목 계층·여백)을 새로 디자인하게 하고 글자는 목록 그대로. 비율은
  `choose_aspect`(내용 양). 상자 글자는 `MAX_BOX`(1~2줄).
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from rra.domain.models.draft import Section
from rra.domain.models.figure import (
    AS_IS_TAGS,
    FIGURE_KINDS,
    KIND_LABEL,
    MAX_BOX,
    MAX_CHANGE_LINE,
    MAX_CHANGE_LINES,
    MAX_LABEL,
    MAX_LINE,
    NEED_CALC,
    PRELIM_NOTE,
    TO_BE_TAGS,
    AsIsToBeSpec,
    ComparisonSpec,
    ConceptSpec,
    Figure,
    ProcessSpec,
    RoadmapSpec,
    ScheduleSpec,
    StatChartSpec,
    TechniqueSpec,
    parse_spec,
)
from rra.domain.models.request import ProposalRequest
from rra.domain.models.table_fact import TableFact
from rra.domain.rules.numbers import numbers
from rra.domain.rules.schedule import TARGET_UNKNOWN, research_period_months
from rra.domain.rules.techniques import LEVELS, PM, technique_texts

NO_INFO = "정보 없음"
AS_IS_HEAD = "As-Is (현재)"
TO_BE_HEAD = "To-Be (연구 후)"
# 개념도 상자 이름은 템플릿 라벨 — 자리별로 고정한다. 모델이 "문제(근본 원인)" 처럼 지시문 라벨을
# 그대로 쓰면 근거 밖 글자로 걸러져 개념도가 빠졌다 (2026-10-28 배포 시험 3회차)
CONCEPT_LABELS: tuple[str, ...] = ("현황", "문제(근본 원인)", "해결 방안", "기대효과")
# 명세에 항상 허용되는 고정 글자 (템플릿 라벨·안내문)
FIXED_TEXTS: frozenset[str] = frozenset(
    {
        NO_INFO,
        TARGET_UNKNOWN,
        "현황",
        "문제",
        "근본 원인",
        "문제(근본 원인)",
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
        AS_IS_HEAD,
        TO_BE_HEAD,
        *AS_IS_TAGS,
        *TO_BE_TAGS,
        NEED_CALC,
        PRELIM_NOTE,
        *LEVELS,
        *PM,
    }
)
# v2 기본 그림 — 이 종류만 초안 뒤 자동으로 (분석 기법은 따로 추천). 나머지는 [다른 그림 추가]에서만
AUTO_KINDS: tuple[str, ...] = ("as_is_to_be", "stat_chart", "schedule")
MAX_FIGURES = 4  # 초안 1건 기본 그림 상한 (기법 추천 포함)
MAX_TECHNIQUES = 2
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
_SPACES = re.compile(r"\s+")
# 위반 코드
TEXT_NOT_IN_SOURCES = "figure_text_not_in_sources"
NUMBER_NOT_IN_SOURCES = "figure_number_not_in_sources"
FACT_NOT_FOUND = "figure_fact_not_found"
SCHEDULE_EXCEEDS = "figure_schedule_exceeds_period"
SOURCE_MISSING = "figure_source_missing"
BOX_EMPTY = "figure_box_empty"  # 개념도 상자에 근거 있는 줄이 하나도 없다 (다듬은 뒤)
# As-Is/To-Be 칸 이름이 정해진 이름(현황·원인·한계 / 목표·해결 방안·기대효과)이 아님
SIDE_TAG = "figure_side_tag"


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
    # 초안 본문·제안자 입력의 수치만 — 계획 그림(개념도·체계도·로드맵 등)의 연도는 여기서만 찾는다.
    # 근거 자료의 연도(2024년 보고서 등)는 과거 사실이라 계획 연도로 쓰지 않는다 (10-28 배포 시험)
    plan_nums: frozenset[tuple] = frozenset()

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
    plan_parts = [s.text for s in sections]
    if request is not None:
        plan_parts.extend(str(v) for v in request.prompt_view().values() if isinstance(v, str))
    plan_nums = {c for _, c in numbers("\n".join(plan_parts))}
    return TextPool(
        text=_norm(joined),
        words=frozenset(words),
        nums=frozenset(nums),
        facts=dict(facts or {}),
        internal_text=_norm("\n".join(internal)),
        plan_nums=frozenset(plan_nums),
    )


def with_texts(pool: TextPool, texts: Iterable[str]) -> TextPool:
    """제안자 쪽 글자(현재 명세·[말로 고치기] 요청 원문)를 출처로 더한 pool. [글자 고치기]가 제안자
    글자를 그대로 받듯, 말로 고친 명세도 제안자가 적은 글자는 통과한다. 수치는 계획 수치로 친다."""
    extra = "\n".join(t for t in texts if t)
    if not extra:
        return pool
    words = {w.casefold() for w in _WORD.findall(extra)}
    nums = {c for _, c in numbers(extra)}
    return replace(
        pool,
        text=pool.text + "\n" + _norm(extra),
        words=pool.words | words,
        nums=pool.nums | nums,
        plan_nums=pool.plan_nums | nums,
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
    elif isinstance(spec, AsIsToBeSpec):
        out.append(AS_IS_HEAD)
        for it in spec.as_is:
            out.extend([it.tag, it.text])
        out.append(spec.solution)
        out.append(TO_BE_HEAD)
        for it in spec.to_be:
            out.extend([it.tag, it.text])
    elif isinstance(spec, TechniqueSpec):
        out.extend(technique_texts(spec))
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
    elif isinstance(spec, AsIsToBeSpec):
        body = (
            "현재 "
            + ", ".join(f"{it.tag} {it.text}" for it in spec.as_is)
            + f" → {spec.solution} → 연구 후 "
            + ", ".join(f"{it.tag} {it.text}" for it in spec.to_be)
        )
    elif isinstance(spec, TechniqueSpec):
        label = spec.title
        if spec.rows:
            body = "; ".join(
                f"{r.name}: "
                + ", ".join(f"{c} {v}" for c, v in zip(spec.columns, r.cells, strict=False))
                for r in spec.rows
            )
        else:
            body = "; ".join(
                f"{g.name}: "
                + ", ".join(
                    it.text
                    + (f"({it.rating})" if it.rating else "")
                    + (f" {it.amount}" if it.amount else "")
                    for it in g.items
                )
                for g in spec.groups
            )
        body = f"{body}. {spec.note}"
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
    if isinstance(spec, ConceptSpec) and any(not b.lines for b in spec.boxes):
        problems.append(BOX_EMPTY)
    if isinstance(spec, AsIsToBeSpec) and (
        any(it.tag not in AS_IS_TAGS for it in spec.as_is)
        or any(it.tag not in TO_BE_TAGS for it in spec.to_be)
    ):
        problems.append(SIDE_TAG)
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
                is_year = canonical[0] == "year"
                if not pool.has_number(canonical) or (is_year and canonical not in pool.plan_nums):
                    problems.append(NUMBER_NOT_IN_SOURCES)
                    break
            if NUMBER_NOT_IN_SOURCES in problems:
                break
    return list(dict.fromkeys(problems))


# ── 명세 다듬기 (버리기 전에) ─────────────────────────────────
_LABEL_KEYS = frozenset({"label", "name", "title", "tag"})
# v2 [4] 상자 글자 — 1~2줄(MAX_BOX). 새 명세만 줄인다(저장된 명세는 그대로 읽힌다)
_BOX_KEYS = frozenset({"text", "solution", "target", "desc"})
_BOX_LISTS = frozenset({"lines", "outputs"})
_LIST_LIMITS = {
    "lines": 2,
    "outputs": 3,
    "stages": 6,
    "metrics": 6,
    "series": 4,
    "aspects": 5,
    "projects": 3,
    "as_is": 4,
    "to_be": 4,
}


def clip_text(text: str, limit: int) -> str:
    """limit 자를 넘으면 단어 경계(공백·쉼표)에서 자른다 — 앞부분이 원문 그대로라 출처 검사를
    통과한다."""
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    cut = value[:limit]
    for sep in (" ", ",", "·"):
        i = cut.rfind(sep)
        if i >= limit // 2:
            return cut[:i].rstrip(" ,·")
    return cut


def normalize_spec_data(data: Any) -> Any:
    """모델 응답(JSON) → 스키마 상한 안으로: 상자·단계 이름 40자, 그 밖 60자에서 자르고 목록은
    상한 개수까지. (7B 가 초안 문장을 통째로 옮겨 60자를 넘기면 형식 오류로 그림 전체가 빠졌다
    — 2026-10-28 배포 시험)"""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                limit = (
                    MAX_LABEL if key in _LABEL_KEYS else MAX_BOX if key in _BOX_KEYS else MAX_LINE
                )
                out[key] = clip_text(value, limit)
            elif isinstance(value, list):
                items = [normalize_spec_data(v) for v in value]
                if key in _LIST_LIMITS:
                    items = items[: _LIST_LIMITS[key]]
                out[key] = [
                    clip_text(v, MAX_BOX) if isinstance(v, str) and key in _BOX_LISTS else v
                    for v in items
                ]
            else:
                out[key] = normalize_spec_data(value)
        return out
    if isinstance(data, list):
        return [normalize_spec_data(v) for v in data]
    return data


def repair_spec(spec: BaseModel, pool: TextPool) -> BaseModel:
    """출처에 없는 **선택 글자**만 덜어 낸다 — 버리기 전에 한 번. 필수 글자(상자·단계·지표 이름)는
    그대로 두므로 그것이 출처에 없으면 validate_spec 이 여전히 거부한다.
    - roadmap: 근거 없는 목표치 → "목표치 확인 필요", 근거 없는 단계 설명 → 없음
    - concept: 근거 없는 설명 줄 → 뺌 / process: 근거 없는 산출물 → 뺌
    - comparison: 근거 없는 칸 → "정보 없음"
    stat_chart·schedule 은 손대지 않는다(값·기간은 고쳐 쓰지 않는다)."""

    def ok(text: str) -> bool:
        if not pool.has_text(text):
            return False
        for _, c in numbers(text):
            if not pool.has_number(c) or (c[0] == "year" and c not in pool.plan_nums):
                return False
        return True

    if isinstance(spec, RoadmapSpec):
        metrics = [
            m.model_copy(update={"target": m.target if ok(m.target) else TARGET_UNKNOWN})
            for m in spec.metrics
        ]
        stages = [
            s.model_copy(update={"desc": s.desc if s.desc and ok(s.desc) else None})
            for s in spec.stages
        ]
        return spec.model_copy(update={"metrics": metrics, "stages": stages})
    if isinstance(spec, ConceptSpec):
        boxes = [
            b.model_copy(
                update={"label": CONCEPT_LABELS[i], "lines": [x for x in b.lines if ok(x)]}
            )
            for i, b in enumerate(spec.boxes)
        ]
        return spec.model_copy(update={"boxes": boxes})
    if isinstance(spec, ProcessSpec):
        stages = [
            s.model_copy(update={"outputs": [x for x in s.outputs if ok(x)]}) for s in spec.stages
        ]
        return spec.model_copy(update={"stages": stages})
    if isinstance(spec, AsIsToBeSpec):

        def side(items, tags):
            fixed = [
                it.model_copy(
                    update={"tag": it.tag if it.tag in tags else tags[min(i, len(tags) - 1)]}
                )
                for i, it in enumerate(items)
            ]
            kept = [it for it in fixed if ok(it.text)]
            return kept if len(kept) >= 3 else fixed  # 3칸 미만이면 그대로 — 검사가 거절한다

        return spec.model_copy(
            update={"as_is": side(spec.as_is, AS_IS_TAGS), "to_be": side(spec.to_be, TO_BE_TAGS)}
        )
    if isinstance(spec, ComparisonSpec):

        def cells(p):
            return p.model_copy(
                update={"cells": {a: (v if ok(v) else NO_INFO) for a, v in p.cells.items()}}
            )

        return spec.model_copy(
            update={"projects": [cells(p) for p in spec.projects], "proposal": cells(spec.proposal)}
        )
    return spec


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
        bad_number = any(
            not pool.has_number(c) or (c[0] == "year" and c not in pool.plan_nums)
            for _, c in numbers(t)
        )
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
    auto_kinds: Sequence[str] = AUTO_KINDS,
) -> list[tuple[str, str]]:
    """(종류, 섹션) 목록 — v2 기본(auto_kinds): As-Is/To-Be(연구목적, 비면 기술적 중요도) →
    수치 그래프(검증 수치가 있을 때) → 일정표(연구기간이 있을 때). 개념도·체계도·로드맵·비교는
    자동으로 넣지 않는다 — 글자가 작고 본문을 되풀이했다(10-28 시범). figures.yaml auto_kinds 로
    다시 켤 수 있다(우선순위는 아래 order). 분석 기법(0~2)은 `technique_slots` 로 따로 채운다."""
    present = {s.key for s in sections if s.sentences}
    period = research_period_months(request.constraints) if request else None
    as_is_section = next((k for k in ("objective", "tech_importance") if k in present), None)
    expected = any(k in present for k in ("expected_technology", "expected_management"))
    order: list[tuple[str, str | None]] = [
        ("as_is_to_be", as_is_section),
        ("concept", "objective" if "objective" in present else None),
        ("process", "method" if "method" in present else None),
        ("stat_chart", "tech_importance" if has_facts and "tech_importance" in present else None),
        ("schedule", "method" if period is not None and "method" in present else None),
        ("roadmap", "expected_technology" if expected else None),
        ("comparison", "tech_importance" if has_overlap and "tech_importance" in present else None),
    ]
    auto = set(auto_kinds)
    out = [(k, sec) for k, sec in order if sec and k in kinds and k in auto]
    return out[: max(0, min(int(max_default), MAX_FIGURES))]


def technique_slots(planned: int, *, max_total: int = MAX_FIGURES) -> int:
    """기본 그림 planned 장 뒤에 남는 분석 기법 자리 (0~2)."""
    return max(0, min(MAX_TECHNIQUES, int(max_total) - int(planned)))


# ── 프롬프트 ─────────────────────────────────────────────
# 종류별 색 — 흑백 인쇄 구분은 명도·무늬·테두리로 함께 (프롬프트 [디자인])
_PALETTE_HINT: dict[str, str] = {
    "as_is_to_be": (
        "왼쪽 As-Is(현재)는 회색·주황 계열(문제 강조는 주황), 오른쪽 To-Be(연구 후)는 "
        "파랑·초록 계열"
        "(목표·효과 강조는 초록), 가운데 화살표는 진한 파랑"
    ),
    "technique": (
        "묶음(칸)마다 서로 다른 차분한 색 띠(남색·청록·주황·자주 등 4색 안쪽), "
        "등급(상·중·하·+·0·−)은 "
        "같은 색의 진하기와 기호 모양으로 구분"
    ),
    "stat_chart": "남색·청록 계열, 가장 최근 값만 진하게",
    "schedule": "남색·청록 계열, 단계마다 명도를 달리한 막대",
}
_DEFAULT_PALETTE = "남색·청록 계열 기본, 핵심 한 곳만 주황 강조"
# Nano Banana imageConfig.aspectRatio 가 받는 값 중 이 앱이 쓰는 것
ASPECTS: tuple[str, ...] = ("21:9", "16:9", "3:2", "4:3", "1:1")


def choose_aspect(spec: BaseModel) -> str:
    """내용 양으로 비율을 고른다 — 빈 공간이 크게 남지 않게 (v2 [4]). 밑그림·그림 생성이 같은 값."""
    if isinstance(spec, AsIsToBeSpec):
        return "3:2" if max(len(spec.as_is), len(spec.to_be)) >= 4 else "16:9"
    if isinstance(spec, TechniqueSpec):
        if spec.rows:
            return "4:3" if len(spec.rows) >= 5 else "16:9"
        n = len(spec.groups)
        most = max((len(g.items) for g in spec.groups), default=1)
        if n == 4:
            return "4:3"
        if n >= 5:
            return "3:2"
        return "4:3" if most >= 4 else "16:9"
    if isinstance(spec, ConceptSpec):
        return "21:9" if sum(len(b.lines) for b in spec.boxes) <= 4 else "16:9"
    if isinstance(spec, ProcessSpec):
        return "16:9" if any(len(s.outputs) >= 2 for s in spec.stages) else "21:9"
    if isinstance(spec, ScheduleSpec):
        n = len(spec.stages)
        return "21:9" if n <= 4 else ("16:9" if n <= 6 else "3:2")
    if isinstance(spec, StatChartSpec):
        return "21:9" if len(spec.categories) > 6 else "16:9"
    if isinstance(spec, ComparisonSpec):
        return "4:3" if len(spec.aspects) >= 4 or len(spec.projects) >= 3 else "16:9"
    return "16:9"


def image_prompt(
    spec: BaseModel, *, caption: str = "", style: str = "", aspect: str | None = None
) -> str:
    """Nano Banana Pro 프롬프트 — v2 [4]: 밑그림은 내용 구조만 알려 주고, 색 강조·아이콘·제목 계층·
    여백을 갖춘 인포그래픽으로 **새로 디자인**하게 한다(예전 "배치 그대로 유지" 는 회색 밑그림을
    베낀
    그림을 만들었다). 글자는 목록 그대로·더하지 않기는 그대로. 데이터 그림(그래프·일정표)은 값·기간
    비율만 지키게 한다. style 은 [말로 고치기]의 모양 요청 — 밑그림에서 새로 그릴 때 덧붙인다."""
    kind = str(getattr(spec, "kind", ""))
    label = spec.title if isinstance(spec, TechniqueSpec) else KIND_LABEL.get(kind, "그림")
    ratio = aspect or choose_aspect(spec)
    data_fixed = isinstance(spec, (StatChartSpec, ScheduleSpec))
    lines = [
        f"공공기관 연구과제 제안서에 넣을 전문 인포그래픽({label})을 새로 디자인하라. "
        f"가로세로 비율 {ratio}.",
        "참고 이미지는 무엇이 어느 묶음에 속하는지, 순서와 화살표 방향만 알려 주는 밑그림이다. "
        "회색 상자 배치를 그대로 베끼지 말고 아래 디자인 규칙으로 완성도 있게 다시 그려라.",
        _layout_hint(spec),
        "[디자인]",
        "- 제목 계층: 그림 제목(가장 크고 굵게) → 묶음 머리글(색 띠, 중간 굵기) → 항목(본문 글씨).",
        f"- 색: {_PALETTE_HINT.get(kind, _DEFAULT_PALETTE)}. 가장 중요한 한 곳만 가장 "
        f"진한 색으로 강조.",
        "- 묶음마다 단순한 선 아이콘 하나(톱니바퀴·그래프·방패·시계·돋보기·전구·체크 표시 "
        "같은 일반 "
        "기호). 아이콘 안에 글자·숫자를 넣지 않는다.",
        "- 흑백 인쇄에서도 구분되게: 색만으로 나누지 말고 명도 차·무늬(점·빗금)·테두리 "
        "모양(실선·점선·"
        "굵기)·도형 모양을 함께 쓴다.",
        "- 여백은 고르게, 큰 빈 공간 없이 그림 전체를 채운다. 상자 크기는 글자 양에 맞춘다.",
        "- 글씨는 크게: 제안서 본문 폭(약 15cm)으로 줄여 넣어도 읽히게, 상자 하나에 1~2줄.",
        "- 흰 배경. 그림 번호·캡션 문구는 그림 안에 넣지 않는다.",
        (
            "- 데이터: 막대 길이·기간 비율·값 순서는 참고 이미지와 같게 지킨다."
            if data_fixed
            else ""
        ),
        "[글자 — 가장 중요]",
        "- 아래 글자 목록의 글자만, 한 글자도 바꾸지 말고 빼거나 더하지도 말고 그대로 쓴다. "
        "맞춤법을 고치지 않는다.",
        "- 목록에 없는 글자·숫자·영문, 로고·사람 얼굴·사진·실제 기관 상표는 넣지 않는다.",
        "- 한 항목의 글자는 한 상자 안에 둔다(줄바꿈은 띄어쓰기 자리에서만).",
        (
            f"모양 요청(제안자): {' '.join(style.split())} — 색·선 굵기·여백 같은 모양만 바꾸고, "
            "글자·묶음·순서·화살표 방향은 글자 목록과 밑그림 그대로 둔다."
        )
        if style.strip()
        else "",
        "글자 목록:",
        *[f"- {t}" for t in texts_of(spec)],
    ]
    if caption:
        lines.append(f"그림 제목(그림 안에 넣지 않는다): {caption}")
    return "\n".join(x for x in lines if x)


def _layout_hint(spec: BaseModel) -> str:
    if isinstance(spec, AsIsToBeSpec):
        return (
            f"구조: 왼쪽 '{AS_IS_HEAD}' 칸 {len(spec.as_is)}개(현황·원인·한계), 오른쪽 "
            f"'{TO_BE_HEAD}' 칸 {len(spec.to_be)}개(목표·해결 방안·기대효과), 가운데 "
            f"큰 화살표 위에 "
            f"핵심 해결 방안 한 줄 '{spec.solution}'. 칸마다 작은 이름표(현황·원인…)를 붙인다."
        )
    if isinstance(spec, TechniqueSpec):
        if spec.rows:
            return (
                f"구조: 평가 표. 열 {len(spec.columns)}개({', '.join(spec.columns)}), 기준(행) "
                f"{len(spec.rows)}개. 칸의 기호(+·0·− 또는 상·중·하)는 기호 모양과 색 진하기로 "
                f"구분한다. 표 아래에 '{spec.note}' 를 작게."
            )
        names = ", ".join(g.name for g in spec.groups)
        grid = "2×2 사분면" if len(spec.groups) == 4 else f"{len(spec.groups)}개 묶음"
        return (
            f"구조: {grid}({names}). 묶음마다 항목 1~4개, 항목 옆 강도·금액(상·중·하, "
            f"산출 필요 등)은 "
            f"작은 배지로. 아래에 '{spec.note}' 를 작게."
        )
    if isinstance(spec, ConceptSpec):
        return "구조: 4단계 흐름(현황 → 문제 → 해결 방안 → 기대효과), 단계 사이 화살표."
    if isinstance(spec, ProcessSpec):
        return (
            f"구조: 단계 {len(spec.stages)}개를 왼쪽에서 오른쪽으로 화살표로 잇고, 단계마다 "
            "산출물을 붙인다."
        )
    if isinstance(spec, ScheduleSpec):
        return (
            f"구조: 간트 차트. 가로축 1~{spec.total_months}개월, 단계마다 가로 막대 하나. "
            "막대 길이 비율을 지켜라."
        )
    if isinstance(spec, StatChartSpec):
        kind = "막대 그래프" if spec.chart == "bar" else "꺾은선 그래프"
        return (
            f"구조: {kind}. 가로축 {len(spec.categories)}개 구분, 값 글자를 막대 위에 표시. "
            "값 비율을 지켜라."
        )
    if isinstance(spec, ComparisonSpec):
        return (
            f"구조: 표. 행은 비교 항목 {len(spec.aspects)}개, 열은 기존 과제 "
            f"{len(spec.projects)}개와 제안 과제(마지막 열 강조)."
        )
    if isinstance(spec, RoadmapSpec):
        return "구조: 위쪽에 성과지표 상자들, 아래쪽에 활용 단계를 왼쪽에서 오른쪽 화살표로."
    return ""


# ── 버전 비교·편집 ─────────────────────────────────────────
def figure_diff(old: Sequence[Figure], new: Sequence[Figure]) -> list[dict[str, Any]]:
    """[{figure_id, kind, section, change}] — added | removed | redrawn | texts | included |
    excluded | confirmed | baseline | swapped(다른 기법) | accepted(넣기 확정) | dismissed(필요
    없음) |
    restored(다시 넣음). 추천 결정이 바뀐 그림은 넣음·뺌을 따로 세지 않는다 (변경 1건)."""
    before = {f.id: f for f in old}
    after = {f.id: f for f in new}
    out: list[dict[str, Any]] = []
    for fid, f in after.items():
        o = before.get(fid)
        if o is None:
            out.append(_row(f, "added"))
            continue
        if getattr(o.spec, "technique", None) != getattr(f.spec, "technique", None):
            out.append(_row(f, "swapped"))
        elif o.spec.model_dump() != f.spec.model_dump():
            out.append(_row(f, "texts"))
        elif o.image_sha != f.image_sha:
            out.append(_row(f, "baseline" if f.renderer == "baseline" else "redrawn"))
        decision = _decision_change(o, f)
        if decision:
            out.append(_row(f, decision))
        elif o.included != f.included:
            out.append(_row(f, "included" if f.included else "excluded"))
        if o.confirmed != f.confirmed and f.confirmed:
            out.append(_row(f, "confirmed"))
    for fid, o in before.items():
        if fid not in after:
            out.append(_row(o, "removed"))
    return out


def _decision_change(old: Figure, new: Figure) -> str | None:
    """[11] 추천 결정 변화 — pending → accepted | dismissed, dismissed → accepted(다시 넣음)."""
    a = old.recommendation.status if old.recommendation else None
    b = new.recommendation.status if new.recommendation else None
    if a == b or b is None:
        return None
    if b == "dismissed":
        return "dismissed"
    if b == "accepted":
        return "restored" if a == "dismissed" else "accepted"
    return None


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
    elif isinstance(spec, AsIsToBeSpec):
        for side, title in (("as_is", "현재"), ("to_be", "연구 후")):
            for i, it in enumerate(getattr(spec, side)):
                rows.append(
                    {"path": f"{side}.{i}.text", "label": f"{title} {it.tag}", "value": it.text}
                )
            if side == "as_is":
                rows.append({"path": "solution", "label": "핵심 해결 방안", "value": spec.solution})
    elif isinstance(spec, TechniqueSpec):
        for gi, g in enumerate(spec.groups):
            for ii, it in enumerate(g.items):
                rows.append(
                    {
                        "path": f"groups.{gi}.items.{ii}.text",
                        "label": f"{g.name} {ii + 1}",
                        "value": it.text,
                    }
                )
        for ri, r in enumerate(spec.rows):
            rows.append({"path": f"rows.{ri}.name", "label": f"기준 {ri + 1}", "value": r.name})
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


def _change_rows(spec: BaseModel) -> list[tuple[str, str]]:
    """바뀐 내용 비교용 (이름, 값) — 고칠 수 있는 글자 + 일정표 기간·수치 그래프 값."""
    rows = [(r["label"], r["value"]) for r in editable_texts(spec)]
    if isinstance(spec, ScheduleSpec):
        rows.extend(
            (f"단계 {i + 1} 기간", f"{s.start_month}~{s.end_month}개월")
            for i, s in enumerate(spec.stages)
        )
        rows.append(("총 기간", f"{spec.total_months}개월"))
    elif isinstance(spec, StatChartSpec):
        rows.extend((f"값 {i + 1}", v) for i, v in enumerate(spec.value_texts))
    return rows


def _clip_line(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_CHANGE_LINE else text[: MAX_CHANGE_LINE - 1] + "…"


def spec_change_summary(
    old: BaseModel, new: BaseModel, *, limit: int = MAX_CHANGE_LINES
) -> list[str]:
    """명세 두 개의 차이를 한 줄씩 — "단계 3 '…' → '…'", "단계 4 추가 '…'", "산출물 삭제 '…'".
    순서 비교(SequenceMatcher)라 단계를 끼워 넣어도 뒤 단계가 모두 바뀐 것으로 나오지 않는다."""
    before, after = _change_rows(old), _change_rows(new)
    a, b = [v for _, v in before], [v for _, v in after]
    lines: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pairs):
            lines.append(f"{after[j1 + k][0]} '{a[i1 + k]}' → '{b[j1 + k]}'")
        for j in range(j1 + pairs, j2):
            lines.append(f"{after[j][0]} 추가 '{b[j]}'")
        for i in range(i1 + pairs, i2):
            lines.append(f"{before[i][0]} 삭제 '{a[i]}'")
    if not lines and old.model_dump() != new.model_dump():
        lines.append("배치·연결 변경")
    if len(lines) > limit:
        lines = [*lines[: limit - 1], f"외 {len(lines) - limit + 1}건"]
    return [_clip_line(x) for x in lines]


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


def next_figure_id(section: str, existing: Iterable[str], *, prefix: str = "") -> str:
    """ "f:<섹션>:<n>" — 분석 기법 추천은 prefix "t" ("f:method:t1") 라 기본 그림과 동시에 만들어도
    id 가 겹치지 않는다."""
    taken = set(existing)
    n = 1
    while f"f:{section}:{prefix}{n}" in taken:
        n += 1
    return f"f:{section}:{prefix}{n}"


def unconfirmed(figures: Iterable[Figure]) -> list[Figure]:
    return [f for f in figures if f.included and not f.confirmed]


def undecided(figures: Iterable[Figure]) -> list[Figure]:
    """[11] 추천 그림 중 [넣기 확정]·[필요 없음] 을 고르지 않은 것 (그대로 마무리하면 들어간다)."""
    return [f for f in figures if f.undecided]
