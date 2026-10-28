"""가짜 모드(RRA_FAKE_LLM=1) 그림 부품 — e2e 전용. 외부 호출 없음.

- `FakeImageGenerator`: 참고 이미지(밑그림)를 그대로 돌려준다(모델명 fake/nano-banana). 호출만 센다.
- 그림 명세 응답은 `ScriptedComposeLLM` 의 `[그림 명세:` 분기(adapters/fake/llm.py).
"""

from __future__ import annotations

from rra.application.ports.figures import ImageResult


class FakeImageGenerator:
    provider = "fake"
    model = "fake/nano-banana"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt, reference, *, mime="image/png", aspect="16:9", size="2K"):
        self.calls.append(prompt)
        return ImageResult(bytes(reference), mime, self.model)

    async def edit(self, prompt, image, *, mime, aspect="16:9", size="2K"):
        self.calls.append(prompt)
        return ImageResult(bytes(image), mime, self.model)

    async def aclose(self) -> None:
        return None
