"""공인 IP 조회 어댑터 + 자료원 가용 상태 파일 (레인 I). 네트워크 없음 (MockTransport)."""

import httpx
import pytest

from rra.adapters.persistence.source_availability import FileSourceAvailability
from rra.adapters.sources import BlockedURL, FetchError, GuardedClient, PublicIpProbe
from rra.application.ports import PublicIpPort, SourceAvailabilityPort


def probe(body, *, status=200, allowed=("api.ipify.org",)):
    def handler(request):
        assert request.url.host == "api.ipify.org"
        assert "key" not in str(request.url)  # 비밀을 보내지 않는다
        return httpx.Response(status, content=body, headers={"content-type": "text/plain"})

    client = GuardedClient(
        list(allowed),
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        retries=0,
    )
    return PublicIpProbe(client, url="https://api.ipify.org")


async def test_probe_returns_normalized_ip_and_closes():
    p = probe(b"  59.0.251.250\n")
    assert isinstance(p, PublicIpPort)
    assert await p.current_ip() == "59.0.251.250"
    await p.aclose()


async def test_probe_rejects_non_ip_bodies():
    with pytest.raises(FetchError):
        await probe(b"<html>blocked</html>").current_ip()
    with pytest.raises(FetchError):
        await probe(b"x" * 200).current_ip()
    with pytest.raises(FetchError):
        await probe(b"", status=500).current_ip()


async def test_probe_obeys_allowlist():
    with pytest.raises(BlockedURL):
        await probe(b"1.2.3.4", allowed=("www.ntis.go.kr",)).current_ip()


def test_availability_file_roundtrip(tmp_path):
    path = tmp_path / "cache" / "source_availability.json"
    store = FileSourceAvailability(path, clock=lambda: 1000.0)
    assert isinstance(store, SourceAvailabilityPort)
    assert store.notices() == {} and store.notice("ntis") is None
    store.record(
        "ntis", "현재 IP 203.0.113.9 가 NTIS 등록 IP 에 없습니다.\x00 활용신청에 추가하세요"
    )
    assert store.notice("ntis") == (
        "현재 IP 203.0.113.9 가 NTIS 등록 IP 에 없습니다. 활용신청에 추가하세요"
    )
    assert "secret" not in path.read_text(encoding="utf-8")
    store.record("Bad Name!", "x")  # 이름 규칙 밖은 무시
    assert set(store.notices()) == {"ntis"}
    store.record("ntis", None)  # 해제
    assert store.notices() == {}
    store.record("ntis", None)  # 없는 것 해제는 파일을 만들지 않아도 된다
    assert store.notices() == {}


def test_availability_file_tolerates_garbage(tmp_path):
    path = tmp_path / "a.json"
    path.write_text("not json", encoding="utf-8")
    store = FileSourceAvailability(path)
    assert store.notices() == {}
    path.write_text('["list"]', encoding="utf-8")
    assert store.notices() == {}
    path.write_text('{"ntis": {"notice": ""}, "x": "no"}', encoding="utf-8")
    assert store.notices() == {}
