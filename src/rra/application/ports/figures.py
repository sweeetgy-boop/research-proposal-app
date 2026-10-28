"""그림(인포그래픽) 포트 — [G] 2026-10-28.

- `ImageGeneratorPort`: 이미지 생성 AI(Nano Banana Pro). 참고 이미지(밑그림)를 넣어 1회 생성,
  또는 현재 그림을 넣어 요청대로 편집. 실패는 예외 — 유스케이스가 기본 그림(밑그림)으로 대체.
  일일 상한을 넘으면 `ImageBudgetExhausted`.
- `FigureRendererPort`: 명세 → SVG 밑그림 → PNG (adapters/figures).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class ImageBudgetExhausted(RuntimeError):
    """그림 호출 일일 상한(figures.daily_image_cap)에 이르렀다."""


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str  # image/png | image/jpeg
    model: str


@runtime_checkable
class ImageGeneratorPort(Protocol):
    provider: str
    model: str

    async def generate(
        self,
        prompt: str,
        reference: bytes,
        *,
        mime: str = "image/png",
        aspect: str = "16:9",
        size: str = "2K",
    ) -> ImageResult:
        """밑그림을 참고 이미지로 넣어 새 그림 1장. 프롬프트에는 명세 글자 목록만 들어간다."""
        ...

    async def edit(
        self,
        prompt: str,
        image: bytes,
        *,
        mime: str,
        aspect: str = "16:9",
        size: str = "2K",
    ) -> ImageResult:
        """현재 그림을 입력으로 넣고 요청대로 고친 그림 1장 ([말로 고치기])."""
        ...


@runtime_checkable
class FigureRendererPort(Protocol):
    def svg(self, spec: Any, *, caption: str = "") -> str: ...

    def png(self, svg: str) -> bytes: ...
