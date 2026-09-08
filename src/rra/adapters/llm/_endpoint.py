"""H. LLM 엔드포인트 검증 — 순수 함수.

- provider=mlx 는 인증이 없으므로 루프백 외 주소를 절대 허용하지 않는다.
- 그 외 provider 는 원격이면 https 만 허용한다.
- userinfo(`http://127.0.0.1@evil.com`)로 호스트를 위장하는 형태를 거부한다.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from rra.adapters.llm.errors import InsecureLLMEndpoint

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOCAL_PROVIDERS = frozenset({"mlx", "local", "llama.cpp"})
USER_AGENT = "rra/0.1"
_PLACEHOLDER_KEYS = {"", "none", "no-key", "null"}


def is_local_host(host: str) -> bool:
    return host.lower() in LOCAL_HOSTS


def guard_base_url(provider: str, base_url: str) -> str:
    """검증 후 정규화된 base_url 을 돌려준다. 위반이면 InsecureLLMEndpoint."""
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ("http", "https"):
        raise InsecureLLMEndpoint(f"지원하지 않는 스킴입니다: {parts.scheme or '(없음)'}")
    if parts.username or parts.password:
        raise InsecureLLMEndpoint("base_url 에 userinfo 를 넣을 수 없습니다.")
    host = parts.hostname
    if not host:
        raise InsecureLLMEndpoint("base_url 에 호스트가 없습니다.")

    local = is_local_host(host)
    if provider.lower() in LOCAL_PROVIDERS:
        if not local:
            raise InsecureLLMEndpoint(
                f"provider={provider} 는 127.0.0.1 로만 접속합니다. "
                f"현재 호스트 {host} — 로컬 LLM 서버는 인증이 없어 외부 노출이 금지됩니다 (보안 H)."
            )
    elif not local and parts.scheme != "https":
        raise InsecureLLMEndpoint(f"원격 provider={provider} 는 https 만 허용합니다.")

    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def auth_headers(api_key: str | None) -> dict[str, str]:
    """로컬 LLM 은 키가 없다. 자리표시자 키는 Authorization 을 만들지 않는다 (보안 D)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    key = (api_key or "").strip()
    if key and key.lower() not in _PLACEHOLDER_KEYS:
        headers["Authorization"] = f"Bearer {key}"
    return headers
