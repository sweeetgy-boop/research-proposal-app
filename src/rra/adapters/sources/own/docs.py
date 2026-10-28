"""공시완료 폴더의 공시용 요약문 적재 (`own_docs`).

투입 위치: `data/inbox/own_docs/` 에 연도 폴더(`2022/…`) 또는 과제 폴더(`260324_…`)를 그대로 복사.
과제 폴더마다 요약 파일을 고른다 — 공시용 > 일반 요약, hwpx > hwp > pdf (`_names` 모듈).
묶음 폴더(수송수요 예측 5건 등)는 파일 꼬리말(고속·준고속·일반·광역·화물)로 과제를 나눈다.

파일 처리는 알리오 filedrop 과 같다: filecheck → 샌드박스(hwp·hwpx·pdf) → 재검증.
본문 라벨 해석·정규화는 알리오 공개 요약 경로(`alio.summary`)를 그대로 쓴다 — 공시용 요약문은
알리오 상세 페이지 요약의 원본 파일이라 같은 doc_id 로 합쳐진다(본문이 긴 쪽이 남는다).
연구자 이름은 저장하지 않는다(authors 비움, 연구책임자는 부서만).
공시용 요약문은 공개 자료(visibility public). 공시용이 없어 일반 요약문을 쓴 과제만 internal
(2026-10-26 결정).

처리가 끝난 과제 폴더는 `_done/` 으로 옮긴다. 파일 하나가 실패해도 폴더의 다른 파일은 계속한다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._inbox import DONE_DIR, QUARANTINE_DIR, error_name
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.alio.summary import (
    DEFAULT_LABELS,
    MissingRequiredField,
    normalize_summary,
)
from rra.adapters.sources.own._names import (
    folder_title,
    nfc,
    select_summary_files,
    strip_person,
)
from rra.domain.models import Document
from rra.domain.rules.series import display_title

logger = logging.getLogger("rra.sources.own_docs")

FILE_FORMATS = frozenset({"hwpx", "hwp", "pdf"})
_YEAR_DIR = re.compile(r"^\d{4}$")
_TITLE_LINE_MAX = 200
_LABEL_START = re.compile(r"^\s*(?:\d{1,2}\s*[.)]\s*)?(?:과제개요|제목|연구과제명|과제명|과제유형)")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]


class NoTextLayer(ValueError):
    pass


def project_dirs(inbox: Path) -> list[Path]:
    """inbox 바로 아래 과제 폴더 + 연도 폴더(`2024`) 안의 과제 폴더. `_`·`.` 으로 시작하면 제외."""
    if not inbox.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(inbox.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if _YEAR_DIR.match(child.name):
            out.extend(
                sorted(
                    p for p in child.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
                )
            )
        else:
            out.append(child)
    return out


def title_first(lines: Sequence[str]) -> list[str]:
    """첫 라벨 앞의 첫 줄이 제목이면 `제목: …` 줄로 바꿔 라벨 해석이 제목을 잡게 한다."""
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        if _LABEL_START.match(text) or len(text) > _TITLE_LINE_MAX:
            return list(lines)
        return [f"제목: {text}", *lines[i + 1 :]]
    return list(lines)


class OwnDocsSource:
    """SourcePort + AcknowledgingSource + InboxSource. Document.source 는 alio (공시 요약)."""

    source = "own_docs"

    def __init__(
        self,
        inbox: Path,
        *,
        limits: SandboxLimits,
        institutions: Sequence[Mapping[str, Any]] = (),
        labels: Mapping[str, Sequence[str]] | None = None,
        default_org: str | None = "korail",
        runner: Runner = run_parser,
    ):
        self.inbox = Path(inbox)
        self.limits = limits
        self.institutions = list(institutions)
        self.labels = {**DEFAULT_LABELS, **(labels or {})}
        self.default_org = default_org
        self._runner = runner

    def __repr__(self) -> str:
        return "OwnDocsSource()"

    async def aclose(self) -> None:
        return None

    def inbox_status(self) -> dict[str, int]:
        def count(d: Path) -> int:
            return len(project_dirs(d)) if d.is_dir() else 0

        return {
            "pending": len(project_dirs(self.inbox)),
            "done": count(self.inbox / DONE_DIR),
            "quarantine": count(self.inbox / QUARANTINE_DIR),
        }

    # ── 수집 ─────────────────────────────────────────────
    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """query 는 쓰지 않는다. 과제 폴더 순서대로, 폴더당 요약 파일 1개 이상 (묶음은 꼬리말별)."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for folder in project_dirs(self.inbox):
            if len(out) >= limit:
                break
            files = select_summary_files(folder)
            if not files:
                logger.warning("own_docs.no_summary folder=%s", _ref(folder))
                continue
            for variant, path in files:
                raw = await self._process(path, folder, variant)
                if raw is None or raw["sha256"] in seen:
                    continue
                seen.add(raw["sha256"])
                out.append(raw)
        return out

    async def _process(self, path: Path, folder: Path, variant: str) -> dict[str, Any] | None:
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=FILE_FORMATS)
        except FileRejected as exc:
            logger.warning("own_docs.rejected error=%s file=%s", error_name(exc), _ref(path))
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(
                    await self._runner(vf.fd, vf.fmt, self.limits)
                )
                if not result.text.strip():
                    raise NoTextLayer("no text")
            except (SandboxError, ValidationError, NoTextLayer) as exc:
                logger.warning(
                    "own_docs.rejected error=%s file=sha256:%s", error_name(exc), vf.sha256[:8]
                )
                return None
        return {
            "sha256": vf.sha256,
            "fmt": vf.fmt,
            "lines": result.text.splitlines(),
            "variant": variant,
            "disclosed": "공시"
            in nfc(path.name),  # 공시용 요약문이면 public, 일반 요약문만 있으면 internal
            "folder_title": folder_title(folder.name),
            "_dir": str(folder),
            "_file": str(path),
        }

    # ── 처리 완료 통보 ───────────────────────────────────
    def acknowledge(self, raws: list[dict[str, Any]]) -> None:
        for folder in {Path(raw["_dir"]) for raw in raws}:
            if folder.parent != self.inbox and folder.parent.parent != self.inbox:
                continue  # 이 inbox 가 만든 raw 가 아니다
            rel = folder.relative_to(self.inbox)
            dest = self.inbox / DONE_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.replace(folder, dest)
            except OSError as exc:
                logger.warning("own_docs.move_failed error=%s", type(exc).__name__)

    # ── 정규화 (순수) ────────────────────────────────────
    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_own_summary(
            raw,
            labels=self.labels,
            institutions=self.institutions,
            default_org=self.default_org,
        )

    def ingest_warnings(self, doc: Document) -> list[tuple[str, str]]:
        if doc.raw.get("org_source") == "default" and doc.orgs:
            return [("assumed_org", doc.orgs[0])]
        return []


def normalize_own_summary(
    raw: Mapping[str, Any],
    *,
    labels: Mapping[str, Sequence[str]] | None = None,
    institutions: Sequence[Mapping[str, Any]] = (),
    default_org: str | None = "korail",
) -> Document:
    """순수 함수. 라벨 해석은 alio.summary 와 같고, 라벨이 없는 파일은 폴더 제목 + 본문으로
    적재한다. 이름(연구자·저자)은 남기지 않는다."""
    lines = [nfc(line) for line in raw["lines"]]
    folder = str(raw.get("folder_title") or "")
    variant = str(raw.get("variant") or "")
    sha = str(raw["sha256"])
    try:
        doc = normalize_summary(
            {"sha256": sha, "lines": title_first(lines)},
            labels=labels,
            institutions=institutions,
            default_org=default_org,
        )
    except MissingRequiredField:
        doc = _plain_document(sha, lines, folder, variant, default_org)
    pi = doc.raw.get("pi")
    disclosed = bool(raw.get("disclosed", True))
    extra = {
        "fmt": raw.get("fmt"),
        "origin": "own_docs",
        "folder_title": folder or None,
        "variant": variant or None,
        "disclosed": disclosed,
        "pi": strip_person(pi) if isinstance(pi, str) else None,
    }
    return doc.model_copy(
        update={
            # 공시용 요약문 머리("요 약 문 1. 연구 제목 …")·꼬리("□ 개 요")를 뗀 제목 (ADR 0043).
            # doc_id 는 뗀 전 제목에서 나온 그대로 — 다시 적재해도 같은 문서로 덮어쓴다
            "title": display_title(doc.title),
            "authors": [],
            "visibility": "public" if disclosed else "internal",
            "raw": {**doc.raw, **extra},
        }
    )


def _plain_document(
    sha: str, lines: Sequence[str], folder: str, variant: str, default_org: str | None
) -> Document:
    text = "\n".join(line for line in lines if line.strip())
    if not text:
        raise ValueError("본문 없음")
    title = " ".join(p for p in (folder, variant) if p) or next(
        line.strip() for line in lines if line.strip()
    )
    return Document(
        doc_id="alio:own-" + hashlib.sha256(sha.encode()).hexdigest()[:16],
        source="alio",
        doc_type="internal_report",
        title=title[:300],
        body=text,
        orgs=[default_org] if default_org else [],
        lang="ko",
        text_basis="summary",
        raw={"sha256": sha, "org_source": "default" if default_org else None, "unlabeled": True},
    )


def _ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(nfc(path.name).encode()).hexdigest()[:8]
