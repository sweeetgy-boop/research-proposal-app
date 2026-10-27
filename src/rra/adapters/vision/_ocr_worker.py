"""격리 자식 전용 OCR 파서 — `_worker.PARSERS["ocr_image"]` 가 이 모듈의 extract 를 부른다.

부모 프로세스에서 import 하지 않는다 (PIL·ocrmac·Vision 프레임워크는 자식에서만 뜬다).
입력: 이미지 바이트. 출력: {"lines": [{"text", "confidence", "box"}], "width", "height",
"elapsed_sec"}.
상한: 픽셀 수(limits.extra.max_pixels — PIL 압축폭탄 예외로 거부), 줄 수·줄 길이.
"""

from __future__ import annotations

import io
import time
from typing import Any

MAX_LINES = 2000
MAX_LINE_CHARS = 2000
DEFAULT_MAX_PIXELS = 40_000_000


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image

    extra = limits.get("extra") or {}
    max_pixels = int(extra.get("max_pixels") or DEFAULT_MAX_PIXELS)
    languages = [str(x) for x in (extra.get("languages") or ["ko-KR", "en-US"])]
    Image.MAX_IMAGE_PIXELS = max_pixels  # 초과 시 DecompressionBombError (ok=false 로 보고)
    started = time.monotonic()
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        width, height = img.size
        if width * height > max_pixels:
            raise ValueError("too many pixels")
        rgb = img.convert("RGB")
    from ocrmac import ocrmac

    raw = ocrmac.OCR(rgb, language_preference=languages, recognition_level="accurate").recognize()
    lines: list[dict[str, Any]] = []
    for entry in raw[:MAX_LINES]:
        try:
            text, confidence, box = entry[0], float(entry[1]), list(entry[2])
        except (IndexError, TypeError, ValueError):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        lines.append(
            {
                "text": text[:MAX_LINE_CHARS],
                "confidence": max(0.0, min(1.0, confidence)),
                "box": [float(v) for v in box[:4]] if len(box) == 4 else None,
            }
        )
    return {
        "lines": lines,
        "width": width,
        "height": height,
        "elapsed_sec": round(time.monotonic() - started, 3),
    }
