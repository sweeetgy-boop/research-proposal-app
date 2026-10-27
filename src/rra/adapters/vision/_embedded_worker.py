"""격리 자식 전용 — 첨부 파일(hwpx·hwp·pdf·pptx·xlsx) 속 내장 이미지를 뽑는다 (P3 확장,
2026-10-27).

`_worker.PARSERS["embedded_images"]` 가 extract 를 부른다. 부모에서 import 하지 않는다(olefile·
pymupdf·PIL 은 자식에서만). 입력: 파일 바이트, limits.extra = {ext, max_images, max_image_bytes,
min_pixels}. 출력: {"images": [{"name", "where", "ext", "mime", "width", "height", "bytes", "b64",
"sha256"}], "skipped": {사유: 수}}. where = pdf 쪽 번호 / pptx 슬라이드 번호 / xlsx 드로잉 이름 /
hwp·hwpx 는 BinData 이름(쪽 미상). 같은 바이트(해시)는 한 번만. 크기·픽셀 하한 미달·알 수 없는
형식은 건너뛴다.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import zipfile
import zlib
from typing import Any

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}
MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}
DEFAULT_MAX_IMAGES = 200
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_MIN_PIXELS = 20_000
_SLIDE_REL = re.compile(r"^ppt/slides/_rels/slide(\d+)\.xml\.rels$")
_DRAWING_REL = re.compile(r"^xl/drawings/_rels/(drawing\d+)\.xml\.rels$")
_TARGET = re.compile(r'Target="([^"]+)"')


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    extra = limits.get("extra") or {}
    ext = str(extra.get("ext") or "").lower()
    opts = {
        "max_images": int(extra.get("max_images") or DEFAULT_MAX_IMAGES),
        "max_image_bytes": int(extra.get("max_image_bytes") or DEFAULT_MAX_IMAGE_BYTES),
        "min_pixels": int(extra.get("min_pixels") or DEFAULT_MIN_PIXELS),
    }
    out = _Collector(opts)
    if ext == "hwpx":
        _from_zip(data, out, prefix="BinData/", where=lambda n: n)
    elif ext == "pptx":
        _from_pptx(data, out)
    elif ext == "xlsx":
        _from_xlsx(data, out)
    elif ext == "hwp":
        _from_hwp(data, out)
    elif ext == "pdf":
        _from_pdf(data, out)
    else:
        raise ValueError("unsupported")
    return {"images": out.images, "skipped": out.skipped}


class _Collector:
    def __init__(self, opts: dict[str, int]):
        self.opts = opts
        self.images: list[dict[str, Any]] = []
        self.skipped: dict[str, int] = {}
        self.seen: set[str] = set()

    def _skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1

    def add(
        self, name: str, where: str | None, payload: bytes, ext_hint: str | None = None
    ) -> None:
        if len(self.images) >= self.opts["max_images"]:
            self._skip("max_images")
            return
        if not payload or len(payload) > self.opts["max_image_bytes"]:
            self._skip("size")
            return
        sha = hashlib.sha256(payload).hexdigest()
        if sha in self.seen:
            self._skip("duplicate")
            return
        ext = (ext_hint or name.rsplit(".", 1)[-1]).lower().lstrip(".")
        if ext not in IMAGE_EXTS:
            ext = _sniff(payload) or ""
            if not ext:
                self._skip("format")
                return
        try:
            from PIL import Image

            with Image.open(io.BytesIO(payload)) as img:
                width, height = img.size
        except Exception:  # noqa: BLE001 — 깨진 이미지는 조용히 건너뛴다 (자식 프로세스)
            self._skip("decode")
            return
        if width * height < self.opts["min_pixels"]:
            self._skip("tiny")
            return
        self.seen.add(sha)
        self.images.append(
            {
                "name": name,
                "where": where,
                "ext": "jpg" if ext == "jpeg" else ext,
                "mime": MIME.get(ext, "application/octet-stream"),
                "width": width,
                "height": height,
                "bytes": len(payload),
                "sha256": sha,
                "b64": base64.b64encode(payload).decode("ascii"),
            }
        )


def _sniff(payload: bytes) -> str | None:
    head = payload[:12]
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8"):
        return "jpg"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _from_zip(data: bytes, out: _Collector, *, prefix: str, where) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name.startswith(prefix) or info.is_dir():
                continue
            if info.file_size > out.opts["max_image_bytes"]:
                out._skip("size")
                continue
            out.add(name, where(name), zf.read(info))


def _rel_map(zf: zipfile.ZipFile, pattern: re.Pattern[str], base: str) -> dict[str, str]:
    """관계 파일(.rels) → {media 경로: 소속 이름}."""
    owner: dict[str, str] = {}
    for info in zf.infolist():
        m = pattern.match(info.filename)
        if not m:
            continue
        rels = zf.read(info).decode("utf-8", "ignore")
        for target in _TARGET.findall(rels):
            path = target.replace("../", "")
            owner.setdefault(f"{base}/{path}" if not path.startswith(base) else path, m.group(1))
    return owner


def _from_pptx(data: bytes, out: _Collector) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        owner = _rel_map(zf, _SLIDE_REL, "ppt")
        for info in zf.infolist():
            if not info.filename.startswith("ppt/media/") or info.is_dir():
                continue
            slide = owner.get(info.filename)
            out.add(info.filename, f"slide {slide}" if slide else None, zf.read(info))


def _from_xlsx(data: bytes, out: _Collector) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        owner = _rel_map(zf, _DRAWING_REL, "xl")
        for info in zf.infolist():
            if not info.filename.startswith("xl/media/") or info.is_dir():
                continue
            out.add(info.filename, owner.get(info.filename), zf.read(info))


def _from_hwp(data: bytes, out: _Collector) -> None:
    import olefile

    if not olefile.isOleFile(data):
        raise ValueError("not ole")
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        for entry in ole.listdir(streams=True, storages=False):
            if not entry or entry[0] != "BinData":
                continue
            name = "/".join(entry)
            with ole.openstream(entry) as stream:
                raw = stream.read(out.opts["max_image_bytes"] + 1)
            if len(raw) > out.opts["max_image_bytes"]:
                out._skip("size")
                continue
            payload = raw
            if _sniff(raw) is None:  # 보통 zlib(raw deflate) 로 압축돼 있다
                try:
                    payload = zlib.decompressobj(-15).decompress(
                        raw, out.opts["max_image_bytes"] + 1
                    )
                except zlib.error:
                    payload = raw
            ext_hint = entry[-1].rsplit(".", 1)[-1] if "." in entry[-1] else None
            out.add(name, None, payload, ext_hint)


def _from_pdf(data: bytes, out: _Collector) -> None:
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, 1):
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    info = doc.extract_image(xref)
                except Exception:  # noqa: BLE001
                    out._skip("decode")
                    continue
                if not info or not info.get("image"):
                    out._skip("decode")
                    continue
                out.add(
                    f"xref{xref}.{info.get('ext', 'png')}",
                    f"page {page_no}",
                    info["image"],
                    info.get("ext"),
                )
