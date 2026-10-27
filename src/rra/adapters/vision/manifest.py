"""ImageSnapshotPort 구현 — data/korail_web/snapshots/<date>/manifest.jsonl 의 이미지 항목.

manifest 는 크롤(레인 A)이 쓴다. 필드 이름이 아직 확정되지 않아 관대하게 읽는다
(docs/vision-manifest.md):
- 이미지 항목 판별: `type`/`kind` == "image" 이거나 sha256 + 이미지 확장자 경로가 있는 줄.
- 별칭: sha256|hash|sha, path|file|local_path, url|src|image_url, page_url|page|source_url,
page_title|title,
  alt|alt_text, caption, width|w, height|h, bytes|size|size_bytes, mime|content_type,
  order_group|group|category,
  page_doc_id|doc_id.
- 깨진 줄은 세고 건너뛴다. 전부 비신뢰 데이터.
읽기: 경로는 스냅샷 폴더 밖으로 나갈 수 없고, 바이트 상한을 넘으면 거부,
내용 sha256 이 manifest 와 다르면 거부.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from rra.domain.models.vision import ORDER_GROUPS, ImageItem

MANIFEST_NAME = "manifest.jsonl"
_SNAPSHOT_NAME = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.-]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
_ALIASES: dict[str, tuple[str, ...]] = {
    "sha256": ("sha256", "hash", "sha"),
    "path": ("path", "file", "local_path", "filename"),
    "url": ("url", "src", "image_url"),
    "page_url": ("page_url", "page", "source_url"),
    "page_title": ("page_title", "title"),
    "page_doc_id": ("page_doc_id", "doc_id"),
    "alt": ("alt", "alt_text"),
    "caption": ("caption", "figcaption"),
    "width": ("width", "w"),
    "height": ("height", "h"),
    "bytes": ("bytes", "size", "size_bytes"),
    "mime": ("mime", "content_type", "mime_type"),
    "order_group": ("order_group", "group", "category"),
    "source": ("source",),
}
MAX_STR = 2000


def latest_snapshot(root: Path) -> str | None:
    """이름순 마지막 스냅샷 폴더 (날짜 이름이면 최신)."""
    if not root.is_dir():
        return None
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and _SNAPSHOT_NAME.match(p.name))
    return names[-1] if names else None


def _pick(raw: dict[str, Any], key: str) -> Any:
    for alias in _ALIASES[key]:
        if alias in raw and raw[alias] not in (None, ""):
            return raw[alias]
    return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s[:MAX_STR] if s else None


def _int(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


ATTACHMENT_IMAGES_NAME = "attachment_images.jsonl"


def _flatten_nested(page: dict[str, Any], img: dict[str, Any]) -> dict[str, Any]:
    """페이지 레코드 안의 이미지 항목을 평평한 이미지 레코드로 — 메뉴 경로·제목·URL 을 붙인다."""
    if img.get("downloaded") is False:
        return {}
    title = " > ".join(str(x) for x in (page.get("menu_path"), page.get("title")) if x)
    return {
        "type": "image",
        "sha256": img.get("sha256"),
        "path": img.get("path"),
        "url": img.get("src") or img.get("url"),
        "page_url": page.get("url"),
        "page_title": title or None,
        "page_doc_id": page.get("doc_id"),
        "alt": img.get("alt"),
        "caption": img.get("caption"),
        "width": img.get("width"),
        "height": img.get("height"),
        "bytes": img.get("bytes"),
        "mime": img.get("mime") or _MIME.get(str(img.get("ext") or "").lower()),
        "source": page.get("source"),
        "attachment": img.get("attachment"),
    }


_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
}


def parse_item(raw: dict[str, Any]) -> ImageItem | None:
    """manifest 한 줄 → ImageItem. 이미지가 아니거나 필수(sha256·path)가 없으면 None."""
    kind = str(raw.get("type") or raw.get("kind") or "").lower()
    path = _str(_pick(raw, "path"))
    sha = _str(_pick(raw, "sha256"))
    if not path or not sha:
        return None
    if kind and kind != "image":
        return None
    if not kind and not path.lower().split("?", 1)[0].endswith(IMAGE_EXT):
        return None
    sha = sha.lower()
    if not _SHA.match(sha):
        return None
    group = _str(_pick(raw, "order_group"))
    if group is not None and group not in ORDER_GROUPS:
        group = None
    return ImageItem(
        sha256=sha,
        path=path,
        url=_str(_pick(raw, "url")),
        page_url=_str(_pick(raw, "page_url")),
        page_title=_str(_pick(raw, "page_title")),
        page_doc_id=_str(_pick(raw, "page_doc_id")),
        alt=_str(_pick(raw, "alt")),
        caption=_str(_pick(raw, "caption")),
        width=_int(_pick(raw, "width")),
        height=_int(_pick(raw, "height")),
        bytes=_int(_pick(raw, "bytes")),
        mime=_str(_pick(raw, "mime")),
        order_group=group,  # type: ignore[arg-type]
        source=_str(_pick(raw, "source")) or "korail_web",
        attachment=raw.get("attachment") if isinstance(raw.get("attachment"), dict) else None,
    )


class SnapshotImages:
    def __init__(
        self, root: Path, snapshot: str | None = None, *, max_bytes: int = 15 * 1024 * 1024
    ):
        self.root = Path(root)
        name = snapshot or latest_snapshot(self.root)
        if not name:
            raise FileNotFoundError("스냅샷 폴더가 없습니다 (data/korail_web/snapshots/<date>/)")
        if not _SNAPSHOT_NAME.match(name):
            raise ValueError("스냅샷 이름이 올바르지 않습니다")
        self.snapshot = name
        self.dir = (self.root / name).resolve()
        self.max_bytes = max_bytes
        self.bad_lines = 0
        self.non_image = 0

    def _lines(self, name: str) -> list[dict[str, Any]]:
        path = self.dir / name
        if not path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except ValueError:
                    self.bad_lines += 1
                    continue
                if not isinstance(raw, dict):
                    self.bad_lines += 1
                    continue
                out.append(raw)
        return out

    def page_records(self) -> list[dict[str, Any]]:
        """manifest 의 페이지(게시물) 레코드 — 첨부 목록(`attachments`)을 가진 것들."""
        return [r for r in self._lines(MANIFEST_NAME) if isinstance(r.get("attachments"), list)]

    def list_images(self) -> list[ImageItem]:
        """manifest.jsonl 의 이미지 줄 + 페이지 레코드 안의 `images` 배열(크롤러 꼴) +
        attachment_images.jsonl(첨부 속 내장 이미지). 같은 (sha256, path) 줄은 하나."""
        path = self.dir / MANIFEST_NAME
        if not path.is_file():
            raise FileNotFoundError(f"manifest 가 없습니다: {self.snapshot}/{MANIFEST_NAME}")
        items: list[ImageItem] = []
        seen: set[tuple[str, str]] = set()  # (sha256, path) — 같은 파일의 중복 줄만 거른다
        self.bad_lines = self.non_image = 0
        for raw in self._lines(MANIFEST_NAME) + self._lines(ATTACHMENT_IMAGES_NAME):
            nested = raw.get("images")
            if isinstance(nested, list) and nested:  # 크롤러 꼴: 페이지 레코드 안에 이미지 목록
                for img in nested:
                    if isinstance(img, dict):
                        item = parse_item(_flatten_nested(raw, img))
                        if item is not None and (item.sha256, item.path) not in seen:
                            seen.add((item.sha256, item.path))
                            items.append(item)
                if not raw.get("path"):
                    continue
            item = parse_item(raw)
            if item is None:
                self.non_image += 1
                continue
            if (item.sha256, item.path) in seen:
                continue
            seen.add((item.sha256, item.path))
            items.append(item)
        return items

    def existing_hashes(self) -> set[str]:
        return {i.sha256 for i in self.list_images()}

    def resolve(self, item: ImageItem) -> Path:
        target = (self.dir / item.path).resolve()
        if not target.is_relative_to(self.dir):
            raise ValueError("이미지 경로가 스냅샷 폴더 밖을 가리킵니다")
        return target

    def read_image(self, item: ImageItem) -> bytes:
        target = self.resolve(item)
        size = target.stat().st_size
        if size > self.max_bytes:
            raise ValueError("이미지가 상한보다 큽니다")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != item.sha256:
            raise ValueError("이미지 내용이 manifest 의 sha256 과 다릅니다")
        return data
