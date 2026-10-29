"""가짜 모드(RRA_FAKE_LLM=1) 그림 부품 — e2e 전용. 외부 호출 없음.

- `FakeImageGenerator`: 참고 이미지(밑그림)를 그대로 돌려준다(모델명 fake/nano-banana). 호출만 센다.
  `RRA_FAKE_FIGURE_DELAY`(초, 기본 0)만큼 기다린 뒤 돌려준다 — e2e 가 "그림 준비 중" 카드를 볼 수
  있게 (ADR 0045, 그림은 초안 뒤 백그라운드).
- 그림 명세 응답은 `ScriptedComposeLLM` 의 `[그림 명세:` 분기(adapters/fake/llm.py).
"""

from __future__ import annotations

import asyncio
import os

from rra.application.ports.figures import ImageResult


def _delay_from_env() -> float:
    try:
        return max(0.0, min(30.0, float(os.environ.get("RRA_FAKE_FIGURE_DELAY", "0") or 0)))
    except ValueError:
        return 0.0


class FakeImageGenerator:
    provider = "fake"
    model = "fake/nano-banana"

    def __init__(self, delay: float | None = None) -> None:
        self.calls: list[str] = []
        self.delay = _delay_from_env() if delay is None else delay

    async def generate(self, prompt, reference, *, mime="image/png", aspect="16:9", size="2K"):
        self.calls.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        return ImageResult(bytes(reference), mime, self.model)

    async def edit(self, prompt, image, *, mime, aspect="16:9", size="2K"):
        self.calls.append(prompt)
        return ImageResult(bytes(image), mime, self.model)

    async def aclose(self) -> None:
        return None
