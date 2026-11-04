"""OpenAI 호환 요청/응답 조립 — 순수 함수. 네트워크·상태 없음."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
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


def build_messages(
    prompt: str, system: str | None, *, system_role: bool = True
) -> list[dict[str, str]]:
    """system_role=False(system 역할이 없는 템플릿)면 시스템 지시를 첫 user 메시지 앞에 붙인다."""
    messages: list[dict[str, str]] = []
    if system and system_role:
        messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
    elif system:
        messages.append({"role": "user", "content": f"{system}\n\n{prompt}"})
    else:
        messages.append({"role": "user", "content": prompt})
    return messages


def build_image_messages(
    prompt: str, image_data_url: str, system: str | None, *, system_role: bool = True
) -> list[dict[str, Any]]:
    """이미지 입력(OpenAI 호환 content parts). 이미지는 data URL(base64) 로만 — 원격 URL 을 보내지
    않는다."""
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]
    if system and system_role:
        return [{"role": "system", "content": system}, {"role": "user", "content": parts}]
    if system:
        parts[0] = {"type": "text", "text": f"{system}\n\n{prompt}"}
    return [{"role": "user", "content": parts}]


def build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    native_json: bool = False,
    reasoning_effort: str | None = None,
    stop: list[str] | None = None,
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
    if stop:
        payload["stop"] = list(stop)[:4]  # OpenAI 호환 상한
    if reasoning_effort:  # gemini 등. thinking_level 은 절대 함께 보내지 않는다 (키 자체가 없다)
        payload["reasoning_effort"] = reasoning_effort
    return payload


def extract_usage(data: Any) -> dict[str, int]:
    """usage.{prompt_tokens, completion_tokens} 가 있으면 정수로. 없으면 빈 dict."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out[key] = value
    return out


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


# ── 오류 응답 분류 (ADR 0055) ───────────────────────────────
# Google(Gemini OpenAI 호환) 오류 본문:
#   {"error": {"code", "message", "status", "details": [{"reason"}]}} — 목록으로 감싸 오기도 한다.
# 로그·예외에는 status·reason 열거값만 싣고 message(본문)는 싣지 않는다.
_ENUM_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
ERROR_BODY_PARSE_LIMIT = 64_000
KEY_INVALID_REASONS = frozenset({"API_KEY_INVALID"})
KEY_INVALID_HINTS = ("api key not valid", "api_key_invalid")
QUOTA_STATUSES = frozenset({"RESOURCE_EXHAUSTED"})
QUOTA_REASONS = frozenset({"insufficient_quota"})
QUOTA_HINTS = ("quota",)


@dataclass(frozen=True)
class ErrorCodes:
    """오류 본문에서 뽑은 열거값 — 형식이 맞는 짧은 영문 식별자만(그 밖의 글자는 버린다)."""

    status: str | None = None  # Google error.status (INVALID_ARGUMENT·RESOURCE_EXHAUSTED …)
    reason: str | None = None  # Google details[].reason (API_KEY_INVALID …) 또는 OpenAI error.code


def _enum(value: Any, secrets: Iterable[str]) -> str | None:
    if not isinstance(value, str) or not _ENUM_CODE.fullmatch(value):
        return None
    for secret in secrets:
        s = (secret or "").strip()
        if len(s) >= 4 and (s in value or value in s):
            return None  # 키 조각일 수 있는 값은 싣지 않는다 (보안 D)
    return value


def error_codes(body: str, secrets: Iterable[str] = ()) -> ErrorCodes:
    """오류 본문(JSON) → ErrorCodes. JSON 이 아니거나 모양이 다르면 빈 값."""
    try:
        data = json.loads(body[:ERROR_BODY_PARSE_LIMIT])
    except (ValueError, TypeError):
        return ErrorCodes()
    if isinstance(data, list) and data:
        data = data[0]
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return ErrorCodes()
    keys = list(secrets)
    reason = None
    details = err.get("details")
    if isinstance(details, list):
        for item in details[:10]:
            if isinstance(item, dict) and (found := _enum(item.get("reason"), keys)):
                reason = found
                break
    if reason is None:
        reason = _enum(err.get("code"), keys)  # OpenAI 형식: code 가 문자열(insufficient_quota …)
    return ErrorCodes(status=_enum(err.get("status"), keys), reason=reason)


# 실패 경고 한 줄 — 텍스트(openai_compat)·그림(image_gen)이 같은 모양. 열거값만(키·URL·본문 없음)
FAILURE_LOG = "llm.failed provider=%s stage=%s kind=%s http=%s status=%s reason=%s"


def failure_args(provider: str, stage: str, exc: Any) -> tuple[str, ...]:
    """FAILURE_LOG 인자 — 어댑터 예외(errors.LLMError)의 code·http_status·api_status·api_reason."""
    http = getattr(exc, "http_status", None)
    return (
        provider,
        stage or "-",
        str(getattr(exc, "code", None) or "error"),
        str(http) if http is not None else "-",
        getattr(exc, "api_status", None) or "-",
        getattr(exc, "api_reason", None) or "-",
    )


def is_key_invalid(status_code: int, body: str, codes: ErrorCodes) -> bool:
    """키 무효 400 — Google 은 401 이 아니라 400 INVALID_ARGUMENT/API_KEY_INVALID 로 답한다."""
    if status_code != 400:
        return False
    if codes.reason in KEY_INVALID_REASONS:
        return True
    low = body[:ERROR_BODY_PARSE_LIMIT].lower()
    return any(h in low for h in KEY_INVALID_HINTS)


def is_quota_exhausted(body: str, codes: ErrorCodes) -> bool:
    """429 중 할당량 소진(RESOURCE_EXHAUSTED·quota 문구) — 그 밖의 429 는 일반 호출 한도."""
    if codes.status in QUOTA_STATUSES or codes.reason in QUOTA_REASONS:
        return True
    low = body[:ERROR_BODY_PARSE_LIMIT].lower()
    return any(h in low for h in QUOTA_HINTS)


def extract_finish_reason(data: Any) -> str | None:
    """choices[0].finish_reason (stop | length | …). 없으면 None. 잘림(length) 집계용."""
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    reason = choices[0].get("finish_reason")
    return reason if isinstance(reason, str) and reason else None
