"""H. 엔드포인트 검증 + 요청 헤더 조립 — 순수 함수."""

import pytest

from rra.adapters.llm._endpoint import auth_headers, chat_url, guard_base_url
from rra.adapters.llm.errors import InsecureLLMEndpoint

ALLOWED = [
    ("mlx", "http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1"),
    ("mlx", "http://localhost:8080/v1/", "http://localhost:8080/v1"),
    ("mlx", "http://[::1]:8080/v1", "http://::1:8080/v1"),
    ("openai", "https://api.openai.com/v1", "https://api.openai.com/v1"),
    ("openai", "http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1"),
]

REJECTED = [
    ("mlx", "http://gpu.example.com/v1"),  # 로컬 provider 의 원격 주소
    ("mlx", "http://192.168.0.5:8080/v1"),
    ("mlx", "http://127.0.0.1@evil.com/v1"),  # userinfo 로 호스트 위장
    ("mlx", "https://evil.com/v1"),
    ("openai", "http://api.example.com/v1"),  # 원격인데 평문
    ("openai", "file:///etc/passwd"),
    ("openai", "ftp://host/v1"),
    ("openai", "not-a-url"),
    ("mlx", ""),
]


@pytest.mark.parametrize(("provider", "url", "expected"), ALLOWED)
def test_allowed_endpoints_are_normalized(provider, url, expected):
    assert guard_base_url(provider, url) == expected


@pytest.mark.parametrize(("provider", "url"), REJECTED)
def test_rejected_endpoints_refuse_startup(provider, url):
    with pytest.raises(InsecureLLMEndpoint):
        guard_base_url(provider, url)


def test_chat_url_normalizes_slashes():
    assert chat_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1/chat/completions"
    assert chat_url("http://127.0.0.1:8080/v1/") == "http://127.0.0.1:8080/v1/chat/completions"


@pytest.mark.parametrize("key", [None, "", "  ", "none", "NONE", "no-key"])
def test_placeholder_keys_send_no_authorization(key):
    assert "Authorization" not in auth_headers(key)


def test_real_key_becomes_bearer_header():
    headers = auth_headers("sk-abc123")  # pragma: allowlist secret
    assert headers["Authorization"] == "Bearer sk-abc123"
    assert headers["Content-Type"] == "application/json"
