"""OpenAlex 어댑터 (키 불필요). SourcePort 구현.

- 네트워크는 GuardedClient(보안 C)로만 쓴다.
- normalize() 는 순수 함수: 응답 dict → Document. 결과 텍스트는 비신뢰(A)로 남는다.
- 질의 목록(config/sources.yaml openalex.queries, 분야별 영문 질의): search(None) 은 목록을 돌며
  질의마다 per_query_limit 까지 받고 같은 work 는 한 번만 둔다. 분야는 raw.field 로 남는다.
  기간은 증분이면 lookback_days, 전체 수집(full_window, CLI --full)이면 backfill_years.
  require_abstract 면 has_abstract 필터. 목록이 비면 예전처럼 default_query 하나.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.domain.models import Document

BASE_URL = "https://api.openalex.org"
MAX_PER_PAGE = 200
MAX_BASIC_RESULTS = 10_000  # page 페이징 상한 (OpenAlex)
SELECT = (
    "id,doi,display_name,publication_date,language,authorships,"
    "abstract_inverted_index,primary_location,type"
)
MAX_TITLE_CHARS = 500
MAX_ABSTRACT_CHARS = 10_000
MAX_ABSTRACT_WORDS = 5_000
MAX_ABSTRACT_POSITIONS = 100_000
MAX_AUTHORS = 100

_ID = re.compile(r"^W\d{1,15}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TAG = re.compile(r"</?[A-Za-z][^<>]{0,40}>")
_SPACES = re.compile(r"\s+")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:")


class OpenAlexSource:
    source = "openalex"

    def __init__(
        self,
        client: GuardedClient,
        *,
        base_url: str = BASE_URL,
        per_page: int = 100,
        default_query: str = "railway",
        lookback_days: int = 7,
        query_max_chars: int = 500,
        mailto: str | None = None,
        today: Callable[[], date] = date.today,
        queries: list[dict[str, str]] | None = None,
        backfill_years: int = 10,
        per_query_limit: int = 200,
        require_abstract: bool = True,
        api_key: SecretStr | None = None,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.per_page = max(1, min(per_page, MAX_PER_PAGE))
        self.default_query = default_query
        self.lookback_days = lookback_days
        self.query_max_chars = query_max_chars
        self.mailto = mailto
        self._today = today
        self.queries = [
            {"field": str(q.get("field") or ""), "query": str(q.get("query") or "")}
            for q in (queries or [])
            if isinstance(q, dict) and str(q.get("query") or "").strip()
        ]
        self.backfill_years = max(1, int(backfill_years))
        self.per_query_limit = max(1, int(per_query_limit))
        self.require_abstract = bool(require_abstract)
        self.full_window = False  # True 면 lookback_days 대신 backfill_years (CLI --full)
        self.api_key = api_key  # 선택. 있으면 요청 파라미터로만 (보안 D). 없으면 익명 page 페이징

    def __repr__(self) -> str:
        return f"OpenAlexSource(base_url={self.base_url!r})"

    async def aclose(self) -> None:
        await self.client.aclose()

    def window_filter(self) -> str:
        """증분(lookback_days) 또는 전체(backfill_years) 기간 + 초록 조건."""
        days = self.backfill_years * 365 if self.full_window else self.lookback_days
        since = self._today() - timedelta(days=days)
        parts = [f"from_publication_date:{since.isoformat()}"]
        if self.require_abstract:
            parts.append("has_abstract:true")
        return ",".join(parts)

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """원본 응답. query 가 있으면 그 질의 하나(기간 없음), None 이면 질의 목록×기간 조건."""
        if limit <= 0:
            return []
        if query is not None:
            return await self._search_one(query, limit, filter_expr=None)
        if not self.queries:
            return await self._search_one(
                self.default_query, limit, filter_expr=self.window_filter()
            )
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in self.queries:
            if len(out) >= limit:
                break
            page = await self._search_one(
                q["query"],
                min(self.per_query_limit, limit - len(out)),
                filter_expr=self.window_filter(),
            )
            for raw in page:
                key = str(raw.get("id") or "")
                if key in seen:
                    continue
                seen.add(key)
                out.append({**raw, "_field": q["field"]})
        return out[:limit]

    async def search_query(
        self, query: str, limit: int, *, require_abstract: bool = True
    ) -> list[dict[str, Any]]:
        """질의 하나(기간 없음) — [4] 실시간 검색용. require_abstract 면 has_abstract 필터."""
        if limit <= 0:
            return []
        return await self._search_one(
            query, limit, filter_expr="has_abstract:true" if require_abstract else None
        )

    async def _search_one(
        self, query: str, limit: int, *, filter_expr: str | None
    ) -> list[dict[str, Any]]:
        # page 페이징(최대 MAX_BASIC_RESULTS 건). cursor 페이징은 2026-10 부터 API 키 필요(401).
        per_page = min(self.per_page, limit)
        params: dict[str, Any] = {"select": SELECT, "per-page": per_page, "page": 1}
        if filter_expr:
            params["filter"] = filter_expr
        text = _clean_text(query)[: self.query_max_chars]
        if text:
            params["search"] = text
        if self.mailto:
            params["mailto"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key.get_secret_value()
        out: list[dict[str, Any]] = []
        page_no = 1
        while len(out) < limit and page_no * per_page <= MAX_BASIC_RESULTS:
            data = await self.client.get_json(f"{self.base_url}/works", {**params, "page": page_no})
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                raise FetchError("OpenAlex 응답에 results 배열이 없습니다.")
            out.extend(r for r in results if isinstance(r, dict))
            if len(results) < per_page:
                break
            page_no += 1
        return out[:limit]

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_work(raw)


def normalize_work(raw: dict[str, Any]) -> Document:
    """순수 함수. 필수 필드(id·제목)가 없으면 ValueError."""
    native = _native_id(raw.get("id"))
    title = _clean_text(raw.get("display_name") or raw.get("title"))[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"openalex:{native} 제목 없음")
    doi = _normalize_doi(raw.get("doi"))
    return Document(
        doc_id=f"openalex:{native}",
        source="openalex",
        doc_type="paper",
        title=title,
        abstract=_rebuild_abstract(raw.get("abstract_inverted_index")),
        pub_date=_parse_date(raw.get("publication_date")),
        authors=_authors(raw.get("authorships")),
        lang=raw["language"] if isinstance(raw.get("language"), str) else "und",
        text_basis="abstract",
        url=_landing_url(raw.get("primary_location"))
        or (f"https://doi.org/{doi}" if doi else None),
        doi=doi,
        raw={
            "openalex_id": native,
            "type": raw.get("type"),
            "field": _clean_text(raw.get("_field"))[:40] or None,  # 질의 목록의 분야 (적재 통계용)
        },
    )


def _native_id(value: Any) -> str:
    native = str(value or "").rsplit("/", 1)[-1]
    if not _ID.match(native):
        raise ValueError("OpenAlex work id 형식이 아닙니다.")
    return native


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = _CONTROL.sub(" ", value)
    text = _TAG.sub("", text)
    return _SPACES.sub(" ", text).strip()


def _rebuild_abstract(inverted: Any) -> str | None:
    """{단어: [위치...]} → 위치 순 문장. 위치 수·길이에 상한을 둔다."""
    if not isinstance(inverted, dict) or not inverted:
        return None
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        pairs.extend((p, word) for p in positions if isinstance(p, int) and p >= 0)
        if len(pairs) > MAX_ABSTRACT_POSITIONS:  # 비정상적으로 큰 입력은 여기서 끊는다
            break
    pairs.sort()
    text = _clean_text(" ".join(w for _, w in pairs[:MAX_ABSTRACT_WORDS]))
    return text[:MAX_ABSTRACT_CHARS] or None


def _normalize_doi(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    doi = value.strip().lower()
    for prefix in _DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi if doi.startswith("10.") else None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _authors(authorships: Any) -> list[str]:
    if not isinstance(authorships, list):
        return []
    names = []
    for a in authorships[:MAX_AUTHORS]:
        author = a.get("author") if isinstance(a, dict) else None
        name = _clean_text(author.get("display_name")) if isinstance(author, dict) else ""
        if name:
            names.append(name[:200])
    return names


def _landing_url(location: Any) -> str | None:
    if not isinstance(location, dict):
        return None
    url = location.get("landing_page_url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url[:2000]
    return None
