"""첨부 파일 속 내장 이미지 추출 (P3 확장, 2026-10-27) — `rra vision extract`.

스냅샷 manifest 의 페이지 레코드마다 내려받은 첨부(hwpx·hwp·pdf·pptx·xlsx)를 격리 자식
(`_worker.PARSERS["embedded_images"]`)에 넘겨 이미지를 뽑고, 같은 해시는 하나만
`images/attachments/<sha>.<ext>` 에 저장한 뒤 `attachment_images.jsonl` 에 이미지 레코드를 쓴다.
레코드에는 원본 위치(첨부 파일명·첨부 해시·쪽/슬라이드)와 페이지(메뉴 경로·제목·URL)가 붙어 거르기·
순서·판독 파이프라인(`rra vision read`)이 페이지 이미지와 똑같이 다룬다. 첨부 바이트는 비신뢰
(보안 B).
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.vision.manifest import ATTACHMENT_IMAGES_NAME, SnapshotImages

logger = logging.getLogger("rra.vision.attachments")
Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
DEFAULT_FORMATS = frozenset({"hwpx", "hwp", "pdf", "pptx", "xlsx"})


@dataclass
class ExtractReport:
    attachments: int = 0  # 시도한 첨부 수
    parsed: int = 0
    images: int = 0  # 새로 저장한 이미지 수
    duplicates: int = 0  # 이미 있는 해시
    rejected: dict[str, int] = field(default_factory=dict)  # 첨부 단위 거부 사유 → 수
    skipped: dict[str, int] = field(default_factory=dict)  # 자식이 건너뛴 이미지 사유 → 수
    by_ext: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachments": self.attachments,
            "parsed": self.parsed,
            "images": self.images,
            "duplicates": self.duplicates,
            "rejected": dict(self.rejected),
            "skipped": dict(self.skipped),
            "by_ext": dict(self.by_ext),
        }


class ExtractAttachmentImages:
    def __init__(
        self,
        snapshot: SnapshotImages,
        limits: SandboxLimits,
        *,
        formats: frozenset[str] = DEFAULT_FORMATS,
        max_images_per_file: int = 200,
        max_image_bytes: int = 8 * 1024 * 1024,
        min_pixels: int = 20_000,
        runner: Runner = run_parser,
    ):
        self.snapshot = snapshot
        self.limits = limits
        self.formats = formats
        self.max_images_per_file = max_images_per_file
        self.max_image_bytes = max_image_bytes
        self.min_pixels = min_pixels
        self._runner = runner

    async def __call__(self, *, limit: int | None = None) -> ExtractReport:
        report = ExtractReport()
        seen = self.snapshot.existing_hashes()
        out_dir = self.snapshot.dir / "images" / "attachments"
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl = self.snapshot.dir / ATTACHMENT_IMAGES_NAME
        done_attachments = _done_attachment_hashes(jsonl)
        with jsonl.open("a", encoding="utf-8") as sink:
            for page in self.snapshot.page_records():
                for att in page.get("attachments") or []:
                    if not isinstance(att, dict) or not att.get("downloaded"):
                        continue
                    ext = str(att.get("ext") or "").lower()
                    if ext not in self.formats or not att.get("path") or not att.get("sha256"):
                        continue
                    if str(att["sha256"]) in done_attachments:
                        continue  # 이미 처리한 첨부 (증분)
                    if limit is not None and report.attachments >= limit:
                        return report
                    report.attachments += 1
                    images = await self._extract(att, ext, report)
                    done_attachments.add(str(att["sha256"]))
                    if images is None:
                        continue
                    report.parsed += 1
                    for img in images:
                        sha = str(img.get("sha256") or "")
                        if not sha or sha in seen:
                            report.duplicates += 1
                            continue
                        try:
                            payload = base64.b64decode(img.get("b64") or "", validate=True)
                        except ValueError:
                            continue
                        target = out_dir / f"{sha}.{img.get('ext', 'png')}"
                        if not target.exists():
                            target.write_bytes(payload)
                        seen.add(sha)
                        report.images += 1
                        report.by_ext[ext] = report.by_ext.get(ext, 0) + 1
                        sink.write(
                            json.dumps(
                                _record(page, att, img, target.relative_to(self.snapshot.dir)),
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    # 아무 이미지도 안 나온 첨부도 표시를 남겨 다음 실행이 건너뛰게
                    if not images:
                        sink.write(
                            json.dumps(
                                {"type": "attachment_done", "attachment_sha256": att["sha256"]}
                            )
                            + "\n"
                        )
        return report

    async def _extract(
        self, att: dict[str, Any], ext: str, report: ExtractReport
    ) -> list[dict] | None:
        path = self.snapshot.dir / str(att["path"])
        try:
            vf = open_validated(
                path, max_bytes=int(self.limits.max_input_mb * 1024 * 1024), allowed=self.formats
            )
        except FileRejected as exc:
            report.rejected[type(exc).__name__] = report.rejected.get(type(exc).__name__, 0) + 1
            return None
        limits = replace(
            self.limits,
            extra={
                **dict(self.limits.extra),
                "ext": ext,
                "max_images": self.max_images_per_file,
                "max_image_bytes": self.max_image_bytes,
                "min_pixels": self.min_pixels,
            },
        )
        with vf:
            try:
                result = await self._runner(vf.fd, "embedded_images", limits)
            except (SandboxError, ValidationError) as exc:
                report.rejected[type(exc).__name__] = report.rejected.get(type(exc).__name__, 0) + 1
                logger.warning("vision.attachment_rejected error=%s", type(exc).__name__)
                return None
        for why, n in (result.get("skipped") or {}).items():
            report.skipped[str(why)] = report.skipped.get(str(why), 0) + int(n)
        images = result.get("images")
        return [i for i in images if isinstance(i, dict)] if isinstance(images, list) else []


def _done_attachment_hashes(jsonl: Path) -> set[str]:
    out: set[str] = set()
    if not jsonl.is_file():
        return out
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        att = raw.get("attachment") if isinstance(raw, dict) else None
        if isinstance(att, dict) and att.get("sha256"):
            out.add(str(att["sha256"]))
        elif isinstance(raw, dict) and raw.get("attachment_sha256"):
            out.add(str(raw["attachment_sha256"]))
    return out


def _record(
    page: dict[str, Any], att: dict[str, Any], img: dict[str, Any], rel: Path
) -> dict[str, Any]:
    title = " > ".join(str(x) for x in (page.get("menu_path"), page.get("title")) if x)
    name = str(att.get("served_name") or att.get("name") or "")
    return {
        "type": "image",
        "sha256": img.get("sha256"),
        "path": rel.as_posix(),
        "url": att.get("url"),  # 원본 = 첨부 파일 URL
        "page_url": page.get("url"),
        "page_title": title or None,
        "page_doc_id": page.get("doc_id"),
        "alt": name,
        "caption": f"{name} {img.get('where') or ''}".strip(),
        "width": img.get("width"),
        "height": img.get("height"),
        "bytes": img.get("bytes"),
        "mime": img.get("mime"),
        "source": page.get("source"),
        "attachment": {
            "name": name,
            "sha256": att.get("sha256"),
            "ext": att.get("ext"),
            "where": img.get("where"),
            "entry": img.get("name"),
        },
    }
