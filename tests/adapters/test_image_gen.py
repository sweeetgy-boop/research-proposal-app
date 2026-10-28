"""[G] GeminiImageGenerator — generateContent 이미지 출력(요청·키 헤더·응답 파싱), 재시도, 상한,
캐시. 네트워크 없음(httpx MockTransport)."""

import base64
import json

import httpx
import pytest

from rra.adapters.llm.errors import InsecureLLMEndpoint, LLMError
from rra.adapters.llm.image_gen import GeminiImageGenerator, native_base_url
from rra.adapters.llm.rate_limiter import RateLimiter
from rra.application.ports import ImageBudgetExhausted, ImageGeneratorPort

BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
HOSTS = ["generativelanguage.googleapis.com"]
PNG = b"\x89PNG\r\n\x1a\nfake"


def ok_response(data: bytes = b"JPEGDATA", mime: str = "image/jpeg"):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "설명"},
                        {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}},
                    ]
                }
            }
        ],
        "usageMetadata": {"promptTokenCount": 1},
    }


def make(handler, **kw):
    kw.setdefault("limiter", RateLimiter(concurrency=2, per_minute=0))
    return GeminiImageGenerator(
        base_url=BASE,
        api_key="secret-key-123",
        allowed_hosts=HOSTS,
        transport=httpx.MockTransport(handler),
        backoff_sec=0.0,
        **kw,
    )


def test_native_base_url_and_endpoint_guard():
    assert native_base_url(BASE) == "https://generativelanguage.googleapis.com/v1beta"
    assert isinstance(make(lambda r: httpx.Response(200)), ImageGeneratorPort)
    with pytest.raises(InsecureLLMEndpoint):
        GeminiImageGenerator(
            base_url="https://evil.example/v1beta", api_key="k", allowed_hosts=HOSTS
        )
    with pytest.raises(LLMError):
        GeminiImageGenerator(base_url=BASE, api_key=" ", allowed_hosts=HOSTS)


async def test_request_shape_key_header_and_response_parsing():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ok_response())

    gen = make(handler, model="gemini-3-pro-image")
    result = await gen.generate("글자 목록:\n- 현황", PNG, aspect="21:9", size="2K")
    assert (
        result.data == b"JPEGDATA"
        and result.mime == "image/jpeg"
        and result.model == "gemini-3-pro-image"
    )
    req = seen[0]
    assert (
        req.url
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image:generateContent"
    )
    assert req.headers["x-goog-api-key"] == "secret-key-123" and "secret-key-123" not in str(
        req.url
    )
    body = json.loads(req.content)
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "글자 목록:\n- 현황"}
    assert parts[1]["inline_data"]["mime_type"] == "image/png"
    assert base64.b64decode(parts[1]["inline_data"]["data"]) == PNG
    assert body["generationConfig"] == {
        "responseModalities": ["IMAGE", "TEXT"],
        "imageConfig": {"aspectRatio": "21:9", "imageSize": "2K"},
    }
    edited = await gen.edit("화살표를 굵게", b"JPEGDATA", mime="image/jpeg")
    assert (
        edited.data == b"JPEGDATA"
        and json.loads(seen[1].content)["contents"][0]["parts"][1]["inline_data"]["mime_type"]
        == "image/jpeg"
    )
    assert gen.calls == 2
    await gen.aclose()


async def test_retries_on_429_and_5xx_but_not_on_401_and_text_only_response_fails():
    codes = iter([429, 503, 200])

    def flaky(request):
        code = next(codes)
        return httpx.Response(
            code,
            json=ok_response() if code == 200 else {"error": "x"},
            headers={"retry-after": "0"},
        )

    gen = make(flaky, attempts=3)
    assert (await gen.generate("p", PNG)).data == b"JPEGDATA" and gen.calls == 3
    gen401 = make(lambda r: httpx.Response(401, json={"error": "nope"}), attempts=3)
    with pytest.raises(LLMError) as info:
        await gen401.generate("p", PNG)
    assert "인증" in str(info.value) and gen401.calls == 1
    text_only = make(
        lambda r: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "못 그림"}]}}]}
        )
    )
    with pytest.raises(LLMError):
        await text_only.generate("p", PNG)
    blocked = make(lambda r: httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]}))
    with pytest.raises(LLMError) as info:
        await blocked.generate("p", PNG)
    assert "SAFETY" in str(info.value)


async def test_input_limits_and_daily_cap_and_cache(tmp_path):
    class Budget:
        def __init__(self, n):
            self.n = n

        def try_spend(self, k=1):
            if self.n <= 0:
                return False
            self.n -= 1
            return True

        def exhausted(self):
            return self.n <= 0

        def remaining(self):
            return self.n

    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=ok_response(b"IMG" + bytes(len(calls))))

    gen = make(handler, budget=Budget(1), cache_dir=tmp_path / "cache")
    with pytest.raises(LLMError):
        await gen.generate("p", PNG, mime="image/gif")
    with pytest.raises(LLMError):
        await gen.generate("p" * 7000, PNG)
    first = await gen.generate("p", PNG)
    again = await gen.generate("p", PNG)  # 같은 프롬프트·밑그림 → 캐시 (호출·상한 소비 없음)
    assert first.data == again.data and len(calls) == 1
    assert sorted(p.suffix for p in (tmp_path / "cache").iterdir()) == [".jpg", ".json"]
    with pytest.raises(ImageBudgetExhausted):
        await gen.generate("다른 프롬프트", PNG)
    assert len(calls) == 1
