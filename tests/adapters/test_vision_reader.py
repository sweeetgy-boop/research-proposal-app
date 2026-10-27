"""Argon 판독 어댑터 — 이미지 data URL 파트, JSON 모드, 상한·형식 거부. MockTransport."""

import base64
import json

import httpx
import pytest

from rra.adapters.llm._payload import build_image_messages
from rra.adapters.llm.errors import InsecureLLMEndpoint, LLMError
from rra.adapters.llm.openai_compat import RetryPolicy
from rra.adapters.llm.vision_reader import OpenAICompatVisionReader
from rra.application.ports.vision import VisionReaderPort
from tests.vision_helpers import make_image

BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
ALLOWED = ["generativelanguage.googleapis.com"]


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def _noop(_s):
    return None


def build(rec, **kw):
    return OpenAICompatVisionReader(
        BASE,
        "gemini-4-argon",
        provider="gemini",
        api_key="sk-test-not-real",
        allowed_hosts=ALLOWED,
        transport=httpx.MockTransport(rec),
        sleep=_noop,
        retry=RetryPolicy(attempts=2, backoff_sec=0),
        **kw,
    )


async def test_sends_text_and_data_url_parts_with_native_json():
    rec = Recorder(ok('{"image_type":"표"}'))
    reader = build(rec, json_mode="native")
    png = make_image(300, 200, ["1"])
    out = await reader.read_image("판독", png, mime="image/png", system="SYS", json_mode=True)

    assert out == '{"image_type":"표"}'
    assert isinstance(reader, VisionReaderPort)
    payload = json.loads(rec.requests[0].content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0] == {"role": "system", "content": "SYS"}
    parts = payload["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "판독"}
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == png
    assert rec.requests[0].headers["Authorization"] == "Bearer sk-test-not-real"


async def test_prompt_fallback_when_system_role_is_absent():
    msgs = build_image_messages("P", "data:image/png;base64,AA==", "S", system_role=False)
    assert len(msgs) == 1 and msgs[0]["content"][0]["text"] == "S\n\nP"


async def test_rejects_bad_mime_oversized_and_empty_without_sending():
    rec = Recorder(ok("{}"))
    reader = build(rec, max_image_bytes=100)
    with pytest.raises(LLMError, match="형식"):
        await reader.read_image("p", b"x", mime="image/gif")
    with pytest.raises(LLMError, match="상한"):
        await reader.read_image("p", b"x" * 101, mime="image/png")
    with pytest.raises(LLMError, match="빈"):
        await reader.read_image("p", b"", mime="image/png")
    assert rec.requests == []


def test_remote_host_must_be_allowed_and_https():
    with pytest.raises(InsecureLLMEndpoint):
        OpenAICompatVisionReader(
            BASE, "m", provider="gemini", api_key="k", allowed_hosts=["other.example"]
        )
    with pytest.raises(InsecureLLMEndpoint):
        OpenAICompatVisionReader(
            "http://generativelanguage.googleapis.com/v1", "m", provider="gemini"
        )
