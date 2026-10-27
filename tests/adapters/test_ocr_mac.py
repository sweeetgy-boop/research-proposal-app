"""macOS Vision OCR — 격리 자식에서 실제 인식(macOS+ocrmac 있을 때만), 아니면 OcrUnavailable."""

import os
import sys

import pytest

from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.vision.ocr_mac import MacVisionOcr, ocr_available
from rra.application.ports.vision import OcrPort, OcrUnavailable
from tests.vision_helpers import make_image

LIMITS = SandboxLimits(timeout_sec=120, mem_mb=2048, max_input_mb=2, max_output_mb=4)


def test_port_conformance_and_limits_carry_languages():
    ocr = MacVisionOcr(limits=LIMITS, languages=("ko-KR",), max_pixels=1000)
    assert isinstance(ocr, OcrPort)
    assert ocr.limits.extra == {"languages": ["ko-KR"], "max_pixels": 1000}
    assert ocr.limits.timeout_sec == 120


async def test_unavailable_engine_raises_clear_error(monkeypatch):
    monkeypatch.setattr("rra.adapters.vision.ocr_mac.ocr_available", lambda: False)
    with pytest.raises(OcrUnavailable):
        await MacVisionOcr(limits=LIMITS).recognize(make_image(100, 100))


async def test_oversized_bytes_are_rejected_before_spawning(monkeypatch):
    monkeypatch.setattr("rra.adapters.vision.ocr_mac.ocr_available", lambda: True)
    with pytest.raises(ValueError):
        await MacVisionOcr(limits=LIMITS, max_bytes=10).recognize(b"x" * 11)


@pytest.mark.skipif(not ocr_available(), reason="macOS Vision(ocrmac) 없음")
async def test_real_recognition_in_sandbox_child_returns_lines_with_confidence():
    png = make_image(800, 300, ["Revenue 5,600 million KRW", "2024 total 1,234"])
    result = await MacVisionOcr(limits=LIMITS).recognize(png, mime="image/png")
    text = result.text
    assert "5,600" in text and "1,234" in text
    assert all(0.0 <= ln.confidence <= 1.0 for ln in result.lines)
    assert result.engine == "macos_vision" and result.elapsed_sec is not None


@pytest.mark.skipif(not ocr_available(), reason="macOS Vision(ocrmac) 없음")
async def test_pixel_cap_rejects_large_image_inside_child():
    from rra.adapters.sources._sandbox import ParseRejected

    png = make_image(400, 400, ["x"])
    with pytest.raises(ParseRejected):
        await MacVisionOcr(limits=LIMITS, max_pixels=10_000).recognize(png)


@pytest.mark.skipif(sys.platform != "darwin", reason="임시 파일 fd 경로는 POSIX 전용 검증")
def test_spool_unlinks_path_and_keeps_fd_readable(tmp_path):
    ocr = MacVisionOcr(limits=LIMITS, tmp_dir=tmp_path)
    fd = ocr._spool(b"hello")
    try:
        assert os.read(fd, 10) == b"hello"
        assert list(tmp_path.iterdir()) == []  # 경로는 이미 지워졌다
    finally:
        os.close(fd)
