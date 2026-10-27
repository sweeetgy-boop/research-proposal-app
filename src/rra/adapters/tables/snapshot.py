"""크롤 스냅샷 첨부 → ParsedTable (korail_web). 파일은 샌드박스 자식에서만 연다 (보안 B).

- xlsx·xls: `_worker` 시트 격자(문자열) → 시트마다 표 하나.
- pdf: `pdf_pages`(쪽별 텍스트) → 숫자가 있는 쪽마다 본문 줄 표 하나 (규칙이 정렬된 숫자 줄만
  사실로).
- doc_id 는 자료원 어댑터(`korail_web/source.py`)와 같은 `korail_web:<sha256 앞 16자>` — 검증한
  파일의 실제 해시를 쓴다. 같은 sha 가 여러 항목에 걸리면 한 번만.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.korail_web.snapshot import SnapshotDir, latest_snapshot, read_manifest
from rra.domain.models import ParsedTable

logger = logging.getLogger("rra.tables.snapshot")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
SHEET_FORMATS = frozenset({"xlsx", "xls"})
PDF_FORMATS = frozenset({"pdf"})
PARSEABLE = SHEET_FORMATS | PDF_FORMATS
DOC_ID_HASH_CHARS = 16
MAX_SHEET_ROWS = 5000
_DIGIT = re.compile(r"\d")


class _Sheet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(max_length=100)
    rows: list[list[str | None]] = Field(max_length=200_000)


class _Sheets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sheets: list[_Sheet] = Field(max_length=50)


class _Pages(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages: list[str] = Field(max_length=600)


class SnapshotTables:
    """TableSourcePort. name 은 Document.source 와 같다 (doc_id 접두어)."""

    def __init__(
        self,
        root: Path,
        *,
        limits: SandboxLimits,
        snapshot: str | None = None,
        source: str = "korail_web",
        runner: Runner = run_parser,
    ):
        self.root = Path(root)
        self.limits = limits
        self.snapshot_day = snapshot
        self.name = source
        self._runner = runner

    def snapshot(self) -> SnapshotDir | None:
        if self.snapshot_day:
            snap = SnapshotDir(self.root, self.snapshot_day)
            return snap if snap.manifest.is_file() else None
        return latest_snapshot(self.root)

    async def tables(self, *, limit: int | None = None) -> list[ParsedTable]:
        snap = self.snapshot()
        if snap is None:
            return []
        out: list[ParsedTable] = []
        seen: set[str] = set()
        for rec in read_manifest(snap).values():
            if rec.get("removed"):
                continue
            for att in rec.get("attachments") or []:
                if limit is not None and len(out) >= limit:
                    return out[:limit]
                if not att.get("downloaded") or not att.get("path"):
                    continue
                if str(att.get("ext") or "").lower() not in PARSEABLE:
                    continue
                sha = str(att.get("sha256") or "")
                if sha in seen:
                    continue
                seen.add(sha)
                base_day = str(att.get("snapshot") or snap.day)
                path = self.root / "snapshots" / base_day / str(att["path"])
                title = str(att.get("name") or rec.get("title") or "")
                out.extend(await self._tables_of(path, title))
        return out if limit is None else out[:limit]

    async def _tables_of(self, path: Path, title: str) -> list[ParsedTable]:
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning("tables.rejected error=%s", type(exc).__name__)
            return []
        doc_id = f"{self.name}:{vf.sha256[:DOC_ID_HASH_CHARS]}"
        with vf:
            fmt = "pdf_pages" if vf.fmt in PDF_FORMATS else vf.fmt
            try:
                raw = await self._runner(vf.fd, fmt, self.limits)
                if fmt == "pdf_pages":
                    return _pdf_tables(_Pages.model_validate(raw), doc_id, title)
                return _sheet_tables(_Sheets.model_validate(raw), doc_id, title)
            except (SandboxError, ValidationError) as exc:
                logger.warning("tables.rejected error=%s sha=%s", type(exc).__name__, vf.sha256[:8])
                return []


def _sheet_tables(sheets: _Sheets, doc_id: str, title: str) -> list[ParsedTable]:
    return [
        ParsedTable(
            doc_id=doc_id,
            rows=sheet.rows[:MAX_SHEET_ROWS],
            sheet=sheet.name[:120],
            title=f"{title} {sheet.name}"[:300],
        )
        for sheet in sheets.sheets
        if sheet.rows
    ]


def _pdf_tables(pages: _Pages, doc_id: str, title: str) -> list[ParsedTable]:
    out: list[ParsedTable] = []
    for i, text in enumerate(pages.pages):
        if not _DIGIT.search(text):
            continue
        out.append(
            ParsedTable(
                doc_id=doc_id,
                lines=[ln for ln in text.splitlines() if ln.strip()],
                page=i + 1,
                title=title[:300],
            )
        )
    return out
