"""나라장터 입찰공고(용역) 어댑터.

구성 예시 fixture(실응답 아님)·MockTransport. 키 없으면 MissingCredential."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.adapters.sources.procurement import G2bProcurementSource, normalize_g2b_item
from rra.adapters.sources.procurement.source import PROCURED_STATUS, parse_response
from rra.domain.rules.overlap import PROCURING_STATUS, tier_label, tier_of

FIX = Path(__file__).parents[2] / "fixtures" / "g2b"
INST = [
    {"name": "한국철도공사", "tag": "korail", "aliases": ["코레일"]},
    {"name": "국가철도공단", "tag": "kr"},
]
TODAY = date(2026, 10, 27)


def _sample():
    return json.loads((FIX / "services_sample.json").read_text(encoding="utf-8"))


def test_parse_response_items_and_total():
    items, total = parse_response(_sample())
    assert total == 2 and [i["bidNtceNo"] for i in items] == ["20261015001", "20250301002"]


def test_parse_response_gateway_error_is_fetch_error():
    with pytest.raises(FetchError):
        parse_response({"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": "20"}}})


def test_normalize_procurement_tier_status_and_no_contact_fields():
    item = _sample()["response"]["body"]["items"][0]
    doc = normalize_g2b_item(item, institutions=INST, today=TODAY)
    assert doc.doc_id == "g2b:20261015001-00" and doc.source == "g2b"
    assert doc.doc_type == "procurement" and doc.visibility == "public"
    assert doc.orgs == ["korail"] and doc.pub_date == date(2026, 10, 15)
    assert doc.raw["status"] == PROCURING_STATUS and doc.raw["close"] == "2026-11-05"
    assert "과업지시서_궤도기하.hwp" in doc.body and "한국철도공사 철도연구원" in doc.body
    # 담당자 이름·전화·이메일은 문서 어디에도 없다
    for secret in ("담당자이름", "042-000-0000", "someone@korail.com"):
        assert secret not in doc.body and secret not in json.dumps(doc.raw, ensure_ascii=False)
    assert tier_of(doc) == "procurement" and tier_label("procurement") == "발주 용역"


def test_old_notice_is_procured_not_procuring():
    item = _sample()["response"]["body"]["items"][1]
    doc = normalize_g2b_item(item, institutions=INST, today=TODAY, active_days=540)
    assert doc.raw["status"] == PROCURED_STATUS and doc.doc_id == "g2b:20250301002-01"
    assert doc.orgs == []


async def test_source_filters_rail_orgs_and_sends_key_only_in_query():
    seen: list[httpx.URL] = []

    def api(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(
            200, json=_sample(), headers={"content-type": "application/json;charset=UTF-8"}
        )

    async def no_sleep(_s):
        return None

    client = GuardedClient(
        ["apis.data.go.kr"],
        transport=httpx.MockTransport(api),
        resolver=lambda h: False,
        sleep=no_sleep,
    )
    src = G2bProcurementSource(
        client,
        service_key=SecretStr("k-secret"),
        queries=["철도"],
        institutions=INST,
        org_filter=["한국철도공사", "국가철도공단"],
        today=lambda: TODAY,
    )
    raws = await src.search(None, 10)
    assert [r["bidNtceNo"] for r in raws] == ["20261015001"]  # 서울교통공사 공고는 걸러짐
    params = dict(seen[0].params)
    assert params["serviceKey"] == "k-secret" and params["bidNtceNm"] == "철도"
    assert params["inqryDiv"] == "1" and params["type"] == "json"
    doc = src.normalize(raws[0])
    assert doc.doc_type == "procurement" and doc.raw["query"] == "철도"
    await src.aclose()


def test_build_skips_without_key(tmp_path):
    from rra.composition import build_available_sources
    from rra.settings import Settings

    settings = Settings(_env_file=None, config_dir=Path(__file__).parents[2].parent / "config")
    sources, skipped = build_available_sources(["g2b"], settings)
    assert sources == [] and skipped[0][0] == "g2b" and "RRA_DATA_GO_KR_KEY" in skipped[0][1]
