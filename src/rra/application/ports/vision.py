"""이미지 판독(P3) 포트. 어댑터: adapters/vision (OCR·스냅샷·캐시), adapters/llm/vision_reader
(Argon)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rra.domain.models.vision import ImageItem, OcrResult


class OcrUnavailable(RuntimeError):
    """OCR 엔진이 없다 (macOS 가 아니거나 Vision 프레임워크·ocrmac 미설치).
    파이프라인은 "OCR 없음" 으로 계속."""


@runtime_checkable
class OcrPort(Protocol):
    engine: str

    async def recognize(self, image: bytes, *, mime: str | None = None) -> OcrResult:
        """줄 단위 텍스트+신뢰도. 엔진이 없으면 OcrUnavailable, 격리 실패는 SandboxError 계열."""
        ...


@runtime_checkable
class VisionReaderPort(Protocol):
    """이미지 입력 LLM. 응답은 문자열(JSON 기대) — 파싱·검증은 도메인 규칙(vision_trust)이 한다."""

    provider: str
    model: str

    async def read_image(
        self,
        prompt: str,
        image: bytes,
        *,
        mime: str,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...


@runtime_checkable
class VisionStorePort(Protocol):
    """해시별 캐시(판독 JSON·OCR)와 호출 기록. 키·본문 원문은 기록에 넣지 않는다."""

    def get_reading(self, sha256: str) -> dict[str, Any] | None: ...

    def put_reading(self, sha256: str, payload: dict[str, Any]) -> None: ...

    def get_ocr(self, sha256: str) -> dict[str, Any] | None: ...

    def put_ocr(self, sha256: str, payload: dict[str, Any]) -> None: ...

    def cached_hashes(self) -> set[str]:
        """판독 캐시가 있는 해시 (실패 기록 포함 — 같은 해시는 다시 부르지 않는다)."""
        ...

    def log(self, record: dict[str, Any]) -> None: ...


@runtime_checkable
class ImageSnapshotPort(Protocol):
    snapshot: str

    def list_images(self) -> list[ImageItem]: ...

    def read_image(self, item: ImageItem) -> bytes:
        """상한(바이트)을 넘으면 ValueError. 경로는 스냅샷 폴더 밖으로 나갈 수 없다."""
        ...
