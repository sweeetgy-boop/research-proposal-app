"""비슷한 유추 자료 묶기 + 묶음 비교 분석 검증 (ADR 0065, 계약 problem-card.md 4.6절). 순수 함수.

**묶기** — 비슷한 자료를 지우지 않고 묶는다. 순위 순 목록의 상위 `window` 건 안에서
"제목 낱말 겹침 ≥ title_ratio(꼬리말 제외·짧은 쪽 기준, `analogy_rank.title_overlap`)" **또는**
"초록 의미 유사도 ≥ abstract_similarity(호출자가 준 유사도 행렬)" 로 이어진 것끼리 한 묶음
(연결 요소). 묶음은 대표 1건(순위가 가장 높은 것) + 나머지 구성원으로 접는다. 유사도 행렬이
없으면(임베딩 없음·실패) 제목 기준만 쓴다.

**검증** — Argon 의 비교 분석 JSON 을 그대로 믿지 않는다:
- id 는 보낸 목록 안의 것만(밖이면 그 항목 버림, 같은 id 는 처음 것만).
- 칸 글에 제공한 글(제목·초록·과제 입력)에 없는 숫자·기관명·법령명이 있거나 한자·가나가 섞였으면
  그 칸을 `NEEDS_SOURCE` 로 바꾼다. 빈 칸, 모델이 "초록에 없음/알 수 없음" 류로 답한 칸도 같은
  문구로 통일한다.
- 모델이 빠뜨린 구성원은 네 칸 모두 그 문구로 채워 표에 남긴다.
- 쓸 만한 칸이 하나라도 있는 항목이 0 이면 실패(None).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rra.domain.models.analogy_group import GROUP_FIELDS, GroupItem, GroupSummary
from rra.domain.rules.analogy_rank import title_overlap, title_words
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.live_search import normalize_query
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.novel_recommendation import unsupported_names
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted

NEEDS_SOURCE = "초록으로는 구분 안 됨 — 원문 확인 필요"
USE_BASIS = "추정"  # '이 과제에 활용할 점'은 늘 추정이다
GROUP_ID_CHARS = 12
MAX_CELL_CHARS = 400
ABSTRACT_CHARS = 900  # 프롬프트에 넣는 초록 앞부분
KEY_VERSION = "analogy-group-v1"


# ── 묶기 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class Grouped[T]:
    """대표(순위가 가장 높은 것) + 함께 묶인 나머지(순위 순)."""

    head: T
    members: tuple[T, ...] = ()


def group_similar[T](
    ordered: Sequence[T],
    titles: Sequence[str],
    *,
    title_ratio: float,
    abstract_similarity: float,
    window: int,
    max_members: int,
    suffixes: Sequence[str] = (),
    similarities: Sequence[Sequence[float]] | None = None,
) -> list[Grouped[T]]:
    """순위 순 목록 → 순위 순 묶음 목록(묶이지 않은 자료는 구성원 없는 묶음).

    titles: ordered 와 같은 순서의 제목. similarities: 상위 window 건의 초록 유사도 행렬
    (`similarities[i][j]`, 없거나 크기가 모자라면 그 쌍은 제목 기준만). window 밖의 자료는 묶지
    않는다. max_members: 대표를 포함한 묶음 크기 — 넘으면 순위 높은 것만 남고, 넘친 자료는 어느
    묶음에도 들지 않은 채 목록에서 빠진다(대표와 비슷한 자료라 따로 한 자리를 주지 않는다)."""
    n = min(len(ordered), max(window, 0))
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    words = [title_words(titles[i], suffixes) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            linked = title_ratio > 0 and title_overlap(words[i], words[j]) >= title_ratio
            if not linked and abstract_similarity > 0 and similarities is not None:
                try:
                    linked = float(similarities[i][j]) >= abstract_similarity
                except (IndexError, TypeError, ValueError):
                    linked = False
            if linked:
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)  # 뿌리는 늘 순위가 가장 높은 것
    members: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        if root != i:
            members.setdefault(root, []).append(i)
    out: list[Grouped[T]] = []
    for i, row in enumerate(ordered):
        if i < n and find(i) != i:
            continue  # 다른 대표의 구성원
        rest = members.get(i, [])[: max(max_members - 1, 0)] if i < n else []
        out.append(Grouped(row, tuple(ordered[k] for k in rest)))
    return out


def dot_matrix(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    """정규화한 벡터들의 내적 행렬(= 코사인)."""
    return [[sum(x * y for x, y in zip(a, b, strict=False)) for b in vectors] for a in vectors]


def group_id(doc_ids: Sequence[str]) -> str:
    """묶음 식별값 — 구성원 doc_id 를 정렬해 만든 짧은 해시(원문·순서 없음)."""
    body = "\n".join(sorted(dict.fromkeys(doc_ids)))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:GROUP_ID_CHARS]


def cache_key(version: str, doc_ids: Sequence[str], input_texts: Sequence[str]) -> str:
    """분석 캐시 키 = 지시문 지문·모델(version) + 정렬한 구성원 doc_id + 과제 입력 글 해시
    (카드 기능 문장 포함 — 호출자가 input_texts 에 넣는다). 원문은 남지 않는다."""
    text_hash = hashlib.sha256(
        "\n".join(normalize_query(t or "") for t in input_texts).encode("utf-8")
    ).hexdigest()
    body = "\n".join([KEY_VERSION, version, *sorted(dict.fromkeys(doc_ids)), text_hash])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── 검증 ───────────────────────────────────────────────────
# 모델이 '모른다'고 답한 칸 — 짧은 답이 이 말들로 이뤄져 있을 때만(긴 설명 속의 한 구절은 아님)
_UNKNOWN = re.compile(
    r"초록에\s*(?:는\s*)?(?:없|나오지|언급|기재|명시)|알\s*수\s*없|구분\s*(?:이\s*)?안\s*됨|"
    r"구분\s*(?:할\s*수\s*없|불가)|확인\s*(?:불가|할\s*수\s*없|필요)|정보\s*(?:가\s*)?없|"
    r"언급\s*(?:이\s*)?없|해당\s*없"
)
UNKNOWN_MAX_CHARS = 40
_REF = re.compile(r"\bD(\d{1,2})\b")
_REF_TITLE_CHARS = 24


def _is_unknown(text: str) -> bool:
    return len(text) <= UNKNOWN_MAX_CHARS and _UNKNOWN.search(text) is not None


def _named(text: str, titles: Mapping[str, str]) -> str:
    """글 속의 자료 표식(D1…)을 그 자료 제목으로 — 화면에 내부 표식을 내보내지 않는다."""

    def swap(m: re.Match[str]) -> str:
        title = titles.get(m.group(0))
        if title is None:
            return "다른 자료"
        short = title[:_REF_TITLE_CHARS] + ("…" if len(title) > _REF_TITLE_CHARS else "")
        return f"'{short}'"

    return _REF.sub(swap, text)


def checked_cell(value: object, allowed: Sequence[str], titles: Mapping[str, str]) -> str:
    """AI 글 한 칸 → 검사를 지난 글 또는 `NEEDS_SOURCE`."""
    if not isinstance(value, str):
        return NEEDS_SOURCE
    text = clean_sentence(escape_untrusted(_named(value, titles))).strip()[:MAX_CELL_CHARS]
    if not text or text == NEEDS_SOURCE or _is_unknown(text):
        return NEEDS_SOURCE
    if has_foreign_script(text):
        return NEEDS_SOURCE
    if unsupported_numbers(text, allowed) or unsupported_names(text, allowed):
        return NEEDS_SOURCE
    return text


@dataclass(frozen=True)
class GroupMember:
    """분석에 보낸 자료 한 건 — key 는 프롬프트의 표식(D1…)."""

    key: str
    doc_id: str
    title: str
    text: str  # 프롬프트에 넣은 글(제목·초록 앞부분·연도·분류) — 숫자·이름 대조의 기준


@dataclass(frozen=True)
class CheckedAnalysis:
    items: tuple[GroupItem, ...]
    summary: GroupSummary
    replaced: int  # 검증이 문구로 바꾼 칸 수(모델이 스스로 그 문구를 쓴 칸은 세지 않는다)
    missing: int  # 모델이 빠뜨려 채운 자료 수


def check_analysis(
    data: object, members: Sequence[GroupMember], input_texts: Sequence[str]
) -> CheckedAnalysis | None:
    """모델 출력(JSON 객체) → 검증한 표. 쓸 만한 항목이 0 이면 None."""
    if not isinstance(data, Mapping):
        return None
    by_key = {m.key: m for m in members}
    titles = {m.key: m.title for m in members}
    allowed = [*input_texts, *(m.text for m in members)]
    found: dict[str, GroupItem] = {}
    replaced = 0
    raw_items = data.get("items")
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, Mapping):
            continue
        key = str(raw.get("id") or "").strip()
        member = by_key.get(key)
        if member is None or key in found:
            continue  # 목록 밖 id · 같은 id 되풀이
        cells: dict[str, str] = {}
        for name in GROUP_FIELDS:
            before = raw.get(name)
            cells[name] = checked_cell(before, allowed, titles)
            if cells[name] == NEEDS_SOURCE and _was_content(before):
                replaced += 1
        found[key] = GroupItem(doc_id=member.doc_id, **cells)
    if not any(_useful(item) for item in found.values()):
        return None
    missing = 0
    items: list[GroupItem] = []
    for m in members:  # 보낸 순서(대표 먼저) — 빠뜨린 자료도 표에 남긴다
        item = found.get(m.key)
        if item is None:
            missing += 1
            item = GroupItem(doc_id=m.doc_id, **{name: NEEDS_SOURCE for name in GROUP_FIELDS})
        items.append(item)
    raw_summary = data.get("summary")
    summary_src: Mapping[str, Any] = raw_summary if isinstance(raw_summary, Mapping) else {}
    summary_cells: dict[str, str] = {}
    for name in ("common", "gap"):
        before = summary_src.get(name)
        summary_cells[name] = checked_cell(before, allowed, titles)
        if summary_cells[name] == NEEDS_SOURCE and _was_content(before):
            replaced += 1
    return CheckedAnalysis(
        items=tuple(items),
        summary=GroupSummary(**summary_cells),
        replaced=replaced,
        missing=missing,
    )


def _was_content(value: object) -> bool:
    """모델이 내용을 썼던 칸인가 — 빈 칸·'모름' 답은 바꾼 것으로 세지 않는다."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(text) and text != NEEDS_SOURCE and not _is_unknown(text)


def _useful(item: GroupItem) -> bool:
    return any(getattr(item, name) != NEEDS_SOURCE for name in GROUP_FIELDS)


def needs_source(item: GroupItem) -> bool:
    """원문을 봐야 하는 칸이 있는가 — 화면이 그 칸 옆에 원문 링크를 붙인다."""
    return any(getattr(item, name) == NEEDS_SOURCE for name in GROUP_FIELDS)
