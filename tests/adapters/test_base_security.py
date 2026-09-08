from rra.adapters.sources._base import cache_key, host_allowed, resolves_private, strip_secrets


def test_strip_secrets_removes_key_params():
    u = "https://apis.data.go.kr/x?serviceKey=SECRET&q=rail&pageNo=1"
    assert "SECRET" not in strip_secrets(u)
    assert cache_key(u) == cache_key("https://apis.data.go.kr/x?q=rail&pageNo=1")


def test_host_allowlist():
    allowed = {"api.openalex.org"}
    assert host_allowed("https://api.openalex.org/works", allowed)
    assert not host_allowed("https://api.openalex.org.evil.com/works", allowed)


def test_private_ip_detection():
    assert resolves_private("localhost")
    assert resolves_private("127.0.0.1")
