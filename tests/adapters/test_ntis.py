"""NTIS — 과제검색·연구보고서·성과·연관콘텐츠. 키·네트워크 없음 (MockTransport + 합성 fixture).

필드 매핑은 공개 매뉴얼 응답명세 기준(tests/fixtures/ntis/README.md). 실응답은 IP 등록 뒤 녹화해
교체한다.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.persistence.file_cache import FileCache
from rra.adapters.sources._base import FetchError, GuardedClient
from rra.adapters.sources._orgs import org_tags
from rra.adapters.sources._xml import XmlResponseError, find_records, flatten, parse
from rra.adapters.sources.ntis import (
    NtisError,
    NtisInsightSource,
    NtisProjectSource,
    NtisReportSource,
    normalize_project,
    normalize_report,
)
from rra.adapters.sources.ntis.client import error_message
from rra.adapters.sources.ntis.insights import normalize_outcome, normalize_related
from rra.domain.models import Document
from rra.domain.rules.dedup import dedup
from rra.domain.rules.overlap import tier_of

FIX = Path(__file__).parents[1] / "fixtures" / "ntis"
INSTITUTIONS = [
    {"code": "C0268", "name": "한국철도공사", "tag": "korail", "aliases": ["코레일"]},
    {"code": "C0269", "name": "한국철도기술연구원", "tag": "krri"},
    {"code": "C0270", "name": "국가철도공단", "tag": "kr", "aliases": ["한국철도시설공단"]},
]
KEY = "NTIS-SECRET-KEY"
IP_ERROR = (
    b"<?xml version='1.0' encoding='UTF-8' ?>\n<error>"
    + "접근 허용 IP가 아닙니다.".encode()
    + b"</error>"
)


# ── 기관 태그 ────────────────────────────────────────────
@pytest.mark.parametrize(
    ("names", "tags"),
    [
        (["한국철도공사"], ["korail"]),
        (["코레일"], ["korail"]),
        (["한국철도기술연구원"], ["krri"]),
        (["한국철도시설공단"], ["kr"]),
        (["서울대학교"], []),
    ],
)
def test_org_tags(names, tags):
    assert org_tags(names, INSTITUTIONS) == tags


# ── 과제 정규화 (매뉴얼 태그) ─────────────────────────────
def raw_project(no="1415171234", agency="한국철도공사"):
    return {
        "ProjectNumber": no,
        "ProjectTitle/Korean": '<span class="search_word">궤도</span> 틀림 상시 감시 기술 개발',
        "Goal/Full": "궤도 상태 자동 감지",
        "Abstract/Teaser": "가속도 센서 기반",
        "ResearchAgency/Name": agency,
        "Manager/Name": "홍길동",
        "Researchers/Name": "김철수;이영희",
        "ProjectPeriod/Start": "20220101",
        "ProjectPeriod/TotalStart": "2021-04-01 00:00:00.0",
        "ProjectPeriod/TotalEnd": "2023-12-31 00:00:00.0",
        "ProjectYear": "2022",
        "Keyword/Korean": "궤도틀림, 가속도",
        "TotalFunds": "650000000",
    }


def test_normalize_project_fields():
    doc = normalize_project(raw_project(), INSTITUTIONS)
    assert doc.doc_id == "ntis:1415171234" and doc.doc_type == "rnd_project"
    assert doc.title == "궤도 틀림 상시 감시 기술 개발"  # 강조 태그 제거
    assert doc.orgs == ["korail"] and doc.department is None
    assert doc.project_period == (doc.pub_date, doc.project_period[1])
    assert doc.project_period[0].isoformat() == "2021-04-01"  # 총연구기간 우선
    assert "[연구목표] 궤도 상태 자동 감지" in doc.abstract and "[연구내용] 가속도" in doc.abstract
    assert doc.authors == [] and "홍길동" not in str(doc.model_dump())  # 사람 이름 미저장
    assert doc.codes == ["궤도틀림", "가속도"]
    assert doc.raw["kind"] == "national_rnd" and doc.raw["budget"] == "650000000"
    assert doc.url is None  # 검증 안 된 링크는 만들지 않는다
    assert doc.visibility == "public"


def test_year_only_project_gets_january_first():
    raw = raw_project()
    for k in ("ProjectPeriod/Start", "ProjectPeriod/TotalStart", "ProjectPeriod/TotalEnd"):
        raw.pop(k)
    doc = normalize_project(raw, INSTITUTIONS)
    assert doc.pub_date.isoformat() == "2022-01-01" and doc.project_period is None


@pytest.mark.parametrize(
    ("agency", "tier"),
    [
        ("한국철도공사", "national_rnd"),  # 부서 필드가 없어 own 이 될 수 없다 → 국가R&D 과제
        ("한국철도시설공단", "national_rnd"),
        ("한국철도기술연구원", "national_rnd"),
        ("서울대학교", "national_rnd"),
    ],
)
def test_ntis_projects_land_in_national_rnd_tier(agency, tier, own):
    assert tier_of(normalize_project(raw_project(agency=agency), INSTITUTIONS), own) == tier


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


def test_fixture_highlight_spans_keep_tail_text():
    """flatten 이 `<span class="search_word">` 아래로 내려가면 강조어 뒤 텍스트가 사라진다 — 잎으로
    본다."""
    root = parse((FIX / "ntis_project_SYNTHETIC_manual.xml").read_bytes())
    flat = flatten(find_records(root, "HIT")[0])
    assert flat["ProjectTitle/Korean"] == "철도 궤도 틀림 상시 감시 기술 개발"
    assert "ProjectTitle/Korean/span" not in flat
    assert flat["Manager/Name"] == "NAME-REMOVED"


# ── 보고서 정규화 ─────────────────────────────────────────
def test_normalize_report_from_manual_fixture():
    root = parse((FIX / "ntis_report_SYNTHETIC_manual.xml").read_bytes())
    docs = [normalize_report(flatten(r), INSTITUTIONS) for r in find_records(root, "HIT")]
    first, second = docs
    assert first.doc_id == "ntis:REP-2023-0115000001" and first.doc_type == "report"
    assert (
        first.title == "철도 궤도 틀림 상시 감시 기술 개발 최종보고서"
    )  # 이스케이프된 강조 태그 제거
    assert first.pub_date.isoformat() == "2023-12-01" and first.url.startswith(
        "https://nrms.kisti.re.kr/"
    )
    assert first.orgs == ["korail"] and first.raw["project_no"] == "1415171234"
    assert first.toc == ["1장 서론", "2장 센서 구성", "3장 알고리즘", "4장 검증"]
    assert first.codes == ["궤도틀림", "가속도", "상시감시"]
    assert second.url is None  # http 링크는 버린다
    assert second.pub_date.isoformat() == "2021-01-01" and second.orgs == ["krri"]
    assert all(not d.authors for d in docs) and "NAME-REMOVED" not in str(
        [d.model_dump() for d in docs]
    )


def test_ntis_report_merges_with_scienceon_report_of_same_project():
    root = parse((FIX / "ntis_report_SYNTHETIC_manual.xml").read_bytes())
    ntis = normalize_report(flatten(find_records(root, "HIT")[0]), INSTITUTIONS)
    scienceon = Document(
        doc_id="scienceon:CN123",
        source="scienceon",
        doc_type="internal_report",
        title="철도 궤도 틀림 상시 감시 기술 개발 최종보고서",
        abstract="짧은 초록",
        pub_date=ntis.pub_date,
        raw={"project_no": "1415171234"},
        text_basis="abstract",
    )
    kept = dedup([scienceon, ntis])
    assert [d.doc_id for d in kept] == ["ntis:REP-2023-0115000001"]  # 초록이 긴 쪽


# ── 오류 본문 판별 ────────────────────────────────────────
def test_error_message_shapes():
    assert error_message(IP_ERROR) == "접근 허용 IP가 아닙니다."
    assert error_message(b"\xef\xbb\xbf<error>?? ?? IP? ????.</error>") == "?? ?? IP? ????."
    bad_url = (
        "<r><verifyFlag>FALSE</verifyFlag><resCd>3</resCd>"
        "<resMsg>API URL이 올바르지 않습니다.</resMsg></r>"
    )
    assert error_message(bad_url.encode()) == "API URL이 올바르지 않습니다. (resCd=3)"
    assert error_message(b"<RESULT><TOTALHITS>0</TOTALHITS></RESULT>") is None
    assert len(error_message(b"<error>" + b"x" * 500 + b"</error>")) <= 80


def test_xxe_rejected():
    with pytest.raises(XmlResponseError):
        parse(
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
        )


# ── 수집 ─────────────────────────────────────────────────
def hits(n, total, start=0):
    body = "".join(
        f"<HIT NO='{i + 1}'><ProjectNumber>{1415170000 + start + i}</ProjectNumber>"
        f"<ProjectTitle><Korean>과제 {start + i}</Korean></ProjectTitle></HIT>"
        for i in range(n)
    )
    return f"<RESULT><TOTALHITS>{total}</TOTALHITS><RESULTSET>{body}</RESULTSET></RESULT>"


def guarded(responses, requests, *, max_requests=None):
    def handler(request):
        requests.append(request)
        item = responses.pop(0)
        if isinstance(item, httpx.Response):
            return item
        body = item if isinstance(item, bytes) else item.encode()
        return httpx.Response(200, content=body, headers={"content-type": "text/xml"})

    async def no_sleep(_):
        return None

    return GuardedClient(
        ["www.ntis.go.kr"],
        transport=httpx.MockTransport(handler),
        resolver=lambda h: False,
        sleep=no_sleep,
        max_requests=max_requests,
        retries=0,
    )


def source_for(responses, *, display=2, max_requests=None, per_query_limit=None, queries=("궤도",)):
    requests = []
    src = NtisProjectSource(
        guarded(responses, requests, max_requests=max_requests),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        project_path="/rndopen/openApi/public_project",
        queries=list(queries),
        institutions=INSTITUTIONS,
        display_count=display,
        record_tag="HIT",
        per_query_limit=per_query_limit,
    )
    return src, requests


async def test_pages_with_start_position():
    src, reqs = source_for([hits(2, 3), hits(1, 3, start=2)])
    raws = await src.search(None, 10)
    assert [r["ProjectNumber"] for r in raws] == ["1415170000", "1415170001", "1415170002"]
    q = parse_qs(urlsplit(str(reqs[1].url)).query)
    assert q["startPosition"] == ["3"] and q["collection"] == ["project"] and q["SRWR"] == ["궤도"]
    assert q["searchFd"] == ["BI"] and q["displayCnt"] == ["2"] and q["apprvKey"] == [KEY]


async def test_per_query_limit_and_cross_query_dedup():
    src, reqs = source_for([hits(2, 10), hits(2, 2)], per_query_limit=2, queries=("궤도", "철도"))
    raws = await src.search(None, 10)
    assert len(reqs) == 2 and [r["ProjectNumber"] for r in raws] == ["1415170000", "1415170001"]


async def test_budget_returns_partial():
    src, _ = source_for([hits(2, 10), hits(2, 10, start=2)], max_requests=1)
    assert len(await src.search(None, 10)) == 2


async def test_ip_error_body_is_an_error_not_an_empty_page():
    """2026-10-27 실호출: HTTP 200 + <error>접근 허용 IP가 아닙니다.</error> — 종전 코드는 이를 ok
    로 올렸다."""
    src, _ = source_for([IP_ERROR])
    with pytest.raises(NtisError, match="접근 허용 IP") as info:
        await src.probe()
    assert KEY not in str(info.value)
    src, _ = source_for(
        [
            httpx.Response(
                200, content=IP_ERROR, headers={"content-type": "text/plain;charset=UTF-8"}
            )
        ]
    )
    with pytest.raises(NtisError):
        await src.search(None, 5)


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
    assert [e.tag for e in find_records(root)] == ["RESULTSET"]
    assert [flatten(r) for r in find_records(root, "HIT")][0]["ProjectNumber"] == "1415170000"


async def test_empty_record_tag_blocks_search_but_not_probe():
    src, _ = source_for([hits(3, 40)])
    src.record_tag = None
    with pytest.raises(NtisError, match="record_tag"):
        await src.search(None, 10)
    assert await src.probe() == {"total": 40, "record_tag_candidates": ["HIT"]}


async def test_report_source_uses_manual_parameters():
    reqs = []
    body = (FIX / "ntis_report_SYNTHETIC_manual.xml").read_bytes()
    src = NtisReportSource(
        guarded([body], reqs),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        report_path="/rndopen/openApi/rresearchpdf/",
        queries=["철도 궤도"],
        institutions=INSTITUTIONS,
        record_tag="HIT",
    )
    raws = await src.search(None, 10)
    q = parse_qs(urlsplit(str(reqs[0].url)).query)
    assert reqs[0].url.path == "/rndopen/openApi/rresearchpdf/"
    assert q["query"] == ["철도 궤도"] and q["searchField"] == ["BI"] and q["returnType"] == ["xml"]
    assert (
        q["collection"] == ["researchpdf"]
        and q["displayCount"] == ["100"]
        and q["apprvKey"] == [KEY]
    )
    docs = [src.normalize(r) for r in raws]
    assert [d.doc_id for d in docs] == ["ntis:REP-2023-0115000001", "ntis:REP-2021-0115000002"]


# ── 성과검색·연관콘텐츠 ───────────────────────────────────
def test_normalize_outcome_and_related_shapes():
    paper = normalize_outcome(
        "paper",
        {"ResultTitle/Korean": "A", "JournalName": "J", "PubYear": "2023", "Author": "홍길동"},
    )
    assert paper == {
        "kind": "paper",
        "title": "A",
        "year": "2023",
        "venue": "J",
        "result_id": None,
        "registration_no": None,
        "project_no": None,
    }
    patent = normalize_outcome(
        "patent", {"ResultTitle/Korean": "B", "Registrant": "홍길동", "RegistNumber": "10-1"}
    )
    assert patent["venue"] is None and patent["registration_no"] == "10-1"  # 개인 등록자는 지운다
    assert (
        normalize_outcome("patent", {"ResultTitle/Korean": "B", "Registrant": "한국철도공사"})[
            "venue"
        ]
        == "한국철도공사"
    )
    assert normalize_outcome("paper", {}) is None
    assert normalize_related(
        {"items": [{"PJT_ID": "1", "KOR_PJT_NM": "t", "similarity_score": 0.5, "rank": 1}]}
    ) == [{"project_no": "1", "title": "t", "score": 0.5, "rank": 1}]
    assert normalize_related({"exist": False}) == [] and normalize_related("junk") == []


async def test_insight_source_calls_both_collections_and_related_json():
    reqs = []
    responses = [
        (FIX / "ntis_outcome_SYNTHETIC_rpaper.xml").read_bytes(),
        (FIX / "ntis_outcome_SYNTHETIC_rpatent.xml").read_bytes(),
        httpx.Response(
            200,
            content=(FIX / "ntis_related_SYNTHETIC.json").read_bytes(),
            headers={"content-type": "application/json"},
        ),
    ]
    src = NtisInsightSource(
        guarded(responses, reqs),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        outcome_path="/rndopen/openApi/public_result",
        related_path="/rndopen/openApi/ConnectionContent",
    )
    outcomes = await src.outcomes("1415171234")
    assert [o["kind"] for o in outcomes] == ["paper", "paper", "patent"]
    assert (
        outcomes[0]["title"] == "차축 가속도 기반 궤도 틀림 추정"
        and outcomes[2]["venue"] == "한국철도공사"
    )
    assert "NAME-REMOVED" not in str(outcomes)
    q0, q1 = (parse_qs(urlsplit(str(r.url)).query) for r in reqs[:2])
    assert (
        q0["collection"] == ["rpaper"]
        and q0["addQuery"] == ["DBT=PAP"]
        and q0["SRWR"] == ["1415171234"]
    )
    assert q1["collection"] == ["rpatent"] and q1["addQuery"] == ["DBT=PAT"]
    related = await src.related("1415171234")
    assert reqs[2].url.path == "/rndopen/openApi/ConnectionContent"
    assert parse_qs(urlsplit(str(reqs[2].url)).query)["pjtId"] == ["1415171234"]
    assert [r["project_no"] for r in related] == [
        "1415199001",
        "1711185678",
        "1415171234",
        "../bad",
    ]


async def test_insight_source_ip_error_raises():
    reqs = []
    src = NtisInsightSource(
        guarded([IP_ERROR], reqs),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        outcome_path="/rndopen/openApi/public_result",
        related_path="/rndopen/openApi/ConnectionContent",
    )
    with pytest.raises(NtisError, match="접근 허용 IP"):
        await src.related("1415171234")


# ── 파일 캐시 ─────────────────────────────────────────────
def test_file_cache_roundtrip_and_ttl(tmp_path):
    now = [1000.0]
    cache = FileCache(tmp_path / "ntis", ttl_sec=10, clock=lambda: now[0])
    assert cache.get("outcomes:1") is None
    cache.set("outcomes:1", [{"kind": "paper", "title": "A"}])
    assert cache.get("outcomes:1") == [{"kind": "paper", "title": "A"}]
    assert all(len(p.stem) == 64 for p in (tmp_path / "ntis").glob("*.json"))  # 키는 해시로만
    now[0] += 11
    assert cache.get("outcomes:1") is None
    (tmp_path / "ntis" / "broken.json").write_text("{not json", encoding="utf-8")
    assert cache.get("x") is None
