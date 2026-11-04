"""LLM 어댑터 예외. 메시지에는 본문·키를 그대로 담지 않는다 (보안 D·I).

`code` 는 실패 종류(짧은 영문 열거값) — 응답 시간 기록(`*.latency.jsonl` error_code)·Argon 연결 상태
(domain/rules/llm_status)·`rra llm-check` 분류 표시가 쓴다. `http_status` 는 HTTP 응답이 있었을
때만.
2026-11-04 ADR 0055: 키 무효 400 이 일반 LLMError 로 묻혀 나흘간 아무도 몰랐던 사고 뒤 더했다.
"""

from __future__ import annotations

from rra.application.ports.llm import RateLimited


class LLMError(RuntimeError):
    """LLM 호출 실패 일반."""

    code = "error"

    def __init__(
        self,
        *args: object,
        code: str | None = None,
        http_status: int | None = None,
        api_status: str | None = None,
        api_reason: str | None = None,
    ):
        super().__init__(*args)
        if code:
            self.code = code
        self.http_status = http_status
        # 오류 본문의 열거값만 (Google status·reason, _payload.error_codes) — 본문 글은 담지 않는다
        self.api_status = api_status
        self.api_reason = api_reason


class LLMTimeout(LLMError):
    """타임아웃. 재시도 소진 후 올라온다."""

    code = "timeout"


class LLMResponseInvalid(LLMError):
    """응답이 OpenAI 호환 스키마가 아님."""

    code = "invalid"


class LLMRateLimited(LLMError, RateLimited):
    """429 — 재시도(Retry-After·공유 백오프)까지 소진. 유스케이스는 rate_limit 으로 기록한다."""

    code = "rate_limit"


class LLMQuotaExceeded(LLMRateLimited):
    """429 중 할당량 소진(Google RESOURCE_EXHAUSTED·quota 문구). 재시도는 일반 429 와 같고, 소진 뒤
    이 예외로 올라온다 — RateLimited 하위라 유스케이스의 rate_limit 기록은 그대로다."""

    code = "quota"


class LLMAuthError(LLMError):
    """401/403, 그리고 키 무효 400(Google API_KEY_INVALID) — 재시도하지 않는다. 메시지에 키·응답
    본문을 넣지 않는다."""

    code = "auth"


class InsecureLLMEndpoint(ValueError):
    """H. 허용되지 않은 LLM 엔드포인트 — 기동 거부."""
