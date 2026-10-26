"""KIPRIS Plus 특허 자유검색 — 정규화(이름 제외·티어)·페이지·결과 없음·오류·키 비노출·probe.

키·네트워크 없음. 실제 태그 이름은 실응답 fixture(tests/fixtures/kipris) 로 확정한다.
"""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.adapters.sources.kipris import KiprisError, KiprisPatentSource, normalize_patent
from rra.adapters.sources.kipris.normalize import is_organization
from rra.domain.rules.dedup import dedup
from rra.domain.rules.overlap import tier_of, uncollected_sources

INSTITUTIONS = [
    {"code": "C0268", "name": "한국철도공사", "tag": "korail", "aliases": ["코레일"]},
    {"code": "C0269", "name": "한국철도기술연구원", "tag": "krri"},
]
KEY = "KIPRIS-SECRET-KEY"


def raw_patent(no="1020230012345", applicant="한국철도공사", **extra):
    return {
        "ApplicationNumber": no,
        "InventionName": "궤도 틀림 자동 검측 장치",
        "Abstract": "가속도 센서로 궤도 틀림을 상시 감지한다",
        "Applicant": applicant,
        "ApplicationDate": "2023.05.01",
        "OpeningDate": "20241101",
        "RegistrationStatus": "공개",
        "InternationalpatentclassificationNumber": "B61K 9/08|G01M 17/08",
        **extra,
    }


def test_normalize_patent_fields_without_person_names():
    doc = normalize_patent(raw_patent(), INSTITUTIONS)
    assert doc.doc_id == "kipris_kr:1020230012345" and doc.source == "kipris_kr"
    assert doc.doc_type == "patent" and doc.application_no == "1020230012345"
    assert doc.orgs == ["korail"] and doc.codes == ["B61K 9/08", "G01M 17/08"]
    assert doc.pub_date.isoformat() == "2024-11-01" and doc.authors == []
    assert doc.raw["applicants"] == ["한국철도공사"] and doc.raw["applicant_kind"] == "organization"
    assert doc.raw["status"] == "공개" and doc.url is None
    person = normalize_patent(raw_patent(applicant="홍길동|김철수"), INSTITUTIONS)
    assert person.raw["applicants"] == [] and person.raw["applicant_kind"] == "person"
    assert "홍길동" not in person.model_dump_json()
    mixed = normalize_patent(raw_patent(applicant="홍길동|주식회사 철도기술"), INSTITUTIONS)
    assert mixed.raw["applicants"] == ["주식회사 철도기술"]


@pytest.mark.parametrize(
    ("name", "org"),
    [
        ("한국철도공사", True),
        ("㈜한국철도기술", True),
        ("서울대학교 산학협력단", True),
        ("홍길동", False),
        ("Siemens Mobility GmbH", True),
        ("", False),
    ],
)
def test_is_organization(name, org):
    assert is_organization(name) is org


@pytest.mark.parametrize("no", ["", "abc", "12", "1 2 3"])
def test_bad_application_number_rejected(no):
    with pytest.raises(ValueError):
        normalize_patent(raw_patent(no=no), INSTITUTIONS)


def test_patents_land_in_overlap_tier_and_source_labels(own):
    korail = normalize_patent(raw_patent(), INSTITUTIONS)
    assert tier_of(korail, own) == "domestic_rail"  # 기관 태그만 있고 부서 없음
    other = normalize_patent(raw_patent(applicant="현대로템 주식회사"), INSTITUTIONS)
    assert tier_of(other, own) == "external"
    assert "kipris_kr" not in uncollected_sources({"kipris_kr": 1})
    dup = normalize_patent(raw_patent(), INSTITUTIONS)
    assert len(dedup([korail, dup])) == 1  # 같은 출원번호 → 하나


# ── 수집 ─────────────────────────────────────────────────
def page(n, total, start=0, code="00"):
    items = "".join(
        f"<PatentUtilityInfo><ApplicationNumber>10202300{start + i:05d}</ApplicationNumber>"
        f"<InventionName>특허 {start + i}</InventionName><Applicant>한국철도공사</Applicant>"
        "</PatentUtilityInfo>"
        for i in range(n)
    )
    return (
        f"<response><header><resultCode>{code}</resultCode><resultMsg>ok</resultMsg></header>"
        f"<body><items>{items}</items><TotalSearchCount>{total}</TotalSearchCount></body></response>"
    )


def source_for(responses, *, docs=2, max_requests=None):
    requests = []

    def handler(request):
        requests.append(request)
        item = responses.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, content=item.encode(), headers={"content-type": "text/xml"})

    async def no_sleep(_):
        return None

    client = GuardedClient(
        ["plus.kipris.or.kr"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=no_sleep,
        max_requests=max_requests,
        retries=0,
    )
    src = KiprisPatentSource(
        client,
        access_key=SecretStr(KEY),
        base_url="https://plus.kipris.or.kr",
        queries=["궤도"],
        institutions=INSTITUTIONS,
        docs_count=docs,
    )
    return src, requests


async def test_pages_with_docs_start_and_access_key():
    src, reqs = source_for([page(2, 3), page(1, 3, start=2)])
    raws = await src.search(None, 10)
    assert [r["InventionName"] for r in raws] == ["특허 0", "특허 1", "특허 2"]
    q = parse_qs(urlsplit(str(reqs[1].url)).query)
    assert q["docsStart"] == ["3"] and q["docsCount"] == ["2"] and q["word"] == ["궤도"]
    assert q["accessKey"] == [KEY] and q["patent"] == ["true"] and q["utility"] == ["true"]
    assert reqs[0].url.path == "/openapi/rest/patUtiModInfoSearchSevice/freeSearchInfo"
    docs = [src.normalize(r) for r in raws]
    assert {d.source for d in docs} == {"kipris_kr"}


async def test_no_result_code_is_empty_not_error_and_budget_returns_partial():
    src, _ = source_for([page(0, 0, code="20")])
    assert await src.search("없는 말", 10) == []
    src, _ = source_for([page(2, 10), page(2, 10, start=2)], max_requests=1)
    assert len(await src.search(None, 10)) == 2


async def test_error_codes_and_http_errors_never_leak_the_key():
    src, _ = source_for([page(0, 0, code="30")])
    with pytest.raises(KiprisError, match="code=30"):
        await src.search(None, 10)
    src, _ = source_for([httpx.Response(403)])
    with pytest.raises(FetchError) as info:
        await src.search(None, 10)
    assert KEY not in str(info.value) and "accessKey" not in str(info.value)


async def test_probe_reports_total_and_record_tag_candidates():
    src, _ = source_for([page(3, 40)])
    assert await src.probe() == {
        "total": 40,
        "record_tag_candidates": ["PatentUtilityInfo"],
        "record_tag_matches": True,
    }
    src, _ = source_for([page(3, 40)])
    src.record_tag = "item"
    assert (await src.probe())["record_tag_matches"] is False
