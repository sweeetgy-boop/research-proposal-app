"""MolitPolicySource — 질의별 목록 → 상세 → 첨부(샌드박스) → raw. normalize 는 순수."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pydantic import ValidationError

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient
from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.molit._html import MolitRow, parse_detail, parse_list
from rra.domain.models import Document
from rra.domain.rules.editions import mark_editions, valid_until_of

logger = logging.getLogger("rra.sources.molit")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"pdf", "hwp", "hwpx"})
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")
MIN_CHARS = 80


class MolitPolicySource:
    """SourcePort + ProbingSource. source='molit', doc_type='policy'."""

    source = "molit"

    def __init__(
        self,
        client: GuardedClient,
        *,
        base_url: str = "https://www.molit.go.kr",
        list_path: str = "/USR/policyData/m_34681/lst.jsp",
        queries: Sequence[str] = (),
        store_dir: Path = Path("data/molit"),
        limits: SandboxLimits,
        max_pages: int = 5,
        max_file_bytes: int = 50 * 1024 * 1024,
        runner: Runner = run_parser,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.list_path = list_path
        self.queries = list(queries)
        self.store_dir = Path(store_dir)
        self.limits = limits
        self.max_pages = max_pages
        self.max_file_bytes = max_file_bytes
        self._runner = runner

    def __repr__(self) -> str:
        return f"MolitPolicySource(queries={len(self.queries)})"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def probe(self) -> dict[str, Any]:
        rows, total, last = await self._list(self.queries[0] if self.queries else "철도", 1)
        return {"total": total, "rows": len(rows), "pages": last}

    def _list_url(self, query: str, page: int) -> str:
        q = urlencode({"search": query, "srch_usr_titl": "Y", "psize": 10, "lcmspage": page})
        return f"{self.base_url}{self.list_path}?{q}"

    async def _list(self, query: str, page: int) -> tuple[list[MolitRow], int | None, int]:
        url = self._list_url(query, page)
        _h, body, _s = await self.client.get_raw(url)
        return parse_list(body.decode("utf-8", "replace"), url)

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """질의마다 목록(최대 max_pages 쪽) → 상세 → 첨부 파싱. 제목으로 판(edition)을 표시한다."""
        queries = [query] if query else self.queries
        rows: dict[str, MolitRow] = {}
        for q in queries:
            page = 1
            while page <= self.max_pages:
                try:
                    found, _total, last = await self._list(q, page)
                except (FetchError, BlockedURL) as exc:
                    logger.warning("molit.list_failed error=%s", type(exc).__name__)
                    break
                for r in found:
                    rows.setdefault(r.id, r)
                if page >= last or not found:
                    break
                page += 1
        marked = mark_editions(
            [{"id": r.id, "title": r.title, "posted": r.posted} for r in rows.values()]
        )
        editions = {m["id"]: m.get("edition") for m in marked}
        out: list[dict[str, Any]] = []
        for r in rows.values():
            if len(out) >= limit:
                break
            try:
                _h, body, _s = await self.client.get_raw(r.url)
            except (FetchError, BlockedURL) as exc:
                logger.warning("molit.detail_failed error=%s id=%s", type(exc).__name__, r.id)
                continue
            detail = parse_detail(body.decode("utf-8", "replace"), r.url)
            base = {
                "id": r.id,
                "url": r.url,
                "title": detail.title or r.title,
                "posted": detail.posted or r.posted,
                "category": detail.category or r.category,
                "department": detail.department,
                "edition": editions.get(r.id),
            }
            for name, url in detail.attachments:
                if len(out) >= limit:
                    break
                raw = await self._attachment(name, url)
                if raw is not None:
                    out.append({**base, **raw, "kind": "attachment"})
            if detail.body and len(detail.body.strip()) >= MIN_CHARS and len(out) < limit:
                out.append(
                    {
                        **base,
                        "kind": "page",
                        "text": detail.body,
                        "sha256": hashlib.sha256(detail.body.encode()).hexdigest(),
                    }
                )
        return out

    async def _attachment(self, name: str, url: str) -> dict[str, Any] | None:
        m = _EXT.search(name)
        ext = m.group(1).lower() if m else ""
        if ext not in PARSEABLE:
            return None
        try:
            _h, body, _s = await self.client.get_raw(url)
        except (FetchError, BlockedURL) as exc:
            logger.warning("molit.file_failed error=%s", type(exc).__name__)
            return None
        if len(body) > self.max_file_bytes:
            return None
        sha = hashlib.sha256(body).hexdigest()
        self.store_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.store_dir / f"{sha}.{ext}"
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(body)
        try:
            vf = open_validated(path, max_bytes=self.max_file_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning("molit.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(
                    await self._runner(vf.fd, vf.fmt, self.limits)
                )
            except (SandboxError, ValidationError) as exc:
                logger.warning("molit.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
                return None
        if len(result.text.strip()) < MIN_CHARS:
            return None
        return {
            "sha256": sha,
            "fmt": vf.fmt,
            "file_name": name,
            "file_url": url,
            "text": result.text,
            "toc": list(result.toc),
            "pages": result.pages,
        }

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_molit_item(raw)


def normalize_molit_item(raw: dict[str, Any]) -> Document:
    text = strip_pii(str(raw["text"])).strip()
    if not text:
        raise ValueError("본문 없음")
    posted = raw.get("posted")
    pub = date.fromisoformat(str(posted)[:10]) if isinstance(posted, str) and posted else None
    sha = str(raw["sha256"])
    edition = raw.get("edition") or None
    extra: dict[str, Any] = {
        "kind": raw.get("kind", "attachment"),
        "molit_id": raw.get("id"),
        "category": raw.get("category"),
        "department": raw.get("department"),
        "file_name": raw.get("file_name"),
        "fmt": raw.get("fmt"),
        "pages": raw.get("pages"),
        "page_url": raw.get("url"),
        "sha256": sha,
    }
    if edition:
        extra["edition"] = dict(edition)
    return Document(
        doc_id=f"molit:{sha[:16]}",
        source="molit",
        doc_type="policy",
        title=str(raw.get("title") or "")[:300] or text.splitlines()[0][:120],
        body=text,
        pub_date=pub,
        orgs=["molit"],
        lang="ko",
        url=str(raw.get("file_url") or raw.get("url") or "") or None,
        toc=[str(t) for t in (raw.get("toc") or [])][:200] or None,
        text_basis="full_text",
        valid_until=valid_until_of({"edition": edition}) if edition else None,
        visibility="public",
        raw=extra,
    )
