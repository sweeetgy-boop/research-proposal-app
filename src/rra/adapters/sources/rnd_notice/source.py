"""RndNoticeSource — 최신 스냅샷(data/rnd_notice/snapshots/<날짜>/) → 공고 1건 = Document 1건.

본문 = 상세 본문(IRIS 인라인 공고문) + 첨부 파싱 텍스트(KAIA 공고문 PDF·안내서, 샌드박스). 중복
레코드(duplicate_of)는
원 레코드의 `also_in` URL 로 합친다. normalize 는 순수(개인정보 제거 포함). valid_until = 접수
마감일.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.korail_web.snapshot import SnapshotDir, latest_snapshot, read_manifest
from rra.domain.models import Document
from rra.domain.rules.notices import parse_date

logger = logging.getLogger("rra.sources.rnd_notice")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"pdf", "hwp", "hwpx"})
MIN_CHARS = 80
MAX_BODY_CHARS = 300_000


class RndNoticeSource:
    """SourcePort. search() 는 query 를 쓰지 않는다 — 스냅샷 전체를 순서대로."""

    source = "rnd_notice"

    def __init__(
        self,
        root: Path,
        *,
        limits: SandboxLimits,
        snapshot: str | None = None,
        runner: Runner = run_parser,
    ):
        self.root = Path(root)
        self.limits = limits
        self.snapshot_day = snapshot
        self._runner = runner

    def __repr__(self) -> str:
        return "RndNoticeSource()"

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
        items = read_manifest(snap)
        return {
            "snapshot": snap.day,
            "items": sum(1 for r in items.values() if not r.get("duplicate_of")),
            "duplicates": sum(1 for r in items.values() if r.get("duplicate_of")),
            "manifest": str(snap.manifest),
        }

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        snap = self.snapshot()
        if snap is None:
            return []
        records = read_manifest(snap)
        also_in: dict[str, list[str]] = {}
        for rec in records.values():
            primary = rec.get("duplicate_of")
            if isinstance(primary, str) and rec.get("url"):
                also_in.setdefault(primary, []).append(str(rec["url"]))
        out: list[dict[str, Any]] = []
        for native_id, rec in records.items():
            if len(out) >= limit:
                break
            if rec.get("duplicate_of"):
                continue
            raw = await self._raw(snap, rec, also_in.get(native_id, []))
            if raw is not None:
                out.append(raw)
        return out

    async def _raw(
        self, snap: SnapshotDir, rec: dict[str, Any], also_in: list[str]
    ) -> dict[str, Any] | None:
        parts: list[str] = []
        rel = rec.get("text_file")
        if isinstance(rel, str):
            try:
                parts.append((snap.path / rel).read_text(encoding="utf-8"))
            except OSError:
                pass
        parsed: list[str] = []
        atts = sorted(
            rec.get("attachments") or [],
            key=lambda a: 0 if "공고문" in str(a.get("name") or "") else 1,
        )
        for att in atts:
            if not att.get("downloaded") or not att.get("path"):
                continue
            text = await self._attachment_text(att)
            if text:
                parts.append(f"[첨부: {att.get('name')}]\n{text}")
                parsed.append(str(att.get("name") or ""))
        body = "\n\n".join(p for p in parts if p.strip())[:MAX_BODY_CHARS]
        if len(body.strip()) < MIN_CHARS:
            return None
        return {
            "native_id": rec.get("native_id"),
            "site": rec.get("site"),
            "title": rec.get("title"),
            "posted": rec.get("posted"),
            "start": rec.get("start"),
            "deadline": rec.get("deadline"),
            "period": rec.get("period"),
            "program": rec.get("program"),
            "agency": rec.get("agency"),
            "ministry": rec.get("ministry"),
            "status": rec.get("status"),
            "notice_no": rec.get("notice_no"),
            "url": rec.get("url"),
            "also_in": also_in,
            "attachments": [str(a.get("name") or "") for a in rec.get("attachments") or []],
            "parsed_attachments": parsed,
            "terms": rec.get("terms"),
            "snapshot": snap.day,
            "key": rec.get("key"),
            "text": body,
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }

    async def _attachment_text(self, att: dict[str, Any]) -> str | None:
        base_day = str(att.get("snapshot") or "")
        path = self.root / "snapshots" / base_day / str(att["path"])
        ext = str(att.get("ext") or "").lower()
        if ext not in PARSEABLE:
            return None
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning("rnd_notice.rejected error=%s", type(exc).__name__)
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(
                    await self._runner(vf.fd, vf.fmt, self.limits)
                )
            except (SandboxError, ValidationError) as exc:
                logger.warning("rnd_notice.rejected error=%s", type(exc).__name__)
                return None
        return result.text if len(result.text.strip()) >= MIN_CHARS else None

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_notice(raw)


def normalize_notice(raw: dict[str, Any]) -> Document:
    text = strip_pii(str(raw.get("text") or "")).strip()
    if not text:
        raise ValueError("본문 없음")
    key = str(raw.get("key") or hashlib.sha256(text.encode()).hexdigest()[:16])
    posted = parse_date(str(raw.get("posted") or ""))
    deadline = parse_date(str(raw.get("deadline") or ""))
    start = parse_date(str(raw.get("start") or ""))
    agency = str(raw.get("agency") or "") or None
    title = strip_pii(str(raw.get("title") or ""))[:300] or text.splitlines()[0][:120]
    notice = {
        "agency": agency,
        "ministry": raw.get("ministry"),
        "program": raw.get("program"),
        "deadline": deadline.isoformat() if deadline else None,
        "start": start.isoformat() if start else None,
        "period": raw.get("period"),
        "status": raw.get("status"),
        "notice_no": raw.get("notice_no"),
        "site": raw.get("site"),
        "also_in": list(raw.get("also_in") or []),
        "attachments": list(raw.get("attachments") or []),
        "parsed_attachments": list(raw.get("parsed_attachments") or []),
    }
    return Document(
        doc_id=f"rnd_notice:{key}",
        source="rnd_notice",
        doc_type="rnd_notice",
        title=title,
        body=text,
        pub_date=posted,
        orgs=["molit"] if raw.get("ministry") == "국토교통부" else [],
        lang="ko",
        url=str(raw.get("url") or "") or None,
        text_basis="full_text",
        valid_until=deadline,
        visibility="public",
        raw={
            "notice": notice,
            "native_id": raw.get("native_id"),
            "crawl_snapshot": raw.get("snapshot"),
            "terms": raw.get("terms"),
            "sha256": raw.get("sha256"),
        },
    )
