"""LLMPort 구현 — OpenAI 호환 /v1/chat/completions (mlx-lm · OpenAI 공용).

두 provider 는 base_url·api_key 만 다르다. 나머지 규칙은 동일하다.

보안:
- H: provider=mlx 면 생성자에서 base_url 을 검증하고 루프백이 아니면 기동을 거부한다.
- A: json_mode 는 response_format 을 먼저 시도하고, 서버가 모르면 프롬프트 지시로 폴백한다.
     (파싱 자체는 유스케이스가 pydantic 으로 다시 검증한다)
- D·I: 예외 메시지에 api_key 를 마스킹하고 응답 본문은 200자로 절단한다.
- DoS: max_tokens 상한, 프롬프트 길이 상한, 재시도 횟수·백오프 상한.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from rra.adapters.llm import _endpoint, _payload
from rra.adapters.llm.errors import LLMError, LLMResponseInvalid, LLMTimeout

JsonMode = Literal["auto", "native", "prompt"]

DEFAULT_MAX_TOKENS = 1024
DEFAULT_MAX_TOKENS_CAP = 4096
DEFAULT_PROMPT_MAX_CHARS = 60_000
DEFAULT_TEMPERATURE = 0.2
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

JSON_FALLBACK_INSTRUCTION = (
    "출력은 JSON 하나만 내보내십시오. 코드블록·설명·머리말·꼬리말을 붙이지 마십시오."
)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_sec: float = 0.5
    max_backoff_sec: float = 8.0

    def delay(self, attempt: int) -> float:
        return min(self.backoff_sec * (2 ** (attempt - 1)), self.max_backoff_sec)


class _ResponseFormatUnsupported(Exception):
    """내부 신호. 밖으로 나가지 않는다."""


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        provider: str = "mlx",
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_tokens_cap: int = DEFAULT_MAX_TOKENS_CAP,
        prompt_max_chars: int = DEFAULT_PROMPT_MAX_CHARS,
        temperature: float = DEFAULT_TEMPERATURE,
        json_mode: JsonMode = "auto",
        json_fallback_instruction: str = JSON_FALLBACK_INSTRUCTION,
        timeout: httpx.Timeout | float = 120.0,
        retry: RetryPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if json_mode not in ("auto", "native", "prompt"):
            raise ValueError(f"json_mode 는 auto|native|prompt 중 하나입니다: {json_mode}")
        self.provider = provider
        self.base_url = _endpoint.guard_base_url(provider, base_url)  # H: 위반 시 기동 거부
        self.model = model
        self.max_tokens = max(1, min(max_tokens, max_tokens_cap))
        self.max_tokens_cap = max_tokens_cap
        self.prompt_max_chars = prompt_max_chars
        self.temperature = temperature
        self.json_mode: JsonMode = json_mode
        self.json_fallback_instruction = json_fallback_instruction
        self.retry = retry or RetryPolicy()
        self._url = _endpoint.chat_url(self.base_url)
        self._api_key = (api_key or "").strip()
        self._headers = _endpoint.auth_headers(self._api_key)
        self._sleep = sleep
        self._native_json_supported: bool | None = None
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    def __repr__(self) -> str:  # D: 키가 repr 로 새지 않게 명시적으로 정의
        return (
            f"OpenAICompatLLM(provider={self.provider!r}, "
            f"base_url={self.base_url!r}, model={self.model!r})"
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatLLM:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── LLMPort ────────────────────────────────────────────
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if len(prompt) > self.prompt_max_chars:
            raise LLMError(
                f"프롬프트 길이 {len(prompt)} > 상한 {self.prompt_max_chars}. 전송하지 않았습니다."
            )
        limit = max(1, min(max_tokens or self.max_tokens, self.max_tokens_cap))

        if json_mode and self._try_native():
            payload = _payload.build_payload(
                model=self.model,
                messages=_payload.build_messages(prompt, system),
                max_tokens=limit,
                temperature=self.temperature,
                native_json=True,
            )
            try:
                data = await self._request(payload)
            except _ResponseFormatUnsupported:
                self._native_json_supported = False  # 이후 호출은 처음부터 폴백
            else:
                self._native_json_supported = True
                return _payload.extract_content(data)

        system_text = self._with_fallback(system) if json_mode else system
        payload = _payload.build_payload(
            model=self.model,
            messages=_payload.build_messages(prompt, system_text),
            max_tokens=limit,
            temperature=self.temperature,
            native_json=False,
        )
        return _payload.extract_content(await self._request(payload))

    # ── 내부 ───────────────────────────────────────────────
    def _try_native(self) -> bool:
        if self.json_mode == "prompt":
            return False
        if self.json_mode == "native":
            return True
        return self._native_json_supported is not False

    def _with_fallback(self, system: str | None) -> str:
        if not system:
            return self.json_fallback_instruction
        if self.json_fallback_instruction in system:
            return system
        return f"{system}\n\n{self.json_fallback_instruction}"

    def _redact(self, text: str) -> str:
        return _payload.redact(text, [self._api_key])

    async def _request(self, payload: dict[str, Any]) -> Any:
        native = "response_format" in payload
        last: LLMError | None = None
        for attempt in range(1, self.retry.attempts + 1):
            try:
                resp = await self._client.post(self._url, json=payload, headers=self._headers)
            except httpx.TimeoutException as exc:
                last = LLMTimeout(f"LLM 응답 시간 초과 ({type(exc).__name__})")
            except httpx.TransportError as exc:
                last = LLMError(f"LLM 서버에 연결하지 못했습니다 ({type(exc).__name__})")
            else:
                if resp.status_code < 400:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise LLMResponseInvalid("응답이 JSON 이 아닙니다.") from exc
                body = self._redact(resp.text)
                if native and _payload.is_response_format_error(resp.status_code, resp.text):
                    if self.json_mode == "native":
                        raise LLMError(f"서버가 response_format 을 거부했습니다: {body}")
                    raise _ResponseFormatUnsupported(body)
                message = f"LLM 오류 {resp.status_code}: {body}"
                if resp.status_code not in RETRYABLE_STATUS:
                    raise LLMError(message)  # 4xx 는 재시도하지 않는다
                last = LLMError(message)
            if attempt < self.retry.attempts:
                await self._sleep(self.retry.delay(attempt))
        raise last or LLMError("LLM 호출에 실패했습니다.")
