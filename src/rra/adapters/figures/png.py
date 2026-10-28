"""SVG → PNG(resvg) 와 이미지 축소(Pillow) — 그림 밑그림·업로드 이미지 공용 ([G] 2026-10-28).

- `svg_to_png`: 번들 폰트만 쓴다(`skip_system_fonts=True`, 운영기·CI 결과 동일).
  상한(`max_bytes`)을 넘으면 zoom 을 0.8 배씩 줄여(최소 0.5) 다시 그리고, 그래도 크면
  팔레트 양자화·축소.
- `shrink_image`: 긴 변 ≤ max_side, RGB 변환, JPEG 는 품질 단계 하향, PNG 는 양자화 뒤 JPEG 로 대체.
- 입력 검증: 열 수 없으면 ValueError, 픽셀 수 40M 초과는 거부(압축 폭탄).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

import resvg_py
from PIL import Image

MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = (
    MAX_PIXELS  # 2배 초과는 DecompressionBombError — 아래 _open 이 ValueError 로 통일
)
MIN_ZOOM = 0.5
JPEG_QUALITIES = (85, 75, 65, 55)
_OPEN_ERROR = "이미지를 열 수 없습니다"


def _open(data: bytes) -> Image.Image:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # Pillow 는 UnidentifiedImageError·OSError·DecompressionBombError 등
        raise ValueError(_OPEN_ERROR) from exc
    if im.width * im.height > MAX_PIXELS:
        raise ValueError(_OPEN_ERROR)
    return im


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "RGB":
        return im
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    return im.convert("RGB")


def _save(im: Image.Image, fmt: str, **kw: object) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format=fmt, **kw)
    return buf.getvalue()


def image_size(data: bytes) -> tuple[int, int]:
    """(폭, 높이). 열 수 없으면 ValueError."""
    return _open(data).size


def svg_to_png(
    svg: str,
    *,
    font_files: Sequence[Path | str],
    dpi: int = 300,
    zoom: float | None = None,
    max_bytes: int = 512_000,
) -> bytes:
    """SVG 문자열을 PNG 로. 픽셀 폭 = SVG width × zoom (zoom 기본 dpi/96)."""
    files = [str(p) for p in font_files]
    z = float(zoom) if zoom else dpi / 96.0
    data = _render(svg, files, dpi, z)
    while len(data) > max_bytes and z > MIN_ZOOM:
        z = max(MIN_ZOOM, z * 0.8)
        data = _render(svg, files, dpi, z)
    if len(data) > max_bytes:
        data = _shrink_png(data, max_bytes)
    return data


def _render(svg: str, files: list[str], dpi: int, zoom: float) -> bytes:
    out = resvg_py.svg_to_bytes(
        svg_string=svg,
        font_files=files,
        skip_system_fonts=True,
        dpi=float(dpi),
        zoom=zoom,
    )
    return bytes(out)


def _shrink_png(data: bytes, max_bytes: int) -> bytes:
    """PNG 를 PNG 로 유지한 채 줄인다: 팔레트 양자화 → 0.8 배 축소 반복."""
    im = _to_rgb(_open(data))
    for _ in range(8):
        pal = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        out = _save(pal, "PNG", optimize=True)
        if len(out) <= max_bytes or min(im.size) <= 200:
            return out
        im = im.resize((max(1, int(im.width * 0.8)), max(1, int(im.height * 0.8))), Image.LANCZOS)
    return out


def shrink_image(
    data: bytes, mime: str, *, max_bytes: int = 512_000, max_side: int = 2000
) -> tuple[bytes, str]:
    """긴 변 ≤ max_side·RGB 로 바꾸고 상한에 맞춘다. (bytes, 'image/png'|'image/jpeg')."""
    im = _to_rgb(_open(data))
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    want_png = (mime or "").lower() == "image/png"
    if want_png:
        out = _save(im, "PNG", optimize=True)
        if len(out) <= max_bytes:
            return out, "image/png"
        out = _save(im.quantize(colors=256, method=Image.Quantize.MEDIANCUT), "PNG", optimize=True)
        if len(out) <= max_bytes:
            return out, "image/png"
    out = b""
    for _ in range(5):
        for q in JPEG_QUALITIES:
            out = _save(im, "JPEG", quality=q, optimize=True)
            if len(out) <= max_bytes:
                return out, "image/jpeg"
        if min(im.size) <= 200:
            break
        im = im.resize((max(1, int(im.width * 0.75)), max(1, int(im.height * 0.75))), Image.LANCZOS)
    return out, "image/jpeg"
