"""DataGoKrFileSource — 데이터셋 페이지 → 2단계 내려받기 → 샌드박스 → raw → Document."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pydantic import ValidationError

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient
from rra.adapters.sources._orgs import org_tags
from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult, TextLines
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.datago._html import parse_dataset_page
from rra.adapters.sources.datago._table import csv_lines_to_table
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.datago")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"csv", "xlsx", "xls"})
_FILENAME = re.compile(r'filename\*?="?(?:UTF-8\'\')?([^";]+)', re.IGNORECASE)
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")


class DataGoKrFileSource:
    """SourcePort + ProbingSource. source='datago', doc_type='statistics'. 키 불필요."""

    source = "datago"

    def __init__(
        self,
        client: GuardedClient,
        *,
        datasets: Sequence[Mapping[str, Any]],
        base_url: str = "https://www.data.go.kr",
        store_dir: Path,
        limits: SandboxLimits,
        institutions: Sequence[Mapping[str, Any]] = (),
        max_file_bytes: int = 50 * 1024 * 1024,
        max_rows: int = 400,
        runner: Runner = run_parser,
    ):
        self.client = client
        self.datasets = [dict(d) for d in datasets if d.get("pk")]
        self.base_url = base_url.rstrip("/")
        self.store_dir = Path(store_dir)
        self.limits = limits
        self.institutions = list(institutions)
        self.max_file_bytes = max_file_bytes
        self.max_rows = max_rows
        self._runner = runner

    def __repr__(self) -> str:
        return f"DataGoKrFileSource(datasets={len(self.datasets)})"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def probe(self) -> dict[str, Any]:
        if not self.datasets:
            return {"datasets": 0}
        page = await self._page(str(self.datasets[0]["pk"]))
        return {"datasets": len(self.datasets), "first": page.title if page else None}

    async def _page(self, pk: str):
        url = f"{self.base_url}/data/{pk}/fileData.do"
        _h, body, _s = await self.client.get_raw(url)
        return parse_dataset_page(body.decode("utf-8", "replace"))

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """query 가 있으면 라벨·주제에 그 말이 든 데이터셋만."""
        out: list[dict[str, Any]] = []
        for ds in self.datasets:
            if len(out) >= limit:
                break
            if query and query not in f"{ds.get('label', '')} {ds.get('topic', '')}":
                continue
            pk = str(ds["pk"])
            try:
                page = await self._page(pk)
            except (FetchError, BlockedURL) as exc:
                logger.warning("datago.page_failed error=%s pk=%s", type(exc).__name__, pk)
                continue
            if page is None:
                logger.warning("datago.no_download_button pk=%s", pk)
                continue
            raw = await self._download(page)
            if raw is None:
                continue
            out.append(
                {
                    "pk": pk,
                    "topic": ds.get("topic"),
                    "label": ds.get("label"),
                    "url": f"{self.base_url}/data/{pk}/fileData.do",
                    "title": page.title,
                    "institution": page.institution,
                    "updated": page.updated,
                    "description": page.description,
                    "cycle": page.cycle,
                    "declared_rows": page.rows,
                    **raw,
                }
            )
        return out

    async def _download(self, page) -> dict[str, Any] | None:
        q = urlencode(
            {
                "publicDataPk": page.public_data_pk,
                "publicDataDetailPk": page.detail_pk,
                "fileDetailSn": page.file_sn,
            }
        )
        try:
            meta = await self.client.get_json(
                f"{self.base_url}/tcs/dss/selectFileDataDownload.do?{q}"
            )
        except (FetchError, BlockedURL) as exc:
            # 응답 content-type 이 text/html 인 JSON — get_json 이 거부하면 get_raw 로
            if not isinstance(exc, FetchError) or "JSON 이 아닌" not in str(exc):
                logger.warning("datago.meta_failed error=%s", type(exc).__name__)
                return None
            import json

            _h, body, _s = await self.client.get_raw(
                f"{self.base_url}/tcs/dss/selectFileDataDownload.do?{q}"
            )
            try:
                meta = json.loads(body)
            except ValueError:
                return None
        atch = str((meta or {}).get("atchFileId") or "")
        sn = str((meta or {}).get("fileDetailSn") or page.file_sn)
        if not atch or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", atch):
            logger.warning("datago.no_atch_id pk=%s", page.public_data_pk)
            return None
        q2 = urlencode({"atchFileId": atch, "fileDetailSn": sn})
        try:
            headers, body, _s = await self.client.get_raw(
                f"{self.base_url}/cmm/cmm/fileDownload.do?{q2}"
            )
        except (FetchError, BlockedURL) as exc:
            logger.warning("datago.file_failed error=%s", type(exc).__name__)
            return None
        if len(body) > self.max_file_bytes:
            return None
        fm = _FILENAME.search(headers.get("content-disposition", ""))
        from urllib.parse import unquote

        file_name = unquote(fm.group(1)).strip() if fm else f"{page.public_data_pk}.csv"
        em = _EXT.search(file_name)
        ext = em.group(1).lower() if em else (page.ext or "csv").lower().strip()
        if ext not in PARSEABLE:
            logger.warning("datago.unsupported_ext ext=%s", ext)
            return None
        sha = hashlib.sha256(body).hexdigest()
        self.store_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.store_dir / f"{sha}.{ext}"
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(body)
        fmt = "txt" if ext == "csv" else ext  # CSV 는 텍스트 디코드(utf-8-sig→cp949)만 샌드박스에서
        try:
            vf = open_validated(path, max_bytes=self.max_file_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning("datago.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
            return None
        with vf:
            try:
                result = await self._runner(vf.fd, fmt, self.limits)
                if fmt == "txt":
                    lines = TextLines.model_validate(result).lines
                    table, rows = csv_lines_to_table(lines, max_rows=self.max_rows)
                    pages = None
                else:
                    extracted = ExtractResult.model_validate(result)
                    table, rows, pages = extracted.text, None, extracted.pages
            except (SandboxError, ValidationError) as exc:
                logger.warning("datago.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
                return None
        if not table.strip():
            return None
        return {
            "sha256": sha,
            "fmt": ext,
            "file_name": file_name[:200],
            "table": table,
            "rows": rows,
            "pages": pages,
        }

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_datago_item(raw, institutions=self.institutions)


def normalize_datago_item(
    raw: Mapping[str, Any], *, institutions: Sequence[Mapping[str, Any]] = ()
) -> Document:
    table = str(raw.get("table") or "").strip()
    if not table:
        raise ValueError("표 없음")
    title = str(raw.get("title") or raw.get("label") or "")[:300]
    inst = str(raw.get("institution") or "").strip()
    head = [f"[통계 표] {title}"]
    if inst:
        head.append(f"제공기관: {inst}")
    if raw.get("updated"):
        head.append(f"수정일: {raw['updated']} / 갱신 주기: {raw.get('cycle') or '-'}")
    if raw.get("description"):
        head.append(f"설명: {strip_pii(str(raw['description']))[:1000]}")
    body = "\n".join(head) + "\n\n" + strip_pii(table)
    updated = raw.get("updated")
    pub = date.fromisoformat(str(updated)[:10]) if isinstance(updated, str) and updated else None
    return Document(
        doc_id=f"datago:{raw['pk']}",
        source="datago",
        doc_type="statistics",
        title=title or f"공공데이터 {raw['pk']}",
        abstract=str(raw.get("description") or "")[:2000] or None,
        body=body,
        pub_date=pub,
        orgs=org_tags([inst], institutions),
        lang="ko",
        url=str(raw.get("url") or "") or None,
        text_basis="full_text",
        visibility="public",
        raw={
            "public_data_pk": str(raw["pk"]),
            "topic": raw.get("topic"),
            "institution": inst or None,
            "cycle": raw.get("cycle"),
            "rows": raw.get("rows"),
            "declared_rows": raw.get("declared_rows"),
            "file_name": raw.get("file_name"),
            "fmt": raw.get("fmt"),
            "sha256": raw.get("sha256"),
            "terms": "이용허락범위 제한 없음(공공데이터포털 표기)",
        },
    )
