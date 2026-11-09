"""OpenAI 호환 어댑터 — 로컬 첫 요청(모델 적재) 읽기 제한 `first_request_timeout`.
첫 전송에만 read 를 first_request 이상으로 늘리고, 둘째부터는 클라이언트 기본. 원격은 안 쓴다."""

import httpx

from rra.adapters.llm.openai_compat import OpenAICompatLLM, RetryPolicy


class Recorder:
    def __init__(self):
        self.timeouts: list[httpx.Timeout] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.timeouts.append(request.extensions.get("timeout"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})


async def _noop(_s: float) -> None:
    return None


def _llm(rec, provider="mlx", base="http://127.0.0.1:8080/v1", **kw):
    return OpenAICompatLLM(
        base,
        "m",
        provider=provider,
        transport=httpx.MockTransport(rec),
        sleep=_noop,
        retry=RetryPolicy(attempts=1, backoff_sec=0),
        timeout=httpx.Timeout(connect=5, read=120, write=10, pool=5),
        **kw,
    )


async def test_local_first_request_uses_longer_read_timeout_then_default():
    rec = Recorder()
    async with _llm(rec, first_request_timeout=300) as llm:
        await llm.complete("a")
        await llm.complete("b")
    first, second = rec.timeouts
    assert first["read"] == 300 and first["connect"] == 5 and first["write"] == 10
    assert second["read"] == 120


async def test_first_request_never_shortens_a_longer_default():
    rec = Recorder()
    async with _llm(rec, first_request_timeout=60) as llm:
        await llm.complete("a")
    assert rec.timeouts[0]["read"] == 120  # max(120, 60)


async def test_remote_provider_and_missing_value_keep_client_timeout():
    rec = Recorder()
    async with _llm(
        rec,
        provider="gemini",
        base="https://g.example/v1",
        allowed_hosts=["g.example"],
        first_request_timeout=300,
    ) as llm:
        await llm.complete("a")
    assert rec.timeouts[0]["read"] == 120
    rec2 = Recorder()
    async with _llm(rec2) as llm:
        await llm.complete("a")
    assert rec2.timeouts[0]["read"] == 120
