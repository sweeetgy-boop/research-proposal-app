"""[4] 실시간 검색 어댑터 (adapters/sources/live.py) — MockTransport + 실응답 fixture. 키·네트워크
없음.

세션마다 요청 예산이 처음부터 세어지는지, 질의가 앞에서부터 가고 건수가 차면 멈추는지, NTIS IP
거부가
SourceIpBlocked 로 올라오는지, 사람 이름을 읽지 않는지 본다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources.live import LiveNtis, LiveOpenAlex, LiveScienceOn
from rra.adapters.sources.ntis import NtisProjectSource, NtisReportSource
from rra.adapters.sources.openalex import OpenAlexSource
from rra.adapters.sources.scienceon import ScienceOnSource, TokenManager
from rra.domain.rules.source_ip import SourceIpBlocked

FIX = Path(__file__).parents[1] / "fixtures"
NTIS_KEY = "NTIS-SECRET-KEY"
JSON_CT = {"content-type": "application/json;charset=UTF-8"}
XML_CT = {"content-type": "text/xml"}
IP_ERROR = "<?xml version='1.0' encoding='UTF-8' ?>\n<error>접근 허용 IP가 아닙니다.</error>"


async def _no_sleep(_):
    return None


def _client(handler, hosts):
    return GuardedClient(
        hosts,
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=_no_sleep,
        retries=0,
    )


def _wrapped(path: Path) -> bytes:
    return json.dumps(path.read_text(encoding="utf-8")).encode("utf-8")


# ── OpenAlex ─────────────────────────────────────────────
async def test_openalex_live_one_request_with_abstract_filter_and_budget_reset():
    page = json.loads((FIX / "openalex" / "works_page1.json").read_text(encoding="utf-8"))
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=page)

    live = LiveOpenAlex(OpenAlexSource(_client(handler, ["api.openalex.org"])), max_requests=3)
    docs = await live.fetch(["train delay prediction", "train delay"], 30)
    q = parse_qs(urlsplit(str(seen[0].url)).query)
    assert q["search"] == ["train delay prediction"] and q["filter"] == ["has_abstract:true"]
    assert q["per-page"] == ["30"]
    # 5건 < 30 이라 둘째 질의도 보낸다 — 같은 work 는 한 번만
    assert len(seen) == 2 and len(docs) == len({d.doc_id for d in docs}) == 5
    for _ in range(3):  # 세션마다 예산이 처음부터 — 여러 세션 뒤에도 막히지 않는다
        assert len(await live.fetch(["x"], 5)) == 5


# ── NTIS ─────────────────────────────────────────────────
def _ntis(handler, *, reports=True):
    def proj():
        return NtisProjectSource(
            _client(handler, ["www.ntis.go.kr"]),
            apprv_key=SecretStr(NTIS_KEY),
            base_url="https://www.ntis.go.kr",
            project_path="/rndopen/openApi/public_project",
            queries=["철도"],
            institutions=[],
            record_tag="HIT",
        )

    def rep():
        return NtisReportSource(
            _client(handler, ["www.ntis.go.kr"]),
            apprv_key=SecretStr(NTIS_KEY),
            base_url="https://www.ntis.go.kr",
            report_path="/rndopen/openApi/rresearchpdf/",
            queries=["철도"],
            institutions=[],
            record_tag="HIT",
        )

    return LiveNtis(proj(), rep() if reports else None, max_requests=4)


async def test_ntis_live_projects_and_reports_split():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        fix = (
            "ntis_report_20261027_track.xml"
            if "rresearchpdf" in request.url.path
            else ("ntis_project_20261027_track.xml")
        )
        return httpx.Response(200, content=_wrapped(FIX / "ntis" / fix), headers=JSON_CT)

    docs = await _ntis(handler).fetch(["철도 궤도", "철도"], 30)
    kinds = [d.doc_type for d in docs]
    assert kinds.count("rnd_project") == 10 and kinds.count("report") == 10  # fixture 각 10건
    counts = {
        r.url.path: parse_qs(urlsplit(str(r.url)).query).get("displayCnt")
        or parse_qs(urlsplit(str(r.url)).query).get("displayCount")
        for r in seen
    }
    assert set(counts) == {"/rndopen/openApi/public_project", "/rndopen/openApi/rresearchpdf/"}
    assert all(v == ["15"] for v in counts.values())  # 30 을 과제·보고서가 반씩
    assert all(not d.authors and "NAME-REMOVED" not in str(d.model_dump()) for d in docs)


async def test_ntis_live_ip_block_raises_source_ip_blocked():
    def handler(request):
        return httpx.Response(200, content=IP_ERROR.encode(), headers=JSON_CT)

    with pytest.raises(SourceIpBlocked) as info:
        await _ntis(handler).fetch(["철도"], 30)
    assert NTIS_KEY not in str(info.value)


async def test_ntis_live_one_service_failing_keeps_the_other():
    def handler(request):
        if "rresearchpdf" in request.url.path:
            return httpx.Response(500)
        fix = FIX / "ntis" / "ntis_project_20261027_track.xml"
        return httpx.Response(200, content=_wrapped(fix), headers=JSON_CT)

    docs = await _ntis(handler).fetch(["철도"], 30)
    assert docs and all(d.doc_type == "rnd_project" for d in docs)


# ── ScienceON ────────────────────────────────────────────
async def test_scienceon_live_targets_share_limit_and_token_reused():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/tokenrequest.do":
            return httpx.Response(200, json={"access_token": "ACCESS-1", "refresh_token": "R-1"})
        target = parse_qs(urlsplit(str(request.url)).query)["target"][0]
        fix = FIX / "scienceon" / f"scienceon_{target}_20261027_1.xml"
        return httpx.Response(200, content=fix.read_bytes(), headers=XML_CT)

    client = _client(handler, ["apigateway.kisti.re.kr"])
    tokens = TokenManager(
        client,
        "https://apigateway.kisti.re.kr",
        client_id=SecretStr("CLIENT-XYZ"),
        auth_key=SecretStr("0123456789abcdef0123456789abcdef"),
        mac=SecretStr("aa:bb:cc:dd:ee:ff"),
        now=lambda: datetime(2026, 10, 28, 9, 0, 0),
    )
    src = ScienceOnSource(
        client,
        tokens,
        base_url="https://apigateway.kisti.re.kr",
        targets=["ARTI", "REPORT", "PATENT"],
        queries=["철도"],
    )
    live = LiveScienceOn(src, max_requests=8)
    docs = await live.fetch(["열차 지연 예측", "열차 지연"], 30)
    pages = [r for r in seen if r.url.path != "/tokenrequest.do"]
    assert len(pages) == 3  # target 마다 한 번 (10건씩 → 30건이 차서 둘째 질의는 없음)
    q = parse_qs(urlsplit(str(pages[0].url)).query)
    assert q["rowCount"] == ["10"] and json.loads(q["searchQuery"][0]) == {"BI": "열차 지연 예측"}
    assert len(docs) == 30 and {d.doc_type for d in docs} >= {"patent"}
    assert all(not d.authors for d in docs)
    await live.fetch(["궤도"], 30)  # 둘째 세션 — 토큰은 재사용, 예산은 처음부터
    assert sum(r.url.path == "/tokenrequest.do" for r in seen) == 1
