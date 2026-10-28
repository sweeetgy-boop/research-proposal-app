"""분석 기법 인포그래픽 규칙 — 순수 함수 ([11] 2026-10-28, ADR 0033).

초안이 만들어진 뒤 Argon 이 본문·입력·근거를 읽고 이 제안에 의미 있는 분석이 나오는 기법만
0~2개 고른다(`parse_picks`). 고른 기법마다 제안 내용으로 실제 분석한 결과(TechniqueSpec)를
받아 여기서 검사한다.

- 정성(qualitative: SWOT·TOWS·PMI·역장분석·PEST(EL)·6색 모자): 묶음 이름은 기법의 고정
  이름, 항목마다 강도 상·중·하.
- 비교·평가(evaluation: 퓨·가중치 매트릭스·AHP·TOPSIS·FMEA): 열 × 기준 표, 칸은 +/0/−
  또는 상·중·하.
- 경제성·확률(economic: 비용-편익·비용-효과·LCC·민감도·의사결정나무·시나리오·DEA): 금액
  칸은 제안·근거에 있는 수치만, 없으면 "산출 필요"(`repair_technique` — 새 수치를 계산해
  넣지 않는다).
- 연구 절차(procedure: 델파이·체계적 문헌고찰): 방법의 단계·대상·기준을 본문에서 정리.
- 모든 기법 그림에 "제안 내용 기반 예비 평가"(PRELIM_NOTE) — 등급은 판단이다.
- 항목마다 출처(source): 본문 문장 id `s:<섹션>:<n>`·근거 청크 id·`input:<입력 칸>`.
  모르는 출처는 글자로 찾아 잇고, 못 찾으면 그 항목을 뺀다. 글자·수치 출처 검사는
  `figures.validate_spec`(pool) 이 함께 한다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models.draft import Section
from rra.domain.models.figure import (
    MAX_BOX,
    NEED_CALC,
    PRELIM_NOTE,
    MatrixRow,
    TechGroup,
    TechItem,
    TechniqueSpec,
)
from rra.domain.models.request import ProposalRequest
from rra.domain.models.review import sentence_id
from rra.domain.rules.numbers import numbers

FAMILIES: tuple[str, ...] = ("qualitative", "evaluation", "economic", "procedure")
LEVELS: tuple[str, ...] = ("상", "중", "하")
PM: tuple[str, ...] = ("+", "0", "−")
# 비교·평가 표에서 항상 쓸 수 있는 열 이름 (구조 라벨 — 사실이 아니다)
EVAL_FIXED_COLUMNS: tuple[str, ...] = ("현행 방식", "제안 방식", "기준안")
MAX_PICKS = 2
MAX_REASON = 120

# 위반 코드
TECH_UNKNOWN = "technique_unknown"
TECH_LAYOUT = "technique_layout"  # 기법 종류에 맞지 않는 모양(묶음 대신 표 등)
TECH_GROUPS = "technique_groups"  # 고정 묶음 이름이 아니거나 묶음 수 부족
TECH_RATING = "technique_rating"  # 강도·평가 기호가 정해진 값이 아님
TECH_CELLS = "technique_cells"  # 표 칸 수가 열 수와 다름
TECH_SOURCE = "technique_source_unknown"  # 항목 출처를 찾을 수 없음
TECH_EMPTY = "technique_empty"  # 다듬은 뒤 항목이 남지 않음

_RATING_ALIASES = {
    "높음": "상",
    "high": "상",
    "h": "상",
    "보통": "중",
    "medium": "중",
    "mid": "중",
    "m": "중",
    "낮음": "하",
    "low": "하",
    "l": "하",
    "-": "−",
    "–": "−",
    "—": "−",
    "－": "−",
    "＋": "+",
    "o": "0",
    "○": "0",
}
_SPACES = re.compile(r"\s+")
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass(frozen=True)
class Technique:
    key: str
    label: str
    family: str
    section: str = "method"
    summary: str = ""
    fits: str = ""
    groups: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    scale: str = "level"  # level(상·중·하) | pm(+/0/−) — evaluation
    free_groups: bool = False
    free_columns: bool = False
    min_groups: int = 0

    @property
    def layout(self) -> str:
        return "matrix" if self.family == "evaluation" else "groups"

    @property
    def needed_groups(self) -> int:
        if self.min_groups:
            return self.min_groups
        return len(self.groups) if self.groups else 2

    def scale_values(self) -> tuple[str, ...]:
        return PM if self.scale == "pm" else LEVELS

    def fixed_texts(self) -> list[str]:
        """그림에 늘 쓸 수 있는 글자 — 기법 이름·묶음·고정 열·등급·안내문 (출처 검사에서 통과)."""
        out = [self.label, *self.groups, *self.columns, PRELIM_NOTE, NEED_CALC, *LEVELS, *PM]
        if self.family == "evaluation":
            out.extend(EVAL_FIXED_COLUMNS)
        return out


@dataclass(frozen=True)
class TechniqueCatalog:
    items: tuple[Technique, ...] = ()

    def get(self, key: str) -> Technique | None:
        return next((t for t in self.items if t.key == key), None)

    def keys(self) -> list[str]:
        return [t.key for t in self.items]

    def __len__(self) -> int:
        return len(self.items)


def catalog_from(data: Mapping[str, Any] | None) -> TechniqueCatalog:
    """techniques.yaml(dict) → 목록. 모르는 family·중복 key 는 오류."""
    rows = (data or {}).get("techniques") or []
    out: list[Technique] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("key") or "").strip()
        family = str(row.get("family") or "")
        if not key or key in seen:
            raise ValueError(f"techniques.yaml: key 가 비었거나 중복입니다 ({key!r}).")
        if family not in FAMILIES:
            raise ValueError(f"techniques.yaml: {key} family 를 모릅니다 ({family!r}).")
        seen.add(key)
        out.append(
            Technique(
                key=key,
                label=str(row.get("label") or key),
                family=family,
                section=str(row.get("section") or "method"),
                summary=" ".join(str(row.get("summary") or "").split()),
                fits=" ".join(str(row.get("fits") or "").split()),
                groups=tuple(str(g) for g in row.get("groups") or ()),
                columns=tuple(str(c) for c in row.get("columns") or ()),
                scale=str(row.get("scale") or "level"),
                free_groups=bool(row.get("free_groups", False)),
                free_columns=bool(row.get("free_columns", False)),
                min_groups=int(row.get("min_groups") or 0),
            )
        )
    return TechniqueCatalog(tuple(out))


# ── 추천 (고르기) ───────────────────────────────────────────
@dataclass(frozen=True)
class Pick:
    technique: str
    reason: str


@dataclass(frozen=True)
class Picks:
    picks: tuple[Pick, ...] = ()
    none_reason: str = ""  # 고른 것이 없을 때 모델이 적은 "해당 없음" 사유 (비신뢰)
    dropped: tuple[str, ...] = ()  # 목록에 없거나 중복이라 버린 key


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def parse_picks(
    data: Any, catalog: TechniqueCatalog, *, limit: int = MAX_PICKS, exclude: Iterable[str] = ()
) -> Picks | None:
    """모델 답 {"picks": [{"technique", "reason"}], "none_reason"} → Picks. 형식이 아니면 None.
    목록 밖·중복·exclude(이미 있는 기법)는 버리고 dropped 에 남긴다. 최대 limit 개."""
    if not isinstance(data, Mapping):
        return None
    raw = data.get("picks")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return None
    skip = set(exclude)
    picks: list[Pick] = []
    dropped: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("technique") or item.get("key") or "").strip()
        if catalog.get(key) is None or key in skip or any(p.technique == key for p in picks):
            if key:
                dropped.append(key[:40])
            continue
        if len(picks) >= max(0, limit):
            dropped.append(key)
            continue
        picks.append(Pick(key, _clip(item.get("reason"), MAX_REASON)))
    return Picks(tuple(picks), _clip(data.get("none_reason"), MAX_REASON), tuple(dropped[:4]))


# ── 출처 ─────────────────────────────────────────────────
@dataclass(frozen=True)
class SourceIndex:
    """항목 출처 후보 — id → 원문(공백 제거). 본문 문장·입력 칸·근거 청크."""

    texts: Mapping[str, str] = field(default_factory=dict)
    labels: Mapping[str, str] = field(
        default_factory=dict
    )  # id → 화면 표시 ("2-다 연구 방법 문장 2")

    def known(self, source: str) -> bool:
        return source in self.texts

    def find(self, text: str) -> str | None:
        """글자가 그대로 든 출처, 없으면 내용 단어(2자 이상)가 모두 든 출처 (앞쪽 우선 = "
        "본문 먼저)."""
        v = _norm(text)
        if not v:
            return None
        for sid, body in self.texts.items():
            if v in body:
                return sid
        words = [w.casefold() for w in _WORD.findall(text) if len(w) >= 2]
        if not words:
            return None
        for sid, body in self.texts.items():
            if all(w in body for w in words):
                return sid
        return None


def _norm(text: str) -> str:
    return _SPACES.sub("", text or "").casefold()


def source_index(
    sections: Sequence[Section],
    request: ProposalRequest | None,
    chunks: Iterable[tuple[str, str]] = (),
    *,
    titles: Mapping[str, str] | None = None,
    input_labels: Mapping[str, str] | None = None,
    chunk_labels: Mapping[str, str] | None = None,
) -> SourceIndex:
    """chunks: (chunk_id, 본문) — 프롬프트에 보인 근거만 (공용 계정이면 internal 제외).
    labels 는 화면 표시용 — 내부 id 대신 "2-다 … 문장 2"·"제안 입력: 발생 원인"·"근거 자료 1"."""
    texts: dict[str, str] = {}
    labels: dict[str, str] = {}
    for s in sections:
        for i, sent in enumerate(s.sentences):
            sid = sentence_id(s.key, i)
            texts[sid] = _norm(sent.text)
            labels[sid] = f"{(titles or {}).get(s.key, s.key)} 문장 {i + 1}"
    if request is not None:
        for key, value in request.prompt_view().items():
            if isinstance(value, str) and value.strip():
                sid = f"input:{key}"
                texts[sid] = _norm(value)
                labels[sid] = f"제안 입력: {(input_labels or {}).get(key) or _input_label(key)}"
    for n, (cid, body) in enumerate(chunks, start=1):
        texts[cid] = _norm(body)
        labels[cid] = (chunk_labels or {}).get(cid) or f"근거 자료 {n}"
    return SourceIndex(texts, labels)


def _input_label(key: str) -> str:
    field_info = ProposalRequest.model_fields.get(key)
    return (field_info.description if field_info and field_info.description else "") or "입력"


# ── 정리·검사 ───────────────────────────────────────────────
def _rating(value: Any) -> str | None:
    if value is None:
        return None
    v = " ".join(str(value).split())
    if not v:
        return None
    return _RATING_ALIASES.get(v.casefold(), v)


def _box(value: Any) -> str:
    from rra.domain.rules.figures import clip_text

    return clip_text(str(value or ""), MAX_BOX)


def normalize_technique_data(data: Any, tech: Technique) -> dict[str, Any]:
    """모델 답 → TechniqueSpec 입력: key·제목·안내문 고정, 글자는 MAX_BOX 로 줄이고 등급 "
    "표기를 맞춘다."""
    src = data if isinstance(data, Mapping) else {}
    out: dict[str, Any] = {
        "technique": tech.key,
        "title": tech.label,
        "note": PRELIM_NOTE,
    }
    if tech.layout == "matrix":
        out["columns"] = [" ".join(str(c).split())[:40] for c in (src.get("columns") or [])][:5]
        rows = []
        for r in (src.get("rows") or [])[:6]:
            if not isinstance(r, Mapping):
                continue
            rows.append(
                {
                    "name": _box(r.get("name") or r.get("text")),
                    "cells": [(_rating(c) or "") for c in (r.get("cells") or [])][:5],
                    "source": str(r.get("source") or "")[:200],
                }
            )
        out["rows"] = rows
        out["groups"] = []
    else:
        groups = []
        for g in (src.get("groups") or [])[:6]:
            if not isinstance(g, Mapping):
                continue
            items = []
            for it in (g.get("items") or [])[:4]:
                if isinstance(it, str):
                    it = {"text": it}
                if not isinstance(it, Mapping):
                    continue
                items.append(
                    {
                        "text": _box(it.get("text")),
                        "rating": _rating(it.get("rating") or it.get("strength")),
                        "amount": (" ".join(str(it["amount"]).split())[:MAX_BOX] or None)
                        if it.get("amount") not in (None, "")
                        else None,
                        "source": str(it.get("source") or "")[:200],
                    }
                )
            groups.append({"name": " ".join(str(g.get("name") or "").split())[:40], "items": items})
        out["groups"] = groups
        out["columns"] = []
        out["rows"] = []
    return out


def _amount_ok(amount: str, pool: Any) -> bool:
    """금액 칸 — "산출 필요" 이거나, 수치가 하나 이상이고 모두 pool(제안·근거)에 있다(연도는 "
    "계획 수치만)."""
    if amount == NEED_CALC:
        return True
    found = list(numbers(amount))
    if not found:
        return False
    return all(pool.has_number(c) and (c[0] != "year" or c in pool.plan_nums) for _, c in found)


def repair_technique(
    spec: TechniqueSpec, tech: Technique, pool: Any, sources: SourceIndex
) -> TechniqueSpec:
    """버리기 전에 한 번 — 출처 id 를 글자로 찾아 잇고, 출처·글자를 못 찾은 항목은 빼고, 경제성
    금액은
    제안·근거 수치가 아니면 "산출 필요", 정성 외의 등급·금액은 지운다. 고정 묶음 이름은 그대로
    둔다."""

    def fix_source(text: str, source: str) -> str | None:
        if source and sources.known(source):
            return source
        return sources.find(text)

    if tech.layout == "matrix":
        rows: list[MatrixRow] = []
        for r in spec.rows:
            src = fix_source(r.name, r.source)
            if src is None or not pool.has_text(r.name):
                continue
            rows.append(r.model_copy(update={"source": src}))
        return spec.model_copy(update={"rows": rows, "groups": [], "note": PRELIM_NOTE})
    groups: list[TechGroup] = []
    for g in spec.groups:
        items: list[TechItem] = []
        for it in g.items:
            src = fix_source(it.text, it.source)
            if src is None or not pool.has_text(it.text):
                continue
            update: dict[str, Any] = {"source": src}
            if tech.family == "economic":
                update["amount"] = (
                    it.amount if it.amount and _amount_ok(it.amount, pool) else NEED_CALC
                )
                update["rating"] = None
            elif tech.family == "procedure":
                update["rating"] = None
                update["amount"] = None
            else:
                update["amount"] = None
            items.append(it.model_copy(update=update))
        if items:
            groups.append(g.model_copy(update={"items": items}))
    return spec.model_copy(
        update={"groups": groups, "columns": [], "rows": [], "note": PRELIM_NOTE}
    )


def validate_technique(
    spec: TechniqueSpec, tech: Technique | None, sources: SourceIndex
) -> list[str]:
    """구조 검사 (글자·수치 출처는 figures.validate_spec 이 따로 본다). 위반 코드 목록."""
    if tech is None or spec.technique != (tech.key if tech else None):
        return [TECH_UNKNOWN]
    problems: list[str] = []
    if tech.layout == "matrix":
        if spec.groups or not spec.rows or len(spec.columns) < 1:
            return [TECH_LAYOUT if spec.groups or not spec.columns else TECH_EMPTY]
        if len(spec.rows) < 2:
            problems.append(TECH_EMPTY)
        fixed = list(tech.columns)
        if fixed and list(spec.columns[: len(fixed)]) != fixed:
            problems.append(TECH_GROUPS)
        if not tech.free_columns and len(spec.columns) != len(fixed):
            problems.append(TECH_GROUPS)
        if tech.free_columns and len(spec.columns) - len(fixed) < 2 and tech.key != "fmea":
            problems.append(TECH_GROUPS)  # 대안 2개 이상이어야 비교가 된다
        allowed = set(tech.scale_values())
        for r in spec.rows:
            if len(r.cells) != len(spec.columns):
                problems.append(TECH_CELLS)
                break
            if any(c not in allowed for c in r.cells):
                problems.append(TECH_RATING)
                break
        if any(not sources.known(r.source) for r in spec.rows):
            problems.append(TECH_SOURCE)
    else:
        if spec.rows or spec.columns:
            return [TECH_LAYOUT]
        if not spec.groups:
            return [TECH_EMPTY]
        names = [g.name for g in spec.groups]
        if not tech.free_groups:
            if any(n not in tech.groups for n in names) or len(set(names)) != len(names):
                problems.append(TECH_GROUPS)
        if len(spec.groups) < tech.needed_groups:
            problems.append(TECH_GROUPS)
        for g in spec.groups:
            for it in g.items:
                if tech.family == "qualitative" and it.rating not in LEVELS:
                    problems.append(TECH_RATING)
                    break
                if tech.family == "economic" and not it.amount:
                    problems.append(TECH_RATING)
                    break
                if not sources.known(it.source):
                    problems.append(TECH_SOURCE)
                    break
    if spec.note != PRELIM_NOTE:
        problems.append(TECH_LAYOUT)
    return list(dict.fromkeys(problems))


def provenance(
    spec: TechniqueSpec,
    sources: SourceIndex | None = None,
    *,
    titles: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """카드 "항목 출처" — [{group, text, rating, amount, source, source_label}]."""
    rows: list[dict[str, str]] = []
    label = dict((sources.labels if sources else {}) or {})
    for src in {it.source for g in spec.groups for it in g.items} | {r.source for r in spec.rows}:
        label.setdefault(src, _default_label(src, titles))
    for g in spec.groups:
        for it in g.items:
            rows.append(
                {
                    "group": g.name,
                    "text": it.text,
                    "rating": it.rating or "",
                    "amount": it.amount or "",
                    "source": it.source,
                    "source_label": label[it.source],
                }
            )
    for r in spec.rows:
        rows.append(
            {
                "group": "",
                "text": r.name,
                "rating": " / ".join(
                    f"{c} {v}" for c, v in zip(spec.columns, r.cells, strict=False)
                ),
                "amount": "",
                "source": r.source,
                "source_label": label[r.source],
            }
        )
    return rows


def _default_label(source: str, titles: Mapping[str, str] | None = None) -> str:
    """SourceIndex 없이 — 본문 문장 id·입력 칸·근거 id 를 사람이 읽는 말로 (내부 id 를 보이지
    않는다)."""
    if source.startswith("s:"):
        parts = source.split(":")
        if len(parts) == 3 and parts[2].isdigit():
            title = (titles or {}).get(parts[1], "본문")
            return f"{title} 문장 {int(parts[2]) + 1}"
    if source.startswith("input:"):
        return f"제안 입력: {_input_label(source[len('input:') :])}"
    return "근거 자료" if source else "출처 없음"


def technique_texts(spec: TechniqueSpec) -> list[str]:
    """그림에 그려질 글자 (figures.texts_of 가 쓴다)."""
    out: list[str] = [spec.title]
    for g in spec.groups:
        out.append(g.name)
        for it in g.items:
            out.append(it.text)
            if it.rating:
                out.append(it.rating)
            if it.amount:
                out.append(it.amount)
    if spec.rows:
        out.extend(spec.columns)
        for r in spec.rows:
            out.append(r.name)
            out.extend(r.cells)
    out.append(spec.note)
    return out
