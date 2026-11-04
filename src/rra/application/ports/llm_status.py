from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMStatusPort(Protocol):
    """원격 LLM 연결 상태 기록 (ADR 0055) — provider 별 마지막 호출 결과.

    record(provider, status): status 는 domain/rules/llm_status.STATES 중 하나. 기록 실패가 호출을
    막지 않는다(구현이 삼킨다). snapshot(provider): {status, since, checked_at} 또는
    None(기록 없음).
    열거값·시각만 — 키·주소·응답 본문은 담지 않는다(보안 D).
    """

    def record(self, provider: str, status: str) -> None: ...

    def snapshot(self, provider: str) -> dict[str, Any] | None: ...
