"""OcrPort 구현 — macOS Vision 텍스트 인식(ocrmac), 격리 자식 프로세스에서 실행 (보안 B).

- 이미지 바이트는 비신뢰. 디코딩(PIL)·인식은 `_sandbox.run_parser` 가 띄우는 `python -I` 자식에서만
  (rlimit·타임아웃·RSS 감시·stdout 상한). 부모는 바이트 상한만 먼저 본다.
- 자식 쪽 상한: 픽셀 수(`max_pixels`, PIL 압축폭탄 차단)·줄 수·줄 길이 (`_ocr_worker`).
- macOS 가 아니거나 ocrmac/Vision 이 없으면 `OcrUnavailable` — 파이프라인은 "OCR 없음" 으로
계속한다.
- 임시 파일은 0600 으로 만들고 fd 를 연 직후 지운다 (경로는 자식에 넘기지 않는다).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from rra.adapters.sources._sandbox import SandboxLimits, run_parser
from rra.application.ports.vision import OcrUnavailable
from rra.domain.models.vision import OcrLine, OcrResult

OCR_FORMAT = "ocr_image"
DEFAULT_LANGUAGES = ("ko-KR", "en-US")
DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_PIXELS = 40_000_000  # 약 6300×6300
DEFAULT_TIMEOUT_SEC = 90.0


def ocr_available() -> bool:
    if sys.platform != "darwin":
        return False
    return (
        importlib.util.find_spec("ocrmac") is not None
        and importlib.util.find_spec("Vision") is not None
    )


class MacVisionOcr:
    engine = "macos_vision"

    def __init__(
        self,
        *,
        limits: SandboxLimits | None = None,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_pixels: int = DEFAULT_MAX_PIXELS,
        tmp_dir: Path | None = None,
    ):
        base = limits or SandboxLimits(timeout_sec=DEFAULT_TIMEOUT_SEC)
        self.limits = replace(
            base,
            max_input_mb=max(0.1, max_bytes / (1024 * 1024)),
            extra={**base.extra, "languages": list(languages), "max_pixels": int(max_pixels)},
        )
        self.languages = tuple(languages)
        self.max_bytes = max_bytes
        self.tmp_dir = tmp_dir

    async def recognize(self, image: bytes, *, mime: str | None = None) -> OcrResult:
        if not ocr_available():
            raise OcrUnavailable("macOS Vision(ocrmac) 을 쓸 수 없습니다")
        if not image:
            raise ValueError("빈 이미지")
        if len(image) > self.max_bytes:
            raise ValueError("이미지가 상한보다 큽니다")
        fd = self._spool(image)
        try:
            result = await run_parser(fd, OCR_FORMAT, self.limits)
        finally:
            os.close(fd)
        lines = []
        for raw in result.get("lines") or []:
            if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
                continue
            try:
                conf = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            box = raw.get("box")
            lines.append(
                OcrLine(
                    text=raw["text"],
                    confidence=min(1.0, max(0.0, conf)),
                    box=[float(x) for x in box]
                    if isinstance(box, list) and len(box) == 4
                    else None,
                )
            )
        elapsed = result.get("elapsed_sec")
        return OcrResult(
            lines=lines,
            engine=self.engine,
            languages=list(self.languages),
            elapsed_sec=float(elapsed) if isinstance(elapsed, int | float) else None,
        )

    def _spool(self, image: bytes) -> int:
        """바이트를 0600 임시 파일에 쓰고 읽기 fd 를 돌려준다. 경로는 바로 지운다."""
        fd_w, path = tempfile.mkstemp(prefix="rra-ocr-", dir=self.tmp_dir)
        try:
            os.fchmod(fd_w, 0o600)
            with os.fdopen(fd_w, "wb") as f:
                f.write(image)
            fd = os.open(path, os.O_RDONLY)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return fd
