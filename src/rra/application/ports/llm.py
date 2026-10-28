from __future__ import annotations

from typing import Protocol, runtime_checkable


class RateLimited(RuntimeError):
    """원격 LLM 이 재시도 뒤에도 429(호출 한도)로 거절했다. 어댑터가 이 예외(하위 클래스)를 던지면
    유스케이스는 원인을 rate_limit 으로 기록한다 (메시지에 본문·키 없음)."""


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
