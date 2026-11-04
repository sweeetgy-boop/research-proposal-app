"""[G] 그림 생성 오류 분류·경고 한 줄·연결 상태 (ADR 0055 덧붙임, 2026-11-04).

텍스트 호출(openai_compat)과 같은 녹화형 오류 본문(tests/fixtures/llm/gemini_errors)으로 예외 종류·
재시도·`llm.failed … stage=figure_image` 줄·상태 기록 규칙을 본다. 상태 규칙: 그림 결과는
gemini_image 에, 키 무효는 gemini(띠)에도, 그림 성공은 gemini 가 key_invalid 일 때만 ok 로,
그림의 할당량·응답 없음은 gemini 를 바꾸지 않는다. 실제 키·네트워크 없음(httpx MockTransport).
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
import pytest

from rra.adapters.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMTimeout,
)
from rra.adapters.llm.image_gen import GeminiImageGenerator
from rra.adapters.llm.rate_limiter import RateLimiter
from rra.adapters.llm.status_file import FileLLMStatus
from rra.domain.rules.llm_status import public_view

FIXTURES = Path(__file__).parents[1] / "fixtures" / "llm" / "gemini_errors"
BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
HOSTS = ["generativelanguage.googleapis.com"]
FAKE_KEY = "test-not-a-real-gemini-key-0000"  # 실키 형태를 피한다 (gitleaks)
PNG = b"\x89PNG\r\n\x1a\nfake"
BODY_WORDS = ("API key not valid", "exceeded your current quota", "billing")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok_response():
    data = base64.b64encode(b"IMG").decode()
    return {
        "candidates": [
            {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": data}}]}}
        ]
    }


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def error(code: int, name: str) -> httpx.Response:
    return httpx.Response(
        code,
        text=fixture(name),
        headers={"content-type": "application/json", "retry-after": "0"},
    )


@pytest.fixture
def status(tmp_path) -> FileLLMStatus:
    return FileLLMStatus(tmp_path / "cache" / "llm_status.json", min_write_interval=0)


def make(rec, status=None, attempts=3):
    return GeminiImageGenerator(
        base_url=BASE,
        api_key=FAKE_KEY,
        allowed_hosts=HOSTS,
        transport=httpx.MockTransport(rec),
        backoff_sec=0.0,
        attempts=attempts,
        limiter=RateLimiter(concurrency=2, per_minute=0, backoff_base_sec=0.0),
        status=status,
    )


def failure_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("llm.failed")]


def assert_no_secret_or_body(caplog):
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in text and "googleapis" not in text
    assert not any(w in text for w in BODY_WORDS)


def state(status: FileLLMStatus, provider: str) -> str | None:
    snap = status.snapshot(provider)
    return snap["status"] if snap else None


async def test_image_400_key_invalid_is_auth_error_and_marks_gemini_key_invalid(caplog, status):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    rec = Recorder(error(400, "400_key_invalid.json"))
    gen = make(rec, status)
    with pytest.raises(LLMAuthError) as info:
        await gen.generate("글자 목록", PNG)
    exc = info.value
    assert exc.code == "auth" and exc.http_status == 400 and len(rec.requests) == 1  # 재시도 없음
    assert (exc.api_status, exc.api_reason) == ("INVALID_ARGUMENT", "API_KEY_INVALID")
    assert FAKE_KEY not in str(exc) and "API key not valid" not in str(exc)
    assert failure_lines(caplog) == [
        "llm.failed provider=gemini stage=figure_image kind=auth http=400 "
        "status=INVALID_ARGUMENT reason=API_KEY_INVALID"
    ]
    assert_no_secret_or_body(caplog)
    # 같은 키 — 텍스트(띠·/healthz) 상태도 key_invalid
    assert state(status, "gemini") == "key_invalid"
    assert state(status, "gemini_image") == "key_invalid"
    assert public_view(status.snapshot("gemini"))["gemini"] == "key_invalid"


@pytest.mark.parametrize("code", [401, 403])
async def test_image_401_403_stay_auth_errors_without_retry(code, status):
    rec = Recorder(error(code, f"{code}.json"))
    with pytest.raises(LLMAuthError):
        await make(rec, status).generate("p", PNG)
    assert len(rec.requests) == 1 and state(status, "gemini") == "key_invalid"


async def test_image_429_quota_records_gemini_image_only_and_keeps_text_status(caplog, status):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    status.record("gemini", "ok")
    before = status.snapshot("gemini")
    rec = Recorder(error(429, "429_quota.json"))
    with pytest.raises(LLMQuotaExceeded) as info:
        await make(rec, status).generate("p", PNG)
    assert info.value.code == "quota" and len(rec.requests) == 3  # 재시도는 그대로
    assert failure_lines(caplog) == [
        "llm.failed provider=gemini stage=figure_image kind=quota http=429 "
        "status=RESOURCE_EXHAUSTED reason=-"
    ]
    assert_no_secret_or_body(caplog)
    assert state(status, "gemini_image") == "quota"
    assert status.snapshot("gemini") == before  # 띠·/healthz 는 그대로


async def test_image_429_rate_and_503_are_unchanged_for_text_status(status):
    rec = Recorder(error(429, "429_rate.json"))
    with pytest.raises(LLMRateLimited) as info:
        await make(rec, status).generate("p", PNG)
    assert not isinstance(info.value, LLMQuotaExceeded) and info.value.code == "rate_limit"
    assert state(status, "gemini_image") == "quota" and status.snapshot("gemini") is None
    rec = Recorder(error(503, "503.json"))
    with pytest.raises(LLMError) as info:
        await make(rec, status).generate("p", PNG)
    assert info.value.code == "server" and len(rec.requests) == 3
    assert state(status, "gemini_image") == "unavailable" and status.snapshot("gemini") is None


async def test_image_timeout_and_connection_failures_are_classified(caplog, status):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(LLMTimeout):
        await make(rec, status, attempts=2).generate("p", PNG)
    assert len(rec.requests) == 2
    rec = Recorder(httpx.ConnectError("down"))
    with pytest.raises(LLMError) as info:
        await make(rec, status, attempts=1).generate("p", PNG)
    assert info.value.code == "connection"
    lines = failure_lines(caplog)
    assert [line.split()[3] for line in lines] == ["kind=timeout", "kind=connection"]
    assert state(status, "gemini_image") == "unavailable" and status.snapshot("gemini") is None


async def test_image_success_after_key_invalid_sets_gemini_ok_but_not_after_quota(status):
    status.record("gemini", "key_invalid")
    await make(Recorder(httpx.Response(200, json=ok_response())), status).generate("p", PNG)
    assert state(status, "gemini") == "ok" and state(status, "gemini_image") == "ok"
    # 텍스트가 quota 면 그림 성공이 그것을 덮지 않는다 (텍스트 대체는 여전히 로컬)
    status.record("gemini", "quota")
    await make(Recorder(httpx.Response(200, json=ok_response())), status).generate("q", PNG)
    assert state(status, "gemini") == "quota"


async def test_not_sent_and_no_status_port_change_nothing(caplog, status):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    rec = Recorder(httpx.Response(200, json=ok_response()))
    gen = make(rec, status)
    with pytest.raises(LLMError) as info:
        await gen.generate("p" * 7000, PNG)  # 보내지 않았다
    assert info.value.code == "not_sent" and rec.requests == []
    assert failure_lines(caplog) == [] and status.snapshot("gemini_image") is None
    # 상태 기록기가 없어도(가짜·조립 없음) 분류·경고는 같다
    with pytest.raises(LLMAuthError):
        await make(Recorder(error(400, "400_key_invalid.json"))).generate("p", PNG)
    assert len(failure_lines(caplog)) == 1
