"""스냅샷 → Document (SourcePort `korail_web`).

최신 스냅샷의 manifest.jsonl 을 읽어 항목 본문(개인정보 제거된 .txt)과 첨부(샌드박스 파싱)를 문서로
만든다.
- 같은 문서가 여러 메뉴·첨부에 겹치면 sha256 으로 한 번만 (먼저 나온 메뉴 경로가 남고 나머지는
  raw.also_in).
- doc_type 은 메뉴 설정(policy | korail_news), visibility public, text_basis full_text,
  orgs ["korail"].
- raw.crawl_snapshot=<날짜>, raw.menu_path, raw.url, raw.terms(공공누리 유형), raw.text_layer(PDF),
  raw.removed.
- "원본 삭제됨" 항목은 적재하지 않는다 (기존 저장본은 그대로 둔다).
저장 전 본문은 다시 strip_pii 를 거친다 (첨부 텍스트는 크롤 단계에서 열지 않았기 때문).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.korail_web._sheets import sheets_to_text
from rra.adapters.sources.korail_web.crawler import MenuSpec
from rra.adapters.sources.korail_web.snapshot import SnapshotDir, latest_snapshot, read_manifest
from rra.domain.models import Document
from rra.domain.rules.doc_category import CLASS_KEY, classify_korail

logger = logging.getLogger("rra.sources.korail_web")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"pdf", "hwp", "hwpx", "xlsx", "xls"})
MIN_CHARS = 80  # 이보다 짧은 본문(메뉴 링크 목록 등)은 적재하지 않는다
_YEAR = re.compile(r"(20\d{2}|19\d{2})")
DOC_TYPES = frozenset(
    {"policy", "korail_news", "statistics", "procurement"}
)  # statistics: 통계자료 게시판 xlsx (P2-3). procurement: 사전정보공표 연구용역(ADR 0040)


class KorailWebSource:
    """SourcePort. search() 는 query 를 쓰지 않는다 — 스냅샷 전체를 순서대로."""

    source = "korail_web"

    def __init__(
        self,
        root: Path,
        *,
        limits: SandboxLimits,
        menus: Mapping[str, MenuSpec] | None = None,
        snapshot: str | None = None,
        runner: Runner = run_parser,
    ):
        self.root = Path(root)
        self.limits = limits
        self.menus = dict(menus or {})
        self.snapshot_day = snapshot
        self._runner = runner

    def __repr__(self) -> str:
        return "KorailWebSource()"

    async def aclose(self) -> None:
        return None

    def snapshot(self) -> SnapshotDir | None:
        if self.snapshot_day:
            snap = SnapshotDir(self.root, self.snapshot_day)
            return snap if snap.manifest.is_file() else None
        return latest_snapshot(self.root)

    def status(self) -> dict[str, Any]:
        """자료원 상태 표시용 — 스냅샷 날짜·항목 수 (없으면 {"snapshot": None})."""
        snap = self.snapshot()
        if snap is None:
            return {"snapshot": None, "items": 0}
        items = read_manifest(snap)
        return {
            "snapshot": snap.day,
            "items": sum(1 for r in items.values() if not r.get("removed")),
            "removed": sum(1 for r in items.values() if r.get("removed")),
            "manifest": str(snap.manifest),
        }

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        snap = self.snapshot()
        if snap is None:
            return []
        out: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for rec in read_manifest(snap).values():
            if len(out) >= limit:
                break
            if rec.get("removed"):
                continue
            page_raw = self._page_raw(snap, rec)
            if page_raw is not None:
                self._add(out, seen, page_raw)
            for att in rec.get("attachments") or []:
                if len(out) >= limit:
                    break
                if not att.get("downloaded") or not att.get("path"):
                    continue
                raw = await self._attachment_raw(snap, rec, att)
                if raw is not None:
                    self._add(out, seen, raw)
        return out

    @staticmethod
    def _add(
        out: list[dict[str, Any]], seen: dict[str, dict[str, Any]], raw: dict[str, Any]
    ) -> None:
        key = raw["sha256"]
        if key in seen:
            seen[key].setdefault("also_in", []).append(raw["menu_path"])
            return
        seen[key] = raw
        out.append(raw)

    def _page_raw(self, snap: SnapshotDir, rec: dict[str, Any]) -> dict[str, Any] | None:
        rel = rec.get("text_file")
        if not isinstance(rel, str):
            return None
        path = snap.path / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if len(text.strip()) < MIN_CHARS:
            return None
        return {
            "kind": "page",
            "sha256": str(rec.get("text_sha256") or hashlib.sha256(text.encode()).hexdigest()),
            "text": text,
            "title": str(rec.get("title") or ""),
            "posted": rec.get("posted"),
            "url": rec.get("url"),
            "menu": rec.get("menu"),
            "menu_path": str(rec.get("menu_path") or ""),
            "doc_type": rec.get("doc_type"),
            "native_id": rec.get("native_id"),
            "terms": rec.get("terms"),
            "snapshot": snap.day,
            "department": rec.get("department"),
            "images": len(rec.get("images") or []),
        }

    async def _attachment_raw(
        self, snap: SnapshotDir, rec: dict[str, Any], att: dict[str, Any]
    ) -> dict[str, Any] | None:
        base_day = str(att.get("snapshot") or snap.day)
        path = self.root / "snapshots" / base_day / str(att["path"])
        ext = str(att.get("ext") or "").lower()
        if ext not in PARSEABLE:
            return None
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning(
                "korail_web.rejected error=%s sha=%s",
                type(exc).__name__,
                str(att.get("sha256", ""))[:8],
            )
            return None
        with vf:
            try:
                raw = await self._runner(vf.fd, vf.fmt, self.limits)
                sheet_text = sheets_to_text(raw)
                if sheet_text is not None:  # xlsx·xls: 시트 구조 → 본문 (표 줄)
                    raw = {"text": sheet_text, "toc": [], "pages": None}
                result = ExtractResult.model_validate(raw)
            except (SandboxError, ValidationError) as exc:
                logger.warning(
                    "korail_web.rejected error=%s sha=%s", type(exc).__name__, vf.sha256[:8]
                )
                return None
        if len(result.text.strip()) < MIN_CHARS:
            return None
        return {
            "kind": "attachment",
            "sha256": vf.sha256,
            "fmt": vf.fmt,
            "text": result.text,
            "toc": list(result.toc),
            "pages": result.pages,
            "title": str(att.get("name") or rec.get("title") or ""),
            "parent_title": str(rec.get("title") or ""),
            "posted": rec.get("posted"),
            "url": att.get("url"),
            "page_url": rec.get("url"),
            "menu": rec.get("menu"),
            "menu_path": str(rec.get("menu_path") or ""),
            "doc_type": rec.get("doc_type"),
            "native_id": rec.get("native_id"),
            "terms": rec.get("terms"),
            "snapshot": snap.day,
            "text_layer": att.get("text_layer"),
        }

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_korail_item(raw)

    def ingest_warnings(self, doc: Document) -> list[tuple[str, str]]:
        if doc.raw.get("text_layer") is False:
            return [("no_text_layer", str(doc.raw.get("file_name") or "")[:40])]
        return []


def _clean_name(name: str) -> str:
    """첨부 이름 → 문서 제목 (날짜 접두·확장자 제거)."""
    name = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name)
    name = re.sub(r"^\d{6}[_\s-]*", "", name)
    name = re.sub(r"^\(사전정보공표\)\s*", "", name)
    return " ".join(name.split())


def normalize_korail_item(raw: Mapping[str, Any]) -> Document:
    """순수 함수. 본문은 strip_pii 를 거친다. doc_type 은 메뉴 설정값을 자료 분류 규칙
    (domain/rules/doc_category, ADR 0040)으로 바로잡는다 — 사전정보공표 연구용역은 procurement +
    raw.doc_class research_service, 행정 공시·사업 현황은 admin_notice·status_report
    + raw.doc_class 로 정책 근거·경영전략 정합성 근거에서 빠진다(ADR 0046)."""
    doc_type = str(raw.get("doc_type") or "policy")
    if doc_type not in DOC_TYPES:
        raise ValueError(f"korail_web doc_type 은 {sorted(DOC_TYPES)}: {doc_type!r}")
    text = strip_pii(str(raw["text"])).strip()
    if not text:
        raise ValueError("본문 없음")
    kind = str(raw.get("kind") or "page")
    title = str(raw.get("title") or "").strip()
    if kind == "attachment":
        title = _clean_name(title) or str(raw.get("parent_title") or "").strip()
    if not title:
        title = text.splitlines()[0][:120]
    posted = raw.get("posted")
    pub = None
    if isinstance(posted, str):
        try:
            pub = date.fromisoformat(posted[:10])
        except ValueError:
            pub = None
    sha = str(raw["sha256"])
    extra: dict[str, Any] = {
        "kind": kind,
        "crawl_snapshot": raw.get("snapshot"),
        "menu": raw.get("menu"),
        "menu_path": raw.get("menu_path"),
        "native_id": raw.get("native_id"),
        "terms": raw.get("terms"),
        "sha256": sha,
    }
    if kind == "attachment":
        extra.update(
            file_name=str(raw.get("title") or ""),
            fmt=raw.get("fmt"),
            pages=raw.get("pages"),
            page_url=raw.get("page_url"),
            parent_title=raw.get("parent_title"),
            text_layer=raw.get("text_layer"),
        )
    if raw.get("also_in"):
        extra["also_in"] = list(raw["also_in"])
    if raw.get("department"):
        extra["department"] = strip_pii(str(raw["department"]))
    doc_type, category = classify_korail(
        doc_type=doc_type,
        title=title,
        raw=extra,
        url=str(raw.get("url") or "") or None,
    )
    if category:
        extra[CLASS_KEY] = category
    return Document(
        doc_id=f"korail_web:{sha[:16]}",
        source="korail_web",
        doc_type=doc_type,  # type: ignore[arg-type]
        title=title[:300],
        body=text,
        pub_date=pub,
        orgs=["korail"],
        lang="ko",
        url=str(raw.get("url") or "") or None,
        toc=[str(t) for t in (raw.get("toc") or [])][:200] or None,
        text_basis="full_text",
        visibility="public",
        raw=extra,
    )
