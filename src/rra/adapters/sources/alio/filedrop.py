"""알리오 filedrop — 수동 다운로드한 공시 보고서(`data/inbox/alio/`)를 적재한다.

파일마다: filecheck(확장자·크기·매직바이트) → 샌드박스 파싱 → 결과 재검증.
- 실패한 파일은 `_quarantine/`, 성공한 파일은 upsert 뒤 `_done/` (`_inbox.Inbox`).
- 카탈로그 매칭: 파일명 stem == catalog_id (`rra alio missing` 이 권장 파일명을 알려준다).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._inbox import Inbox, error_name, inbox_status
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.application.ports import CatalogPort
from rra.domain.models import CatalogEntry, Document

logger = logging.getLogger("rra.sources.alio")

__all__ = ["AlioSource", "NoTextLayer", "inbox_status", "normalize_report"]

FILE_FORMATS = frozenset({"pdf", "hwpx", "hwp"})
MAX_TITLE_CHARS = 200
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]


class NoTextLayer(ValueError):
    """텍스트가 없는 문서 (스캔 PDF 등). OCR 은 범위 밖."""


def _clean(value: Any, limit: int = MAX_TITLE_CHARS) -> str:
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


class AlioSource:
    """SourcePort + AcknowledgingSource."""

    source = "alio"

    def __init__(
        self,
        inbox: Path,
        *,
        limits: SandboxLimits,
        catalog: CatalogPort | None = None,
        runner: Runner = run_parser,
    ):
        self.inbox = Path(inbox)
        self._box = Inbox(self.inbox, formats=FILE_FORMATS, logger=logger, event="alio")
        self.limits = limits
        self.catalog = catalog
        self._runner = runner

    def __repr__(self) -> str:
        return "AlioSource()"

    async def aclose(self) -> None:
        return None

    # ── 수집 ─────────────────────────────────────────────
    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """query 는 쓰지 않는다 (inbox 전체가 대상). 파일은 순차 처리 (동시성 1)."""
        files = self._box.pending() if limit > 0 else []
        if not files:
            return []
        index = await self._catalog_index()
        out: list[dict[str, Any]] = []
        for path in files:
            if len(out) >= limit:
                break
            if raw := await self._process(path, index):
                out.append(raw)
        return out

    async def _catalog_index(self) -> dict[str, CatalogEntry]:
        if self.catalog is None:
            return {}
        try:
            return {e.catalog_id: e for e in await self.catalog.entries()}
        except Exception as exc:  # 카탈로그가 깨져도 파일 적재는 계속한다
            logger.warning("alio.catalog_failed error=%s", error_name(exc))
            return {}

    async def _process(self, path: Path, index: dict[str, CatalogEntry]) -> dict[str, Any] | None:
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=FILE_FORMATS)
        except FileRejected as exc:
            self._box.quarantine(path, exc, sha256=None)
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(
                    await self._runner(vf.fd, vf.fmt, self.limits)
                )
                if not result.text.strip():
                    raise NoTextLayer("no text")
            except (SandboxError, ValidationError, NoTextLayer) as exc:
                self._box.quarantine(path, exc, sha256=vf.sha256)
                return None
        entry = index.get(path.stem)
        return {
            "sha256": vf.sha256,
            "fmt": vf.fmt,
            "catalog": entry.model_dump(mode="json") if entry else None,
            "extract": result.model_dump(),
            "_file": str(path),
        }

    # ── 처리 완료 통보 ───────────────────────────────────
    def acknowledge(self, raws: list[dict[str, Any]]) -> None:
        self._box.acknowledge(raws)

    # ── 정규화 (순수) ────────────────────────────────────
    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_report(raw)


def normalize_report(raw: dict[str, Any]) -> Document:
    """순수 함수. 카탈로그 매칭이 있으면 그 메타데이터를, 없으면 추출 결과로 제목을 만든다."""
    sha = str(raw["sha256"])
    extract = ExtractResult.model_validate(raw["extract"])
    entry = CatalogEntry.model_validate(raw["catalog"]) if raw.get("catalog") else None
    text = extract.text.strip()
    if not text:
        raise ValueError("본문 없음")
    title = (
        _clean(entry.title if entry else None)
        or _clean(extract.meta_title)
        or next((_clean(line) for line in text.splitlines() if line.strip()), "")
    )
    return Document(
        doc_id=f"alio:{entry.catalog_id}" if entry else f"alio:sha-{sha[:16]}",
        source="alio",
        doc_type="internal_report",
        title=title,
        body=text,
        pub_date=entry.published if entry else None,
        orgs=[entry.institution_tag] if entry else [],
        lang="ko",
        text_basis="full_text",
        url=entry.url if entry else None,
        toc=[t for t in (_clean(h) for h in extract.toc) if t] or None,
        raw={
            "sha256": sha,
            "fmt": raw.get("fmt"),
            "catalog_id": entry.catalog_id if entry else None,
            "catalog_matched": entry is not None,
            "pages": extract.pages,
            "truncated": extract.truncated,
        },
    )
