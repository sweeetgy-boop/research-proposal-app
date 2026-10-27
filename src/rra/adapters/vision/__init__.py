"""이미지 판독(P3) 어댑터 — 스냅샷 manifest 읽기, 해시별 캐시·기록, macOS Vision OCR(격리 실행)."""

from .manifest import SnapshotImages, latest_snapshot
from .ocr_mac import MacVisionOcr, ocr_available
from .store import FileVisionStore

__all__ = [
    "ExtractAttachmentImages",
    "ExtractReport",
    "FileVisionStore",
    "MacVisionOcr",
    "SnapshotImages",
    "latest_snapshot",
    "ocr_available",
]
from rra.adapters.vision.attachments import ExtractAttachmentImages, ExtractReport  # noqa: E402
