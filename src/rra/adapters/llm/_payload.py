"""OpenAI 호환 요청/응답 조립 — 순수 함수. 네트워크·상태 없음."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rra.adapters.llm.errors import LLMResponseInvalid

JSON_OBJECT_FORMAT = {"type": "json_object"}
_RESPONSE_FORMAT_HINTS = (
    "response_format",
    "response format",
    "json_object",
    "json_schema",
    "guided_json",
)
_UNSUPPORTED_HINTS = ("unsupported", "not supported", "unknown", "unrecognized", "invalid", "extra")
ERROR_BODY_LIMIT = 200


def build_messages(prompt: str, system: str | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def build_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    native_json: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if native_json:
        payload["response_format"] = dict(JSON_OBJECT_FORMAT)
    return payload


def extract_content(data: Any) -> str:
    """choices[0].message.content 만 수용. 그 외 형태는 전부 거부 (보안 A)."""
    if not isinstance(data, dict):
        raise LLMResponseInvalid("응답이 JSON 객체가 아닙니다.")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseInvalid("응답에 choices 가 없습니다.")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMResponseInvalid("choices[0] 형식이 올바르지 않습니다.")
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMResponseInvalid("choices[0].message.content 가 문자열이 아닙니다.")
    return content


def is_response_format_error(status_code: int, body: str) -> bool:
    """서버가 response_format 을 모르는 경우인지 판정 → 프롬프트 지시로 폴백."""
    if status_code not in (400, 404, 422, 500):
        return False
    low = body.lower()
    return any(h in low for h in _RESPONSE_FORMAT_HINTS) and any(
        h in low for h in _UNSUPPORTED_HINTS
    )


def redact(text: str, secrets: Iterable[str] = (), *, limit: int = ERROR_BODY_LIMIT) -> str:
    """오류 메시지용. 비밀 문자열 마스킹 후 절단 (보안 D·I)."""
    out = text
    for secret in secrets:
        s = (secret or "").strip()
        if len(s) >= 4:
            out = out.replace(s, "***")
    out = " ".join(out.split())
    return out[:limit] + "…" if len(out) > limit else out
