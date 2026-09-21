"""NTIS 과제검색 — 페이지·오류·키 비노출, 기관 태그·티어·dedup. 키·네트워크 없음.

과제 필드 매핑(normalize_project)의 실제 태그 이름은 실응답 fixture 로 확인한다.
여기서는 후보 이름을 가진 최소 레코드로 흐름만 검증한다.
"""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.sources._base import FetchError, GuardedClient
from rra.adapters.sources._orgs import org_tags
from rra.adapters.sources._xml import XmlResponseError, find_records, flatten, parse
from rra.adapters.sources.ntis import NtisProjectSource, normalize_project
from rra.adapters.sources.ntis.client import NtisError
from rra.domain.models import Document
from rra.domain.rules.dedup import dedup
from rra.domain.rules.overlap import tier_of

INSTITUTIONS = [
    {"code": "C0268", "name": "한국철도공사", "tag": "korail", "aliases": ["코레일"]},
    {"code": "C0269", "name": "한국철도기술연구원", "tag": "krri"},
    {"code": "C0270", "name": "국가철도공단", "tag": "kr", "aliases": ["한국철도시설공단"]},
]
KEY = "NTIS-SECRET-KEY"


# ── 기관 태그 ────────────────────────────────────────────
@pytest.mark.parametrize(
    ("names", "tags"),
    [
        (["한국철도공사"], ["korail"]),
        (["한국철도공사 철도연구원"], ["korail"]),
        (["코레일"], ["korail"]),
        (["한국철도기술연구원"], ["krri"]),  # 한국철도공사와 혼동하지 않는다
        (["한국철도시설공단"], ["kr"]),  # 2020 개칭 전 이름
        (["국가 철도 공단"], ["kr"]),
        (["서울교통공사", "한국철도공사"], ["korail"]),
        (["서울대학교"], []),
        (["", "  "], []),
    ],
)
def test_org_tags(names, tags):
    assert org_tags(names, INSTITUTIONS) == tags


# ── 과제 정규화 → 티어·dedup ──────────────────────────────
def raw_project(no="1415171234", agency="한국철도공사", dept=""):
    return {
        "ProjectNumber": no,
        "ProjectTitle/Korean": "궤도 틀림 상시 감시 기술 개발",
        "Goal/Teaser": "궤도 상태 자동 감지",
        "Abstract/Teaser": "가속도 센서 기반",
        "ResearchAgency/Name": agency,
        "ResearchAgencyDepartment": dept,
        "ProjectPeriod/Start": "2021-04-01",
        "ProjectPeriod/End": "2023-12-31",
        "Manager/Name": "홍길동",
    }


def test_normalize_project_fields():
    doc = normalize_project(raw_project(), INSTITUTIONS)
    assert doc.doc_id == "ntis:1415171234" and doc.doc_type == "rnd_project"
    assert doc.orgs == ["korail"]
    assert doc.project_period[0].isoformat() == "2021-04-01"
    assert "[연구목표] 궤도 상태 자동 감지" in doc.abstract
    assert doc.url is None  # 검증 안 된 링크는 만들지 않는다


@pytest.mark.parametrize(
    ("agency", "dept", "tier"),
    [
        ("한국철도공사", "철도연구원", "own"),
        ("한국철도공사", "", "domestic_rail"),
        ("한국철도시설공단", "", "domestic_rail"),
        ("한국철도기술연구원", "", "external"),
        ("서울대학교", "", "external"),
    ],
)
def test_ntis_projects_land_in_the_right_overlap_tier(agency, dept, tier):
    assert tier_of(normalize_project(raw_project(agency=agency, dept=dept), INSTITUTIONS)) == tier


@pytest.mark.parametrize("no", ["", "../x", "1 2", "x" * 50])
def test_bad_project_number_rejected(no):
    with pytest.raises(ValueError):
        normalize_project(raw_project(no=no), INSTITUTIONS)


def test_project_is_not_merged_with_same_title_report():
    project = normalize_project(raw_project(), INSTITUTIONS)
    report = Document(
        doc_id="alio:77",
        source="alio",
        doc_type="internal_report",
        title=project.title,
        body="긴 본문" * 100,
    )
    assert {d.doc_id for d in dedup([project, report])} == {"ntis:1415171234", "alio:77"}


# ── XML 공통 ─────────────────────────────────────────────
def test_flatten_and_auto_detect_records():
    root = parse(
        b"<RESULT><TOTALHITS>2</TOTALHITS><RESULTSET>"
        b"<HIT><ProjectNumber>1</ProjectNumber><ProjectTitle><Korean>A</Korean></ProjectTitle></HIT>"
        b"<HIT><ProjectNumber>2</ProjectNumber><ProjectTitle><Korean>B</Korean></ProjectTitle></HIT>"
        b"</RESULTSET></RESULT>"
    )
    recs = find_records(root)
    assert [flatten(r) for r in recs] == [
        {"ProjectNumber": "1", "ProjectTitle/Korean": "A"},
        {"ProjectNumber": "2", "ProjectTitle/Korean": "B"},
    ]


def test_xxe_rejected():
    with pytest.raises(XmlResponseError):
        parse(
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
        )


# ── 수집 ─────────────────────────────────────────────────
def hits(n, total, start=0):
    body = "".join(
        f"<HIT><ProjectNumber>{1415170000 + start + i}</ProjectNumber>"
        f"<ProjectTitle><Korean>과제 {start + i}</Korean></ProjectTitle></HIT>"
        for i in range(n)
    )
    return f"<RESULT><TOTALHITS>{total}</TOTALHITS><RESULTSET>{body}</RESULTSET></RESULT>"


def source_for(responses, *, display=2, max_requests=None):
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
        ["www.ntis.go.kr"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=no_sleep,
        max_requests=max_requests,
        retries=0,
    )
    src = NtisProjectSource(
        client,
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        project_path="/rndopen/openApi/public_project",
        queries=["궤도"],
        institutions=INSTITUTIONS,
        display_count=display,
        record_tag="HIT",
    )
    return src, requests


async def test_pages_with_start_position():
    src, reqs = source_for([hits(2, 3), hits(1, 3, start=2)])
    raws = await src.search(None, 10)
    assert [r["ProjectNumber"] for r in raws] == ["1415170000", "1415170001", "1415170002"]
    q = parse_qs(urlsplit(str(reqs[1].url)).query)
    assert q["startPosition"] == ["3"] and q["collection"] == ["project"] and q["SRWR"] == ["궤도"]
    assert q["apprvKey"] == [KEY]


async def test_budget_returns_partial():
    src, _ = source_for([hits(2, 10), hits(2, 10, start=2)], max_requests=1)
    assert len(await src.search(None, 10)) == 2


async def test_error_code_and_http_errors_never_leak_the_key():
    src, _ = source_for(["<RESULT><ERROR_CODE>E901</ERROR_CODE></RESULT>"])
    with pytest.raises(NtisError, match="E901"):
        await src.search(None, 10)
    src, _ = source_for([httpx.Response(403)])
    with pytest.raises(FetchError) as info:
        await src.search(None, 10)
    assert KEY not in str(info.value) and "apprvKey" not in str(info.value)


def test_single_record_page_is_why_record_tag_is_required():
    root = parse(hits(1, 1).encode())
    assert [e.tag for e in find_records(root)] == ["RESULTSET"]  # 자동 탐지는 여기서 틀린다
    assert [flatten(r) for r in find_records(root, "HIT")][0]["ProjectNumber"] == "1415170000"


async def test_empty_record_tag_blocks_search_but_not_probe():
    src, _ = source_for([hits(3, 40)])
    src.record_tag = None
    with pytest.raises(NtisError, match="record_tag"):
        await src.search(None, 10)
    assert await src.probe() == {"total": 40, "record_tag_candidates": ["HIT"]}
