"""문제 정의 카드 → 실제로 보내는 검색 질의와 그 지문 (ADR 0065, 계약 problem-card.md 4.1절).

0단계 계약 — 레인은 고치지 않는다(질의 구성을 바꿔야 하면 멈추고 보고). 순수 함수.

캐시·세션·메모가 **카드 전체가 아니라 실제로 보낸 질의**를 기준으로 갈리게 하는 한 곳이다.

- `card_queries` : 카드에서 만든 질의 묶음(저장 자료 질의·실시간 국문·영문·분류 코드).
  카드가 없거나 쓰임새가 꺼져 있으면 None — 호출자는 종전 방식(규칙 문제어)으로 돈다.
- `search_fingerprint` : 그 질의 묶음의 지문. 실시간 검색 **세션 소유자**(`analogy_owner`)와
  유추 메모 키에 넣는다. 기능 문장·사다리를 고쳐 질의가 바뀌면 지문이 바뀌어 이전 세션·메모가
  재사용되지 않는다. 질의에 들어가지 않는 칸(원인·모순 등)을 고쳐도 지문은 그대로다.
- `pick_fingerprint` : 검색 지문 + 최종 5건 정렬에 쓰는 값(문제어·재순위 질의·정렬 설정).
  유추 결과 메모 키에 넣는다.
- 카드가 없을 때 소유자·메모 키는 종전 값 그대로다(`analogy_owner(base, None) == base`).
  카드를 쓸 때는 늘 `:card:` 표식이 붙어 스위치 꺼짐(규칙 문제어) 때의 세션·메모와 섞이지 않는다.
- 자료원 응답 24시간 캐시(`live_search.cache_key`)는 원래 (자료원, 보낸 질의, 건수)가 키다.
  분류 코드 검색은 질의 문자열을 `class_query` 로 만들어("ipc:" 표식) 같은 글자의 키워드
  검색과 키가 겹치지 않게 한다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from rra.domain.models.problem_card import CardRank, ProblemCard
from rra.domain.rules.live_search import normalize_query

FINGERPRINT_VERSION = "card-queries:v1"
FINGERPRINT_CHARS = 16
CARD_OWNER_MARK = "card"
CLASS_QUERY_PREFIX = "ipc:"
MAX_STORED_QUERIES = 5
MAX_LIVE_QUERIES = 3


class CardQueries(BaseModel):
    """카드에서 만든, 실제로 보내는 질의 묶음."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stored: tuple[str, ...] = ()  # 저장 자료(벡터) 질의 — 사다리 3단 + 국문·영문 기능 문장
    live_ko: tuple[str, ...] = ()  # 실시간 국문 자료원 키워드 — 대상어+작용어 짝, 구체 단
    live_en: tuple[str, ...] = ()  # 실시간 영문 자료원(OpenAlex) 키워드
    ipc: tuple[str, ...] = ()  # KIPRIS 분류 검색에 쓰는 코드(확인된 것만)

    @property
    def empty(self) -> bool:
        return not (self.stored or self.live_ko or self.live_en or self.ipc)


def _unique(items: Iterable[str], limit: int) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        text = " ".join((raw or "").split())
        key = normalize_query(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text)
    return tuple(out[:limit])


def card_queries(
    card: ProblemCard | None,
    *,
    use_queries: bool = True,
    use_class: bool = True,
    max_live: int = MAX_LIVE_QUERIES,
) -> CardQueries | None:
    """카드 → 질의 묶음. None 이면 카드 기반 검색을 하지 않는다(종전 방식).

    use_queries: `use.analogy_queries` (맨 위 스위치 포함 — `ProblemCardConfig.uses`).
    use_class: `use.kipris_class`. 분류 코드는 `verified != "unverified"` 인 것만.
    """
    if card is None or not use_queries:
        return None
    ko, en = card.function_ko.value, card.function_en.value
    concrete, general = card.ladder_text("구체"), card.ladder_text("일반화")
    stored = _unique([concrete, general, card.ladder_text("추상화"), ko, en], MAX_STORED_QUERIES)
    # 실시간 국문 키워드는 짧은 "대상어 작용어" 짝 먼저 — 긴 구절은 국문 자료원(ScienceON 등)이
    # 낱말을 모두 요구해 0~4건만 돌려준다(2026-11-10 실제 카드 측정). 모자라면 구체 단.
    pairs_ko = [
        f"{obj} {act}" for obj in card.terms.objects_ko[:2] for act in card.terms.actions_ko[:1]
    ]
    live_ko = _unique([*pairs_ko, concrete, general, ko], max_live)
    pairs = [
        f"{obj} {act}" for obj in card.terms.objects_en[:2] for act in card.terms.actions_en[:1]
    ]
    live_en = _unique([*pairs, en], max_live)
    ipc = (
        _unique((c.code for c in card.ipc if c.verified != "unverified"), len(card.ipc))
        if use_class
        else ()
    )
    queries = CardQueries(stored=stored, live_ko=live_ko, live_en=live_en, ipc=ipc)
    return None if queries.empty else queries


def _digest(groups: Sequence[tuple[str, Iterable[str]]]) -> str:
    parts = [FINGERPRINT_VERSION]
    for label, values in groups:
        parts.append(label + "=" + "\x1f".join(normalize_query(v) for v in values))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]


def search_fingerprint(queries: CardQueries | None) -> str:
    """실제로 보내는 질의의 지문. 질의가 없으면(카드 없음) 빈 문자열."""
    if queries is None:
        return ""
    return _digest(
        [
            ("stored", queries.stored),
            ("ko", queries.live_ko),
            ("en", queries.live_en),
            ("ipc", queries.ipc),
        ]
    )


def rerank_query(card: ProblemCard) -> str:
    """재순위(cross-encoder) 질의 — 국문 기능 문장 + " / " + 영문 기능 문장."""
    return " / ".join(p for p in (card.function_ko.value, card.function_en.value) if p)


def pick_fingerprint(queries: CardQueries | None, card: ProblemCard | None, rank: CardRank) -> str:
    """검색 지문 + 최종 정렬에 쓰는 값의 지문 — 유추 결과 메모 키용. 카드가 없으면 빈 문자열."""
    if queries is None or card is None:
        return ""
    terms = card.terms
    return _digest(
        [
            ("search", [search_fingerprint(queries)]),
            ("objects", [*terms.objects_ko, *terms.objects_en]),
            ("actions", [*terms.actions_ko, *terms.actions_en]),
            ("rerank", [rerank_query(card)]),
            (
                "rank",
                [
                    str(rank.rerank_top),
                    str(rank.per_source),
                    str(rank.priority_window),
                    str(rank.priority_min_ratio),
                    str(rank.with_request_query),
                    str(rank.dup_title_ratio),
                    str(rank.weak_ratio),
                    str(rank.weak_keep_title_object),
                    *rank.dup_title_suffixes,
                    str(rank.require_object),
                ],
            ),
        ]
    )


def analogy_owner(base: str, queries: CardQueries | None) -> str:
    """실시간 검색 세션 소유자. 카드가 없으면 종전 값 그대로, 있으면 질의 지문을 붙인다 —
    `live_search.session_key(owner, req)` 가 입력 글만 보므로 질의가 바뀐 것을 여기서 가른다."""
    if queries is None:
        return base
    return f"{base}:{CARD_OWNER_MARK}:{search_fingerprint(queries)}"


def class_query(code: str) -> str:
    """분류 코드 검색의 캐시 키용 질의 문자열 — 같은 글자의 키워드 검색과 겹치지 않게 표식."""
    return CLASS_QUERY_PREFIX + " ".join((code or "").upper().split())


def memo_groups(fingerprint: str) -> list[list[str]]:
    """유추 메모 키(`novelty.input_key(req, core, *memo_groups(...))`)에 덧붙일 묶음.
    카드가 없으면(빈 지문) 덧붙이지 않는다 — 키가 종전과 같다."""
    return [[f"{CARD_OWNER_MARK}:{fingerprint}"]] if fingerprint else []
