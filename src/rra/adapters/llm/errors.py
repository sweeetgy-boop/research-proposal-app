"""LLM 어댑터 예외. 메시지에는 본문·키를 그대로 담지 않는다 (보안 D·I)."""

from __future__ import annotations


class LLMError(RuntimeError):
    """LLM 호출 실패 일반."""


class LLMTimeout(LLMError):
    """타임아웃. 재시도 소진 후 올라온다."""


class LLMResponseInvalid(LLMError):
    """응답이 OpenAI 호환 스키마가 아님."""


class LLMAuthError(LLMError):
    """401/403 — 재시도하지 않는다. 메시지에 키·응답 본문을 넣지 않는다."""


class InsecureLLMEndpoint(ValueError):
    """H. 허용되지 않은 LLM 엔드포인트 — 기동 거부."""
