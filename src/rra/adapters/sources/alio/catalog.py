"""알리오 공시 카탈로그 — 공공데이터포털 `기획재정부_공공기관 연구보고서 공시` (fileData CSV).

- 기본: 사용자가 `data/catalog/` 에 CSV 를 넣는다.
- `fetch_catalog()`: sources.yaml 의 URL 을 GuardedClient 로 받아 같은 검증을 거쳐 저장한다.
- CSV 파싱은 샌드박스(`csv` 파서), 해석은 순수 함수 `normalize_catalog_row()`.
- 카탈로그의 URL 은 참고용이다. 알리오 본문은 robots.txt 때문에 자동으로 받지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._sandbox import SandboxLimits, run_parser
from rra.adapters.sources.alio._models import CatalogRows
from rra.adapters.sources.alio.filecheck import check_magic, open_validated
from rra.domain.models import CatalogEntry

# 필드 → 후보 헤더명. 실제 헤더는 fixture 를 보고
# config/sources.yaml 의 alio.catalog.columns 로 확정한다.
DEFAULT_COLUMNS: dict[str, list[str]] = {
    "catalog_id": ["공시번호", "게시물번호", "등록번호", "일련번호"],
    "institution_code": ["기관코드", "공공기관코드"],
    "institution_name": ["기관명", "공공기관명"],
    "title": ["제목", "보고서명", "연구보고서명", "연구과제명", "과제명"],
    "published": ["공시일", "공시일자", "등록일", "등록일자", "발간일", "작성일"],
    "url": ["URL", "상세URL", "링크", "상세링크"],
}
CSV_CONTENT_TYPES = frozenset(
    {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/octet-stream",
        "application/vnd.ms-excel",
    }
)
MAX_TITLE_CHARS = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ID_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_DATE = re.compile(r"^(\d{4})[-./]?(\d{1,2})(?:[-./]?(\d{1,2}))?")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]


def _clean(value: Any, limit: int = MAX_TITLE_CHARS) -> str:
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


def _pick(row: Mapping[str, str], candidates: Sequence[str]) -> str:
    for name in candidates:
        if value := (row.get(name) or "").strip():
            return value
    return ""


def _parse_date(value: str) -> date | None:
    m = _DATE.match(value.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    except ValueError:
        return None


def catalog_id_for(raw_id: str, inst_code: str, title: str, published: str) -> str:
    """카탈로그 id — 파일명 stem·doc_id 로 쓰이므로 [A-Za-z0-9_-] 만.

    원본 id 컬럼이 없으면 (기관, 제목, 공시일) 해시로 안정적인 id 를 만든다.
    """
    if safe := _ID_UNSAFE.sub("", raw_id)[:64]:
        return safe
    basis = "\x1f".join((inst_code, title, published)).encode()
    return "h" + hashlib.sha256(basis).hexdigest()[:15]


def normalize_catalog_row(
    row: Mapping[str, str],
    columns: Mapping[str, Sequence[str]],
    institutions: Sequence[Mapping[str, str]],
) -> CatalogEntry | None:
    """순수 함수. 대상 기관(코드 또는 기관명 일치)이 아니거나 제목이 없으면 None."""
    code = _pick(row, columns.get("institution_code", ()))
    name = "".join(_pick(row, columns.get("institution_name", ())).split())
    inst = next(
        (
            i
            for i in institutions
            if (code and code == i.get("code")) or (name and name == "".join(i["name"].split()))
        ),
        None,
    )
    if inst is None:
        return None
    title = _clean(_pick(row, columns.get("title", ())))
    if not title:
        return None
    published_raw = _pick(row, columns.get("published", ()))
    url = _pick(row, columns.get("url", ()))
    return CatalogEntry(
        catalog_id=catalog_id_for(
            _pick(row, columns.get("catalog_id", ())), inst.get("code", ""), title, published_raw
        ),
        institution_tag=inst["tag"],
        title=title,
        published=_parse_date(published_raw),
        url=url[:500] if url.startswith("https://") else None,
    )


def latest_csv(catalog_dir: Path) -> Path | None:
    if not catalog_dir.is_dir():
        return None
    files = [p for p in catalog_dir.iterdir() if p.suffix.lower() == ".csv" and p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


class FileCatalog:
    """CatalogPort 구현. `catalog_dir` 의 가장 최근 CSV 를 읽는다 (인스턴스당 1회)."""

    def __init__(
        self,
        catalog_dir: Path,
        *,
        limits: SandboxLimits,
        institutions: Sequence[Mapping[str, str]],
        columns: Mapping[str, Sequence[str]] | None = None,
        runner: Runner = run_parser,
    ):
        self.catalog_dir = Path(catalog_dir)
        self.limits = limits
        self.institutions = list(institutions)
        self.columns = {**DEFAULT_COLUMNS, **(columns or {})}
        self._runner = runner
        self._cache: list[CatalogEntry] | None = None

    def __repr__(self) -> str:
        return "FileCatalog()"

    async def entries(self) -> list[CatalogEntry]:
        if self._cache is None:
            self._cache = await self._load()
        return list(self._cache)

    async def _load(self) -> list[CatalogEntry]:
        path = latest_csv(self.catalog_dir)
        if path is None:
            return []
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        with open_validated(path, max_bytes=max_bytes, allowed=frozenset({"csv"})) as vf:
            parsed = CatalogRows.model_validate(await self._runner(vf.fd, "csv", self.limits))
        seen: dict[str, CatalogEntry] = {}
        for row in parsed.rows:
            entry = normalize_catalog_row(row, self.columns, self.institutions)
            if entry is not None:
                seen.setdefault(entry.catalog_id, entry)
        return list(seen.values())


async def fetch_catalog(
    client: GuardedClient, url: str, catalog_dir: Path, *, max_bytes: int
) -> Path:
    """카탈로그 CSV 다운로드 → 텍스트 검증 → `<sha256 16자>.csv` 로 원자적 저장(0600)."""
    body = await client.get_bytes(url, accept_types=CSV_CONTENT_TYPES)
    if not body or len(body) > max_bytes:
        raise ValueError("카탈로그 크기가 허용 범위를 벗어났습니다.")
    check_magic("csv", body[:65536])
    catalog_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = catalog_dir / f"{hashlib.sha256(body).hexdigest()[:16]}.csv"
    tmp = catalog_dir / f".{dest.name}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest
