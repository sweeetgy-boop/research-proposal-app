"""GuardedClient — MockTransport·resolver·sleep 주입. 네트워크·DNS 없음."""

import httpx
import pytest

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient

ALLOWED = ["api.openalex.org", "mirror.openalex.org"]
OK_JSON = {"results": [], "meta": {}}


class Router:
    """URL 별 응답 목록. 요청 URL 을 기록한다."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url.copy_with(query=None))
        self.requests.append(str(request.url))
        queue = self.routes.get(url)
        if not queue:
            raise AssertionError(f"예상하지 않은 요청: {url}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def redirect(to, status=302):
    return httpx.Response(status, headers={"location": to})


def json_response(data=OK_JSON, **kw):
    return httpx.Response(200, json=data, **kw)


def make(router, *, resolver=lambda host: False, sleeps=None, **kw):
    sleeps = sleeps if sleeps is not None else []

    async def fake_sleep(sec):
        sleeps.append(sec)

    return GuardedClient(
        ALLOWED,
        transport=httpx.MockTransport(router),
        resolver=resolver,
        sleep=fake_sleep,
        **kw,
    )


async def test_plain_get_json_with_params():
    router = Router({"https://api.openalex.org/works": [json_response({"ok": 1})]})
    async with make(router) as client:
        assert await client.get_json("https://api.openalex.org/works", {"search": "rail"}) == {
            "ok": 1
        }
    assert router.requests == ["https://api.openalex.org/works?search=rail"]


async def test_redirect_to_allowed_host_is_followed():
    router = Router(
        {
            "https://api.openalex.org/works": [redirect("https://mirror.openalex.org/w")],
            "https://mirror.openalex.org/w": [json_response()],
        }
    )
    async with make(router) as client:
        assert await client.get_json("https://api.openalex.org/works") == OK_JSON
    assert len(router.requests) == 2


async def test_relative_redirect_is_resolved_and_checked():
    router = Router(
        {
            "https://api.openalex.org/works": [redirect("/works2")],
            "https://api.openalex.org/works2": [json_response()],
        }
    )
    async with make(router) as client:
        assert await client.get_json("https://api.openalex.org/works") == OK_JSON


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.com/steal",  # 허용목록 밖
        "https://127.0.0.1/admin",  # 루프백 리터럴
        "https://[::1]/admin",
        "http://mirror.openalex.org/w",  # https 다운그레이드
        "https://api.openalex.org:8080/w",  # 포트 변경
    ],
)
async def test_redirect_to_forbidden_target_is_blocked_before_request(target):
    router = Router({"https://api.openalex.org/works": [redirect(target)]})
    async with make(router) as client:
        with pytest.raises(BlockedURL):
            await client.get_json("https://api.openalex.org/works")
    assert len(router.requests) == 1  # 두 번째 요청은 나가지 않는다


async def test_redirect_to_allowed_host_that_resolves_private_is_blocked():
    router = Router({"https://api.openalex.org/works": [redirect("https://mirror.openalex.org/w")]})

    def resolver(host):
        return host == "mirror.openalex.org"  # DNS 가 사설 IP 를 돌려준 상황

    async with make(router, resolver=resolver) as client:
        with pytest.raises(BlockedURL):
            await client.get_json("https://api.openalex.org/works")
    assert len(router.requests) == 1


async def test_initial_url_is_checked_too():
    router = Router({})
    async with make(router) as client:
        with pytest.raises(BlockedURL):
            await client.get_json("https://evil.com/works")
    assert router.requests == []


async def test_too_many_redirects():
    router = Router(
        {
            "https://api.openalex.org/a": [redirect("https://api.openalex.org/b")],
            "https://api.openalex.org/b": [redirect("https://api.openalex.org/a")],
        }
    )
    async with make(router, max_redirects=3) as client:
        with pytest.raises(BlockedURL):
            await client.get_json("https://api.openalex.org/a")
    assert len(router.requests) == 4


async def test_response_over_limit_is_rejected():
    big = httpx.Response(
        200, content=b"[" + b"1," * 600 + b"1]", headers={"content-type": "application/json"}
    )
    router = Router({"https://api.openalex.org/works": [big]})
    async with make(router, max_response_bytes=1000) as client:
        with pytest.raises(FetchError):
            await client.get_json("https://api.openalex.org/works")


async def test_non_json_content_type_is_rejected():
    html = httpx.Response(200, text="<html>", headers={"content-type": "text/html"})
    router = Router({"https://api.openalex.org/works": [html]})
    async with make(router) as client:
        with pytest.raises(FetchError):
            await client.get_json("https://api.openalex.org/works")


async def test_retries_429_with_retry_after_then_succeeds():
    router = Router(
        {
            "https://api.openalex.org/works": [
                httpx.Response(429, headers={"retry-after": "2"}),
                httpx.Response(503),
                json_response(),
            ]
        }
    )
    sleeps = []
    async with make(router, sleeps=sleeps, backoff_sec=0.5) as client:
        assert await client.get_json("https://api.openalex.org/works") == OK_JSON
    assert sleeps == [2.0, 1.0]  # Retry-After, 그다음 지수 백오프(0.5*2)


async def test_gives_up_after_retries_without_leaking_secret():
    router = Router({"https://api.openalex.org/works": [httpx.Response(503)]})
    async with make(router, retries=2) as client:
        with pytest.raises(FetchError) as exc:
            await client.get_json("https://api.openalex.org/works", {"api_key": "SECRET"})
    assert len(router.requests) == 3
    assert "SECRET" not in str(exc.value)


async def test_transport_error_is_retried_then_wrapped():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    sleeps = []

    async def fake_sleep(sec):
        sleeps.append(sec)

    client = GuardedClient(
        ALLOWED,
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=fake_sleep,
        retries=1,
    )
    with pytest.raises(FetchError):
        await client.get_json("https://api.openalex.org/works")
    await client.aclose()
    assert len(calls) == 2


async def test_rate_limit_spaces_requests():
    router = Router({"https://api.openalex.org/works": [json_response()]})
    sleeps = []
    async with make(router, sleeps=sleeps, rate_limit=10, clock=lambda: 100.0) as client:
        await client.get_json("https://api.openalex.org/works")
        await client.get_json("https://api.openalex.org/works")
    assert sleeps == [pytest.approx(0.1)]


def test_repr_has_no_secrets():
    assert "GuardedClient" in repr(GuardedClient(ALLOWED))


# ── get_bytes (카탈로그 파일 다운로드) ────────────────────
CSV_TYPES = {"text/csv", "application/octet-stream"}


def file_response(body=b"a,b\n1,2\n", ctype="text/csv; charset=euc-kr", **kw):
    return httpx.Response(200, content=body, headers={"content-type": ctype}, **kw)


async def test_get_bytes_returns_body():
    router = Router({"https://api.openalex.org/f.csv": [file_response()]})
    async with make(router) as client:
        assert (
            await client.get_bytes("https://api.openalex.org/f.csv", accept_types=CSV_TYPES)
            == b"a,b\n1,2\n"
        )


async def test_get_bytes_rejects_unexpected_content_type():
    router = Router({"https://api.openalex.org/f.csv": [file_response(ctype="text/html")]})
    async with make(router) as client:
        with pytest.raises(FetchError, match="content-type"):
            await client.get_bytes("https://api.openalex.org/f.csv", accept_types=CSV_TYPES)


async def test_get_bytes_rechecks_every_redirect_hop():
    router = Router({"https://api.openalex.org/f.csv": [redirect("https://evil.example/f.csv")]})
    async with make(router) as client:
        with pytest.raises(BlockedURL):
            await client.get_bytes("https://api.openalex.org/f.csv", accept_types=CSV_TYPES)


async def test_get_bytes_size_cap():
    router = Router({"https://api.openalex.org/f.csv": [file_response(body=b"x" * 2048)]})
    async with make(router, max_response_bytes=1024) as client:
        with pytest.raises(FetchError, match="상한"):
            await client.get_bytes("https://api.openalex.org/f.csv", accept_types=CSV_TYPES)
