"""OpenAI 호환 어댑터 — httpx.MockTransport 로 요청/응답을 검증한다. 네트워크 없음."""

import json

import httpx
import pytest

from rra.adapters.llm import _payload
from rra.adapters.llm.errors import (
    InsecureLLMEndpoint,
    LLMError,
    LLMResponseInvalid,
    LLMTimeout,
)
from rra.adapters.llm.openai_compat import JSON_FALLBACK_INSTRUCTION, OpenAICompatLLM, RetryPolicy

BASE = "http://127.0.0.1:8080/v1"
FAKE_KEY = "sk-test-not-a-real-key"  # 실키 형태를 피한다 (gitleaks)


def ok(content="[]"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class Recorder:
    """MockTransport 핸들러. 요청을 기록하고 준비된 응답을 순서대로 돌려준다."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def payloads(self):
        return [json.loads(r.content) for r in self.requests]


async def _noop_sleep(_seconds: float) -> None:
    return None


def build(recorder, **kw):
    kw.setdefault("model", "local-14b")
    kw.setdefault("retry", RetryPolicy(attempts=3, backoff_sec=0))
    return OpenAICompatLLM(
        kw.pop("base_url", BASE),
        kw.pop("model"),
        transport=httpx.MockTransport(recorder),
        sleep=_noop_sleep,
        **kw,
    )


# ── 요청 조립 ─────────────────────────────────────────────
async def test_posts_to_chat_completions_with_expected_payload():
    rec = Recorder(ok('[{"text":"ok","evidence":[]}]'))
    llm = build(rec, max_tokens=512, max_tokens_cap=2000)
    out = await llm.complete("본문", system="시스템")

    assert out == '[{"text":"ok","evidence":[]}]'
    request = rec.requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE}/chat/completions"
    payload = rec.payloads[0]
    assert payload["model"] == "local-14b"
    assert payload["messages"] == [
        {"role": "system", "content": "시스템"},
        {"role": "user", "content": "본문"},
    ]
    assert payload["max_tokens"] == 512
    assert payload["stream"] is False
    assert "response_format" not in payload
    await llm.aclose()


async def test_max_tokens_is_capped():
    rec = Recorder(ok())
    llm = build(rec, max_tokens=512, max_tokens_cap=1000)
    await llm.complete("본문", max_tokens=99_999)
    assert rec.payloads[0]["max_tokens"] == 1000


async def test_local_provider_sends_no_authorization_header():
    rec = Recorder(ok())
    llm = build(rec, api_key="none")
    await llm.complete("본문")
    assert "authorization" not in rec.requests[0].headers


async def test_remote_provider_sends_bearer_and_never_leaks_it():
    rec = Recorder(ok())
    llm = build(rec, base_url="https://api.openai.com/v1", provider="openai", api_key=FAKE_KEY)
    await llm.complete("본문")
    assert rec.requests[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in repr(llm)


async def test_prompt_over_limit_is_rejected_before_sending():
    rec = Recorder(ok())
    llm = build(rec, prompt_max_chars=10)
    with pytest.raises(LLMError, match="전송하지 않았습니다"):
        await llm.complete("x" * 11)
    assert rec.requests == []


# ── json_mode ─────────────────────────────────────────────
async def test_json_mode_uses_native_response_format_when_supported():
    rec = Recorder(ok())
    llm = build(rec)
    await llm.complete("본문", system="시스템", json_mode=True)
    assert rec.payloads[0]["response_format"] == {"type": "json_object"}
    assert JSON_FALLBACK_INSTRUCTION not in rec.payloads[0]["messages"][0]["content"]


async def test_json_mode_falls_back_to_prompt_and_remembers_it():
    rejection = httpx.Response(
        400, json={"error": {"message": "unsupported parameter: response_format"}}
    )
    rec = Recorder(rejection, ok("[]"), ok("[]"))
    llm = build(rec)

    assert await llm.complete("본문", system="시스템", json_mode=True) == "[]"
    assert len(rec.requests) == 2
    assert "response_format" not in rec.payloads[1]
    assert rec.payloads[1]["messages"][0]["content"].endswith(JSON_FALLBACK_INSTRUCTION)

    # 두 번째 호출은 native 를 다시 시도하지 않는다 (요청 1건만 추가).
    await llm.complete("본문2", system="시스템", json_mode=True)
    assert len(rec.requests) == 3
    assert "response_format" not in rec.payloads[2]


async def test_fallback_instruction_used_without_system_prompt():
    rejection = httpx.Response(422, json={"error": "response_format is not supported"})
    rec = Recorder(rejection, ok())
    llm = build(rec)
    await llm.complete("본문", json_mode=True)
    assert rec.payloads[1]["messages"][0] == {
        "role": "system",
        "content": JSON_FALLBACK_INSTRUCTION,
    }


async def test_json_mode_prompt_setting_never_tries_native():
    rec = Recorder(ok())
    llm = build(rec, json_mode="prompt")
    await llm.complete("본문", system="시스템", json_mode=True)
    assert "response_format" not in rec.payloads[0]
    assert JSON_FALLBACK_INSTRUCTION in rec.payloads[0]["messages"][0]["content"]


async def test_json_mode_native_setting_propagates_rejection():
    rec = Recorder(httpx.Response(400, json={"error": "unknown field response_format"}))
    llm = build(rec, json_mode="native")
    with pytest.raises(LLMError, match="response_format"):
        await llm.complete("본문", json_mode=True)
    assert len(rec.requests) == 1


# ── 재시도·타임아웃 ────────────────────────────────────────
async def test_retries_transient_status_then_succeeds():
    rec = Recorder(httpx.Response(503), httpx.Response(503), ok("[]"))
    llm = build(rec)
    assert await llm.complete("본문") == "[]"
    assert len(rec.requests) == 3


async def test_client_error_is_not_retried():
    rec = Recorder(httpx.Response(401, text="bad key"))
    llm = build(rec)
    with pytest.raises(LLMError, match="401"):
        await llm.complete("본문")
    assert len(rec.requests) == 1


async def test_retries_exhausted_raises():
    rec = Recorder(httpx.Response(500, text="boom"))
    llm = build(rec, retry=RetryPolicy(attempts=2, backoff_sec=0))
    with pytest.raises(LLMError):
        await llm.complete("본문")
    assert len(rec.requests) == 2


async def test_timeout_is_retried_then_raises_llm_timeout():
    rec = Recorder(httpx.ReadTimeout("too slow"))
    llm = build(rec, retry=RetryPolicy(attempts=2, backoff_sec=0))
    with pytest.raises(LLMTimeout):
        await llm.complete("본문")
    assert len(rec.requests) == 2


async def test_connect_error_becomes_llm_error():
    rec = Recorder(httpx.ConnectError("refused"))
    llm = build(rec, retry=RetryPolicy(attempts=1, backoff_sec=0))
    with pytest.raises(LLMError, match="연결하지 못했습니다"):
        await llm.complete("본문")


# ── 응답 검증·비밀 보호 ────────────────────────────────────
async def test_error_message_redacts_key_and_truncates_body():
    body = f"key={FAKE_KEY} " + "x" * 5000
    rec = Recorder(httpx.Response(400, text=body))
    llm = build(rec, base_url="https://api.openai.com/v1", provider="openai", api_key=FAKE_KEY)
    with pytest.raises(LLMError) as exc:
        await llm.complete("본문")
    message = str(exc.value)
    assert FAKE_KEY not in message
    assert "***" in message
    assert len(message) < 300


@pytest.mark.parametrize(
    "body",
    [{}, {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {}}]}, {"choices": "x"}],
)
async def test_invalid_response_shape_is_rejected(body):
    rec = Recorder(httpx.Response(200, json=body))
    llm = build(rec)
    with pytest.raises(LLMResponseInvalid):
        await llm.complete("본문")


async def test_non_json_success_body_is_rejected():
    rec = Recorder(httpx.Response(200, text="<html>hi</html>"))
    llm = build(rec)
    with pytest.raises(LLMResponseInvalid):
        await llm.complete("본문")


# ── 보안 H ────────────────────────────────────────────────
def test_remote_base_url_refuses_startup_for_mlx():
    with pytest.raises(InsecureLLMEndpoint):
        OpenAICompatLLM("http://gpu.example.com/v1", "local-14b", provider="mlx")


def test_invalid_json_mode_setting_rejected():
    with pytest.raises(ValueError, match="json_mode"):
        OpenAICompatLLM(BASE, "local-14b", json_mode="yes")


# ── 순수 함수 ─────────────────────────────────────────────
@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (400, "unsupported parameter: response_format", True),
        (422, "response_format is not supported", True),
        (400, "context length exceeded", False),
        (429, "response_format unsupported", False),
        (200, "response_format unsupported", False),
    ],
)
def test_response_format_error_detection(status, body, expected):
    assert _payload.is_response_format_error(status, body) is expected


def test_redact_ignores_short_secrets():
    assert _payload.redact("a none b", ["no"]) == "a none b"


# ── /v1/models (llm-check 진단) ──────────────────────────
async def test_list_models_reads_ids():
    rec = Recorder(
        httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "mlx-community/Qwen2.5-3B-Instruct-4bit"},
                    {"id": 7},
                    "junk",
                    {"id": "/abs/model"},
                ],
            },
        )
    )
    async with build(rec) as llm:
        assert await llm.list_models() == ["mlx-community/Qwen2.5-3B-Instruct-4bit", "/abs/model"]
    assert str(rec.requests[0].url) == f"{BASE}/models"
    assert rec.requests[0].method == "GET"


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(500, text="boom"), LLMError),
        (httpx.Response(200, text="not json"), LLMResponseInvalid),
        (httpx.Response(200, json={"data": "nope"}), LLMResponseInvalid),
    ],
)
async def test_list_models_errors(response, error):
    async with build(Recorder(response)) as llm:
        with pytest.raises(error):
            await llm.list_models()


def test_served_model_listed_is_exact():
    from rra.adapters.llm._endpoint import served_model_listed

    assert served_model_listed({"a/b"}, [" a/b "])
    assert not served_model_listed({"a/B"}, ["a/b"])
    assert not served_model_listed({""}, [""])
