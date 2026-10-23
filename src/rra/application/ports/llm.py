from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMPort(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...


@runtime_checkable
class ModelListingPort(Protocol):
    """진단용 (선택): 서버가 제공하는 모델 id 목록. LLM 어댑터가 함께 구현할 수 있다."""

    async def list_models(self) -> list[str]: ...
