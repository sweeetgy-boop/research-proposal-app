"""Gemini 오류 분류 (ADR 0055) — 녹화형 오류 본문(tests/fixtures/llm/gemini_errors)으로
예외 종류·재시도·경고 한 줄·연결 상태 기록·응답 시간 error_code 를 검사한다. 실제 키·네트워크 없음.

2026-10-30 ~ 11-03 사고: Google 은 키 무효를 401 이 아니라 400 INVALID_ARGUMENT/API_KEY_INVALID 로
답했고,
어댑터가 그것을 일반 LLMError 로 올려 로그에 `err=LLMError` 만 남았다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest

from rra.adapters.llm import _payload
from rra.adapters.llm.daily_budget import BudgetedLLM, FileDailyBudget, latency_path
from rra.adapters.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMTimeout,
)
from rra.adapters.llm.openai_compat import OpenAICompatLLM, RetryPolicy
from rra.adapters.llm.status_file import FileLLMStatus
from rra.application.ports import LLMStatusPort, RateLimited

FIXTURES = Path(__file__).parents[1] / "fixtures" / "llm" / "gemini_errors"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"
FAKE_KEY = "test-not-a-real-gemini-key-0000"  # 실키 형태를 피한다 (gitleaks)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class MemoryStatus:
    def __init__(self):
        self.records: list[tuple[str, str]] = []

    def record(self, provider, status):
        self.records.append((provider, status))

    def snapshot(self, provider):
        return None


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


async def _noop_sleep(_s):
    return None


def gemini(rec, status=None, **kw):
    return OpenAICompatLLM(
        GEMINI,
        "gemini-argon",
        provider="gemini",
        api_key=FAKE_KEY,
        allowed_hosts=["generativelanguage.googleapis.com"],
        transport=httpx.MockTransport(rec),
        sleep=_noop_sleep,
        retry=RetryPolicy(attempts=3, backoff_sec=0),
        stage="same_judgment",
        status=status,
        **kw,
    )


def respond(status: int, name: str) -> httpx.Response:
    return httpx.Response(status, text=fixture(name))


def ok():
    return httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]})


def _only_failure_line(caplog) -> str:
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("llm.failed")]
    assert len(lines) == 1, lines  # 실패 1건 = 경고 1줄 (재시도마다 아님)
    assert all(r.levelno == logging.WARNING for r in caplog.records if r.getMessage() in lines)
    return lines[0]


def _assert_no_leak(text: str, body: str) -> None:
    assert FAKE_KEY not in text
    assert "generativelanguage" not in text and "?key=" not in text  # URL·쿼리 없음
    message = json.loads(body)
    message = (message[0] if isinstance(message, list) else message)["error"]["message"]
    assert message not in text  # 본문 글은 열거값 말고는 싣지 않는다


# ── 분류 (재시도·예외 종류·상태) ─────────────────────────────
@pytest.mark.parametrize(
    ("status", "name", "exc_type", "code", "attempts", "state", "api_status", "api_reason"),
    [
        (
            400,
            "400_key_invalid.json",
            LLMAuthError,
            "auth",
            1,
            "key_invalid",
            "INVALID_ARGUMENT",
            "API_KEY_INVALID",
        ),  # noqa: E501
        (
            401,
            "401.json",
            LLMAuthError,
            "auth",
            1,
            "key_invalid",
            "UNAUTHENTICATED",
            "ACCESS_TOKEN_TYPE_UNSUPPORTED",
        ),  # noqa: E501
        (403, "403.json", LLMAuthError, "auth", 1, "key_invalid", "PERMISSION_DENIED", None),
        (429, "429_quota.json", LLMQuotaExceeded, "quota", 3, "quota", "RESOURCE_EXHAUSTED", None),
        (
            429,
            "429_rate.json",
            LLMRateLimited,
            "rate_limit",
            3,
            "quota",
            None,
            "rate_limit_exceeded",
        ),  # noqa: E501
        (503, "503.json", LLMError, "server", 3, "unavailable", "UNAVAILABLE", None),
    ],
)
async def test_recorded_errors_are_classified_logged_once_and_recorded(
    caplog, status, name, exc_type, code, attempts, state, api_status, api_reason
):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    rec = Recorder(respond(status, name))
    sink = MemoryStatus()
    llm = gemini(rec, sink)
    with pytest.raises(exc_type) as exc:
        await llm.complete("p")
    await llm.aclose()

    err = exc.value
    assert type(err) is exc_type and isinstance(err, LLMError)
    assert err.code == code and err.http_status == status
    assert (err.api_status, err.api_reason) == (api_status, api_reason)
    assert len(rec.requests) == attempts  # 인증 실패는 재시도 없음, 429·5xx 는 기존 재시도 그대로
    assert sink.records == [("gemini", state)]
    if code in ("auth", "quota", "rate_limit"):  # 분류된 실패는 예외 메시지에도 본문 없음
        _assert_no_leak(str(err), fixture(name))

    line = _only_failure_line(caplog)
    assert line.startswith(f"llm.failed provider=gemini stage=same_judgment kind={code} ")
    assert f"http={status}" in line
    assert f"status={api_status or '-'}" in line and f"reason={api_reason or '-'}" in line
    _assert_no_leak(line, fixture(name))


async def test_quota_and_rate_limit_stay_rate_limited_for_the_usecases():
    """유스케이스는 RateLimited 로 rate_limit 을 기록한다 — 할당량 소진도 그 하위 클래스."""
    for name in ("429_quota.json", "429_rate.json"):
        llm = gemini(Recorder(respond(429, name)))
        with pytest.raises(RateLimited):
            await llm.complete("p")
        await llm.aclose()


async def test_400_that_is_not_about_the_key_stays_a_plain_error_without_retry(caplog):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    body = json.dumps(
        {
            "error": {
                "code": 400,
                "message": "Invalid value at 'contents'",
                "status": "INVALID_ARGUMENT",
            }
        }
    )
    sink = MemoryStatus()
    rec = Recorder(httpx.Response(400, text=body))
    llm = gemini(rec, sink)
    with pytest.raises(LLMError) as exc:
        await llm.complete("p")
    assert not isinstance(exc.value, LLMAuthError)
    assert exc.value.code == "http" and len(rec.requests) == 1
    assert sink.records == [("gemini", "unavailable")]
    assert "kind=http http=400 status=INVALID_ARGUMENT reason=-" in _only_failure_line(caplog)


async def test_key_invalid_text_without_json_is_still_auth():
    rec = Recorder(httpx.Response(400, text="API key not valid. Please pass a valid API key."))
    with pytest.raises(LLMAuthError):
        await gemini(rec).complete("p")
    assert len(rec.requests) == 1


async def test_timeout_and_connection_failures_are_unavailable(caplog):
    caplog.set_level(logging.WARNING, logger="rra.llm")
    for error, exc_type, code in (
        (httpx.ReadTimeout("slow"), LLMTimeout, "timeout"),
        (httpx.ConnectError("refused"), LLMError, "connection"),
    ):
        sink = MemoryStatus()
        rec = Recorder(error)
        with pytest.raises(exc_type) as exc:
            await gemini(rec, sink).complete("p")
        assert exc.value.code == code and exc.value.http_status is None
        assert len(rec.requests) == 3
        assert sink.records == [("gemini", "unavailable")]
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("llm.failed")]
    assert [ln.split(" kind=")[1].split(" ")[0] for ln in lines] == ["timeout", "connection"]
    assert all("http=- status=- reason=-" in ln for ln in lines)


async def test_success_records_ok_and_not_sent_prompt_changes_nothing():
    sink = MemoryStatus()
    llm = gemini(Recorder(ok()), sink, prompt_max_chars=10)
    assert await llm.complete("짧음") == "[]"
    with pytest.raises(LLMError) as exc:
        await llm.complete("x" * 11)  # 보내지 않은 호출은 연결 상태와 무관
    assert exc.value.code == "not_sent"
    assert sink.records == [("gemini", "ok")]


async def test_key_shaped_codes_are_dropped_from_the_parsed_codes():
    body = json.dumps({"error": {"status": FAKE_KEY.replace("-", "_"), "code": 400}})
    codes = _payload.error_codes(body, [FAKE_KEY.replace("-", "_")])
    assert codes.status is None
    weird = json.dumps(
        {"error": {"status": "has spaces and <html>", "details": [{"reason": "x" * 80}]}}
    )
    assert _payload.error_codes(weird) == _payload.ErrorCodes()
    assert _payload.error_codes("<html>bad gateway</html>") == _payload.ErrorCodes()


# ── 상태 파일 (FileLLMStatus) ────────────────────────────────
def test_status_file_keeps_since_while_the_status_holds(tmp_path):
    from datetime import datetime, timedelta

    t0 = datetime.fromisoformat("2026-11-03T16:14:49+09:00")
    clock = {"now": t0}
    store = FileLLMStatus(tmp_path / "cache" / "llm_status.json", now=lambda: clock["now"])
    assert isinstance(store, LLMStatusPort)
    assert store.snapshot("gemini") is None

    store.record("gemini", "key_invalid")
    clock["now"] = t0 + timedelta(minutes=30)
    store.record("gemini", "key_invalid")
    snap = store.snapshot("gemini")
    assert snap == {
        "status": "key_invalid",
        "since": "2026-11-03T16:14:49+09:00",
        "checked_at": "2026-11-03T16:44:49+09:00",
    }
    clock["now"] = t0 + timedelta(hours=1, minutes=14)
    store.record("gemini", "ok")
    snap = store.snapshot("gemini")
    assert snap["status"] == "ok" and snap["since"] == "2026-11-03T17:28:49+09:00"
    # 같은 상태를 1분 안에 다시 적지 않는다 (성공 호출마다 디스크 쓰기 없음)
    clock["now"] = t0 + timedelta(hours=1, minutes=14, seconds=30)
    store.record("gemini", "ok")
    assert store.snapshot("gemini")["checked_at"] == "2026-11-03T17:28:49+09:00"
    # 열거값·시각만 — 파일 권한 600
    text = (tmp_path / "cache" / "llm_status.json").read_text(encoding="utf-8")
    assert set(json.loads(text)["gemini"]) == {"status", "since", "checked_at"}
    assert oct((tmp_path / "cache" / "llm_status.json").stat().st_mode & 0o777) == "0o600"


def test_status_file_ignores_unknown_states_and_broken_files(tmp_path):
    path = tmp_path / "llm_status.json"
    store = FileLLMStatus(path)
    store.record("gemini", "exploded")
    assert not path.exists()
    path.write_text("{not json", encoding="utf-8")
    assert store.snapshot("gemini") is None
    store.record("gemini", "quota")
    assert store.snapshot("gemini")["status"] == "quota"


async def test_adapter_writes_the_status_file_end_to_end(tmp_path):
    store = FileLLMStatus(tmp_path / "llm_status.json")
    llm = gemini(Recorder(respond(400, "400_key_invalid.json")), store)
    with pytest.raises(LLMAuthError):
        await llm.complete("p")
    assert store.snapshot("gemini")["status"] == "key_invalid"
    assert FAKE_KEY not in (tmp_path / "llm_status.json").read_text(encoding="utf-8")


# ── 응답 시간 기록 error_code ─────────────────────────────────
def test_latency_row_carries_the_error_code_without_body(tmp_path):
    budget = FileDailyBudget(tmp_path / "llm_budget.json", 5)
    inner = gemini(Recorder(respond(400, "400_key_invalid.json")))
    llm = BudgetedLLM(inner, budget, stage="same_judgment")

    async def run():
        with pytest.raises(LLMAuthError):
            await llm.complete("비밀 프롬프트")

    asyncio.run(run())
    text = latency_path(budget).read_text(encoding="utf-8")
    row = json.loads(text.splitlines()[-1])
    assert (row["stage"], row["ok"], row["error"], row["error_code"]) == (
        "same_judgment",
        False,
        "LLMAuthError",
        "auth",
    )
    assert "비밀" not in text and "API key" not in text and FAKE_KEY not in text
