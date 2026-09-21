"""OpenAlex 어댑터 (키 불필요). SourcePort 구현.

- 네트워크는 GuardedClient(보안 C)로만 쓴다.
- normalize() 는 순수 함수: 응답 dict → Document. 결과 텍스트는 비신뢰(A)로 남는다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.domain.models import Document

BASE_URL = "https://api.openalex.org"
MAX_PER_PAGE = 200
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
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.per_page = max(1, min(per_page, MAX_PER_PAGE))
        self.default_query = default_query
        self.lookback_days = lookback_days
        self.query_max_chars = query_max_chars
        self.mailto = mailto
        self._today = today

    def __repr__(self) -> str:
        return f"OpenAlexSource(base_url={self.base_url!r})"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """원본 응답 반환. query=None 이면 default_query + 최근 lookback_days 증분."""
        if limit <= 0:
            return []
        params: dict[str, Any] = {
            "select": SELECT,
            "per-page": min(self.per_page, limit),
            "cursor": "*",
        }
        if query is None:
            since = self._today() - timedelta(days=self.lookback_days)
            params["filter"] = f"from_publication_date:{since.isoformat()}"
            query = self.default_query
        text = _clean_text(query)[: self.query_max_chars]
        if text:
            params["search"] = text
        if self.mailto:
            params["mailto"] = self.mailto

        out: list[dict[str, Any]] = []
        while len(out) < limit:
            data = await self.client.get_json(f"{self.base_url}/works", params)
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                raise FetchError("OpenAlex 응답에 results 배열이 없습니다.")
            out.extend(r for r in results if isinstance(r, dict))
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not results or not isinstance(cursor, str) or not cursor:
                break
            params = {**params, "cursor": cursor}
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
        raw={"openalex_id": native, "type": raw.get("type")},
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
