"""BaiAuditSource — 감사원 스냅샷(manifest.jsonl + 전문 PDF) → Document (source bai, doc_type
audit)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.audit._common import orgs_in_title
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.korail_web.snapshot import SnapshotDir, latest_snapshot, read_manifest
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.bai")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"pdf", "hwp", "hwpx"})
MIN_CHARS = 80


class BaiAuditSource:
    """SourcePort. search() 는 query 를 쓰지 않는다 — 최신 스냅샷 전체."""

    source = "bai"

    def __init__(
        self,
        root: Path,
        *,
        limits: SandboxLimits,
        institutions: Sequence[Mapping[str, Any]] = (),
        snapshot: str | None = None,
        max_file_bytes: int = 50 * 1024 * 1024,
        runner: Runner = run_parser,
    ):
        self.root = Path(root)
        self.limits = limits
        self.institutions = list(institutions)
        self.snapshot_day = snapshot
        self.max_file_bytes = max_file_bytes
        self._runner = runner

    def __repr__(self) -> str:
        return "BaiAuditSource()"

    async def aclose(self) -> None:
        return None

    def snapshot(self) -> SnapshotDir | None:
        if self.snapshot_day:
            snap = SnapshotDir(self.root, self.snapshot_day)
            return snap if snap.manifest.is_file() else None
        return latest_snapshot(self.root)

    def status(self) -> dict[str, Any]:
        snap = self.snapshot()
        if snap is None:
            return {"snapshot": None, "items": 0}
        return {
            "snapshot": snap.day,
            "items": len(read_manifest(snap)),
            "manifest": str(snap.manifest),
        }

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        snap = self.snapshot()
        if snap is None:
            return []
        out: list[dict[str, Any]] = []
        for rec in read_manifest(snap).values():
            if len(out) >= limit:
                break
            raw = await self._record_raw(snap, rec)
            if raw is not None:
                out.append(raw)
        return out

    async def _record_raw(self, snap: SnapshotDir, rec: dict[str, Any]) -> dict[str, Any] | None:
        """전문(pdf) 우선, 없으면 받은 첫 파일. 한 건 = 문서 1개."""
        files = [f for f in rec.get("files") or [] if f.get("downloaded") and f.get("path")]
        files.sort(key=lambda f: 0 if str(f.get("ext")) == "pdf" else 1)
        for f in files:
            ext = str(f.get("ext") or "").lower()
            if ext not in PARSEABLE:
                continue
            path = snap.path / str(f["path"])
            try:
                vf = open_validated(path, max_bytes=self.max_file_bytes, allowed=PARSEABLE)
            except (FileRejected, OSError) as exc:
                logger.warning(
                    "bai.rejected error=%s id=%s", type(exc).__name__, rec.get("native_id")
                )
                continue
            with vf:
                try:
                    result = ExtractResult.model_validate(
                        await self._runner(vf.fd, vf.fmt, self.limits)
                    )
                except (SandboxError, ValidationError) as exc:
                    logger.warning(
                        "bai.rejected error=%s id=%s", type(exc).__name__, rec.get("native_id")
                    )
                    continue
            if len(result.text.strip()) < MIN_CHARS:
                continue
            return {
                **rec,
                "text": result.text,
                "toc": list(result.toc),
                "pages": result.pages,
                "file_name": f.get("name"),
                "sha256": f.get("sha256"),
                "fmt": vf.fmt,
            }
        return None

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_bai_record(raw, institutions=self.institutions)


def normalize_bai_record(
    raw: Mapping[str, Any], *, institutions: Sequence[Mapping[str, Any]] = ()
) -> Document:
    text = strip_pii(str(raw["text"])).strip()
    if not text:
        raise ValueError("본문 없음")
    title = str(raw.get("title") or "")[:300] or text.splitlines()[0][:120]
    posted = raw.get("posted")
    pub = date.fromisoformat(str(posted)[:10]) if isinstance(posted, str) and posted else None
    return Document(
        doc_id=f"bai:{raw['native_id']}",
        source="bai",
        doc_type="audit",
        title=title,
        body=text,
        pub_date=pub,
        orgs=orgs_in_title(title, institutions),
        lang="ko",
        url=str(raw.get("url") or "") or None,
        toc=[str(t) for t in (raw.get("toc") or [])][:200] or None,
        text_basis="full_text",
        visibility="public",
        raw={
            "audit_kind": raw.get("kind"),
            "audit_field": raw.get("field"),
            "bai_department": raw.get("bai_department"),
            "query": raw.get("query"),
            "file_name": raw.get("file_name"),
            "sha256": raw.get("sha256"),
            "fmt": raw.get("fmt"),
            "pages": raw.get("pages"),
            "terms": raw.get("terms"),
            "crawl_snapshot": raw.get("snapshot"),
        },
    )
