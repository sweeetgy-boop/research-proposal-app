"""이미지 판독(P3) 테스트 공용 — PIL 로 만든 fixture 이미지, 포트 페이크. 네트워크·실모델 없음."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from rra.application.ports.vision import OcrUnavailable
from rra.domain.models.vision import ImageItem, OcrLine, OcrResult

_FONTS = (
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(size: int):
    from PIL import ImageFont

    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_image(
    width: int, height: int, lines: list[str] | None = None, *, fmt: str = "PNG"
) -> bytes:
    """글자 줄을 그린 PNG. 글꼴이 없으면 기본 글꼴(한글은 □ 가 될 수 있지만 크기·해시는 유효)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = _font(max(12, min(32, height // 8)))
    y = 10
    for line in lines or []:
        draw.text((10, y), line, fill="black", font=font)
        y += font.size + 8
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def table_image() -> bytes:
    return make_image(
        800, 400, ["구분 | 2023 | 2024", "수송인원 | 1,234만명 | 1,300만명", "증가율 | 3.5% | 5.3%"]
    )


def diagram_image() -> bytes:
    return make_image(
        900, 600, ["비전: 국민과 함께하는 철도", "목표: 안전 최우선", "전략과제: 디지털 전환"]
    )


def icon_image() -> bytes:
    return make_image(32, 32)


def banner_image() -> bytes:
    return make_image(1200, 150, ["함께하는 철도"])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def item(data: bytes, path: str, **kw: Any) -> ImageItem:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
    base = {
        "sha256": sha(data),
        "path": path,
        "url": f"https://info.korail.com/img/{path}",
        "page_url": "https://info.korail.com/vision",
        "page_title": "경영목표",
        "width": w,
        "height": h,
        "bytes": len(data),
        "mime": "image/png",
    }
    base.update(kw)
    return ImageItem(**base)


class FakeSnapshot:
    def __init__(
        self, images: dict[str, bytes], items: list[ImageItem], snapshot: str = "2026-10-27"
    ):
        self.images, self.items, self.snapshot = images, items, snapshot
        self.reads = 0

    def list_images(self) -> list[ImageItem]:
        return list(self.items)

    def read_image(self, it: ImageItem) -> bytes:
        self.reads += 1
        return self.images[it.sha256]


def snapshot_of(*pairs: tuple[bytes, ImageItem]) -> FakeSnapshot:
    return FakeSnapshot({it.sha256: data for data, it in pairs}, [it for _, it in pairs])


class FakeOcr:
    engine = "fake"

    def __init__(self, text_by_hash: dict[str, str] | None = None, *, unavailable: bool = False):
        self.text_by_hash = text_by_hash or {}
        self.unavailable = unavailable
        self.calls = 0

    async def recognize(self, image: bytes, *, mime: str | None = None) -> OcrResult:
        self.calls += 1
        if self.unavailable:
            raise OcrUnavailable("no engine")
        text = self.text_by_hash.get(sha(image), "")
        lines = [OcrLine(text=t, confidence=0.95) for t in text.splitlines() if t.strip()]
        return OcrResult(lines=lines, engine=self.engine)


class FakeReader:
    """VisionReaderPort 페이크 — 응답(문자열) 을 순서대로. fail_at 번째 호출은 예외."""

    provider = "fake-gemini"
    model = "fake-argon"

    def __init__(
        self, responses: list[str | dict] | None = None, *, fail_at: set[int] | None = None
    ):
        self.responses = [
            json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r for r in responses or []
        ]
        self.fail_at = set(fail_at or ())
        self.calls: list[dict[str, Any]] = []

    async def read_image(
        self, prompt, image, *, mime, system=None, max_tokens=None, json_mode=False
    ):
        n = len(self.calls)
        self.calls.append(
            {"prompt": prompt, "sha": sha(image), "mime": mime, "json_mode": json_mode}
        )
        if n in self.fail_at:
            raise RuntimeError("LLM 오류 500: upstream — 키 sk-secret 노출 금지")
        return self.responses.pop(0) if self.responses else "{}"


TABLE_READING = {
    "image_type": "표",
    "title": "수송 실적",
    "text": "구분 | 2023 | 2024\n수송인원 | 1,234만명 | 1,300만명\n증가율 | 3.5% | 5.3%",
    "structure": {
        "cols": ["구분", "2023", "2024"],
        "rows": [["수송인원", "1,234만명", "1,300만명"], ["증가율", "3.5%", "5.3%"]],
        "units": "",
    },
    "summary": "2023·2024 수송인원과 증가율 표",
    "uncertain": False,
}
DIAGRAM_READING = {
    "image_type": "체계도·조직도·흐름도",
    "title": "경영 비전 체계",
    "text": "비전: 국민과 함께하는 철도\n목표: 안전 최우선\n전략과제: 디지털 전환",
    "structure": {
        "비전": "국민과 함께하는 철도",
        "목표": ["안전 최우선"],
        "전략과제": ["디지털 전환"],
    },
    "summary": "비전·목표·전략과제 체계도",
    "uncertain": False,
}
