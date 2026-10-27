"""NTIS — 과제검색·연구보고서·성과·연관콘텐츠. 키·네트워크 없음 (MockTransport + 실응답 fixture).

fixture 는 2026-10-27 실응답 녹화(tests/fixtures/ntis/README.md, 사람 이름은 NAME-REMOVED).
실서버는 Accept 에 json 이 있으면 XML 을 JSON 문자열로 감싸 보내고(`wrapped`), 연구보고서는 맨 `&`
를 내보낸다 — 둘 다 여기서 재현한다.
"""

import json
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
from rra.adapters.sources.ntis.client import (
    error_message,
    parse_response,
    probe_result,
    unwrap_json_string,
)
from rra.adapters.sources.ntis.insights import (
    PROBE_PROJECT_NO,
    normalize_outcome,
    normalize_related,
)
from rra.domain.models import Document
from rra.domain.rules.dedup import dedup
from rra.domain.rules.overlap import tier_of

FIX = Path(__file__).parents[1] / "fixtures" / "ntis"
PROJECT_FIX = FIX / "ntis_project_20261027_track.xml"
REPORT_FIX = FIX / "ntis_report_20261027_track.xml"
PAPER_FIX = FIX / "ntis_outcome_20261027_rpaper.xml"
PATENT_FIX = FIX / "ntis_outcome_20261027_rpatent.xml"
RELATED_FIX = FIX / "ntis_related_20261027.json"
JSON_CT = {"content-type": "application/json;charset=UTF-8"}
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


def wrapped(path: Path) -> bytes:
    """실서버 꼴 — 본문 전체를 JSON 문자열 하나로 (Accept 에 application/json 이 있을 때)."""
    return json.dumps(path.read_text(encoding="utf-8")).encode("utf-8")


def test_fixture_highlight_spans_keep_tail_text():
    """과제검색은 강조 태그가 이스케이프돼 오고(strip_highlight), 보고서는 날 `<span>` 이 텍스트
    안에 온다 — flatten 이 아래로 내려가면 강조어 뒤 텍스트가 사라지므로 잎으로 본다."""
    flat = flatten(find_records(parse_response(PROJECT_FIX.read_bytes()), "HIT")[0])
    assert "search_word" in flat["ProjectTitle/Korean"] and "/span" not in "".join(flat)
    assert flat["Manager/Name"] == flat["Researchers/Name"] == "NAME-REMOVED"
    doc = normalize_project(flat, INSTITUTIONS)
    assert doc.title == (
        "콘크리트 궤도/철도교량의 성능중심 설계법 개발 및 철도 토공노반 설계기준 개선"
    )
    assert doc.orgs == ["krri"] and doc.raw["agencies"] == ["한국철도기술연구원"]
    assert doc.raw["business"] == "철도기술연구사업" and doc.raw["ministry"] == "국토교통부"
    assert doc.raw["science_class"] == "철도교통기술 | 시설물 설계/해석기술"  # 반복 요소 중복 제거
    assert doc.pub_date.isoformat() == "2013-12-27" and doc.project_period[1].isoformat() == (
        "2018-06-26"
    )
    report = flatten(find_records(parse_response(REPORT_FIX.read_bytes()), "HIT")[0])
    assert report["PublicationAgency"] == "한국철도기술연구원"  # `한국<span>철도</span>기술연구원`
    assert report["ResultTitle/Korean"] == "철도 구성품 환경성 향상 기술개발"
    assert "ResultTitle/Korean/span" not in report and report["ManagerName"] == "NAME-REMOVED"


# ── 실응답 형식: JSON 문자열 감싸기·맨 & (2026-10-27 ParseError 원인) ──────────
def test_unwrap_json_string_shapes():
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n<RESULT><TOTALHITS>1</TOTALHITS></RESULT>'
    assert unwrap_json_string(json.dumps(xml.decode()).encode()) == xml
    assert unwrap_json_string(b"\xef\xbb\xbf" + json.dumps(xml.decode()).encode()) == xml
    assert unwrap_json_string(xml) is xml  # 날 XML 은 그대로
    obj = b'{"items": []}'
    assert unwrap_json_string(obj) is obj  # JSON 객체는 건드리지 않는다
    assert unwrap_json_string(b'"not closed') == b'"not closed'
    inner = json.dumps({"exist": True, "items": []})
    assert json.loads(unwrap_json_string(json.dumps(inner).encode())) == {
        "exist": True,
        "items": [],
    }


def test_wrapped_real_response_was_the_parse_error_and_is_now_parsed():
    with pytest.raises(XmlResponseError, match="ParseError"):
        parse(wrapped(PROJECT_FIX))  # 종전 경로 — `"<?xml` 로 시작하는 본문
    root = parse_response(wrapped(PROJECT_FIX))
    assert root.tag == "RESULT" and root.findtext("TOTALHITS") == "1087"
    assert len(find_records(root, "HIT")) == 10 and root.findtext("HITS") == "10"


def test_bare_ampersand_in_report_docurl_is_repaired():
    body = REPORT_FIX.read_bytes()
    assert b"dbt=TRKO&cn=" in body  # 녹화 원문 그대로 (이스케이프 없는 &)
    with pytest.raises(XmlResponseError, match="ParseError"):
        parse(body)
    docs = [
        normalize_report(flatten(r), INSTITUTIONS)
        for r in find_records(parse_response(body), "HIT")
    ]
    assert docs[0].url == (
        "https://scienceon.kisti.re.kr/commons/util/originalView.do?dbt=TRKO&cn=TRKO201300021692"
    )
    assert parse_response(b"<r><a>x &amp; y &#39; &lt;</a></r>").findtext("a") == "x & y ' <"


def test_undefined_named_entity_is_treated_as_bare_ampersand():
    # 2026-10-27 실응답(철도 궤도, displayCount 100) 2722행 "Joint R&DB;" — DTD 가 없으니 &DB; 는
    # 정의되지 않은 엔티티라 ParseError. 미리 정의된 5개·숫자 참조만 남기고 나머지는 맨 & 로 본다.
    body = b"<r><English>Policy;Joint R&DB;Turn - Key;EPCM &copy; &amp; &#x41;</English></r>"
    with pytest.raises(XmlResponseError, match="ParseError"):
        parse(body)
    assert parse_response(body).findtext("English") == (
        "Policy;Joint R&DB;Turn - Key;EPCM &copy; & A"
    )


def test_probe_result_prefers_configured_tag_over_navigation_entries():
    root = parse_response(PROJECT_FIX.read_bytes())
    assert [e.tag for e in find_records(root)] == ["NAVIGATIONENTRY"] * 13  # 자동 탐지는 틀린다
    assert probe_result(root, "HIT") == {
        "total": 1087,
        "hits": 10,
        "record_tag_matches": True,
        "record_tag_candidates": ["HIT", "NAVIGATIONENTRY"],
    }
    assert probe_result(root, "ROW") == {
        "total": 1087,
        "hits": 0,
        "record_tag_matches": False,
        "record_tag_candidates": ["NAVIGATIONENTRY"],
    }
    assert probe_result(root, None) == {"total": 1087, "record_tag_candidates": ["NAVIGATIONENTRY"]}


# ── 보고서 정규화 (실응답) ────────────────────────────────
def test_normalize_report_from_recorded_fixture():
    root = parse_response(REPORT_FIX.read_bytes())
    docs = [normalize_report(flatten(r), INSTITUTIONS) for r in find_records(root, "HIT")]
    first, second = docs[:2]
    assert first.doc_id == "ntis:REP-2011-0115023251" and first.doc_type == "report"
    assert first.title == "철도 구성품 환경성 향상 기술개발"  # 날 강조 태그 제거
    assert first.pub_date.isoformat() == "2011-01-01" and first.lang == "ko"
    assert first.orgs == ["krri"] and first.raw["project_no"] == "1415119784"
    assert first.raw["report_no"] == "TRKO201300021692" and first.raw["year"] == "2011"
    assert first.raw["specialized_agency"] == "한국철도기술연구원"
    assert first.raw["agency_project_no"] == "PK11002B" and first.raw["orgs_named"] == [
        "한국철도기술연구원",
        "한국철도기술연구원",
    ]
    assert first.codes == ["제동디스크", "강화노반", "슬래브궤도", "포장궤도", "철도 교량"]
    assert first.toc and "국내외 연구현황" in " ".join(first.toc)
    assert "search_word" not in first.abstract and first.abstract.startswith("... 제동디스크")
    assert second.doc_id == "ntis:REP-2012-0118227104" and second.orgs == []  # 고려대학교
    assert second.raw["project_no"] == "1345147315" and second.pub_date.isoformat() == "2012-01-01"
    assert all(not d.authors for d in docs) and "NAME-REMOVED" not in str(
        [d.model_dump() for d in docs]
    )


def test_ntis_report_merges_with_scienceon_report_of_same_project():
    root = parse_response(REPORT_FIX.read_bytes())
    ntis = normalize_report(flatten(find_records(root, "HIT")[0]), INSTITUTIONS)
    scienceon = Document(
        doc_id="scienceon:CN123",
        source="scienceon",
        doc_type="internal_report",
        title="철도 구성품 환경성 향상 기술개발",
        abstract="짧은 초록",
        pub_date=ntis.pub_date,
        raw={"project_no": "1415119784"},
        text_basis="abstract",
    )
    kept = dedup([scienceon, ntis])
    assert [d.doc_id for d in kept] == ["ntis:REP-2011-0115023251"]  # 초록이 긴 쪽


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
    body = httpx.Response(200, content=wrapped(REPORT_FIX), headers=JSON_CT)  # 실서버 꼴
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
    assert len(docs) == 10 and docs[0].doc_id == "ntis:REP-2011-0115023251"
    assert docs[1].doc_id == "ntis:REP-2012-0118227104"
    assert len(reqs) == 1  # 10건 < displayCount 100 → 다음 페이지 없음


async def test_project_source_reads_wrapped_real_response_and_probe_is_ok():
    """2026-10-27 `rra sources check` ParseError 재현 → 수정 뒤 ok. search 도 같은 본문을 읽는다."""
    responses = [httpx.Response(200, content=wrapped(PROJECT_FIX), headers=JSON_CT)]
    src, reqs = source_for(responses, display=100)
    assert await src.probe() == {
        "total": 1087,
        "hits": 10,
        "record_tag_matches": True,
        "record_tag_candidates": ["HIT", "NAVIGATIONENTRY"],
    }
    assert "application/json" in reqs[0].headers["accept"]  # 한글 오류 문구 때문에 유지
    src, _ = source_for(
        [httpx.Response(200, content=wrapped(PROJECT_FIX), headers=JSON_CT)], display=100
    )
    raws = await src.search("철도 궤도", 50)
    assert [r["ProjectNumber"] for r in raws][:3] == ["1615007833", "2610000650", "1711047418"]
    assert len(raws) == 10 and "Manager/Name" in raws[0]  # 정규화가 읽지 않을 뿐 원본에는 있다
    docs = [src.normalize(r) for r in raws]
    assert all(not d.authors and "NAME-REMOVED" not in str(d.model_dump()) for d in docs)
    assert sum("krri" in d.orgs for d in docs) == 7 and sum("korail" in d.orgs for d in docs) == 1


async def test_sources_check_row_is_ok_for_the_recorded_response():
    """진단 유스케이스 끝까지 — 가짜 클라이언트로 `rra sources check --source ntis` 행이 ok."""
    from rra.application.usecases.diagnostics import CheckSources, SourceTarget

    src, _ = source_for([httpx.Response(200, content=wrapped(PROJECT_FIX), headers=JSON_CT)])
    rows = await CheckSources(
        [SourceTarget("ntis", "www.ntis.go.kr", True, {"RRA_NTIS_KEY": True}, lambda: src)]
    )()
    assert rows[0]["roundtrip"] == "ok" and rows[0]["result"]["record_tag_matches"] is True
    assert rows[0]["result"]["total"] == 1087 and KEY not in json.dumps(rows)


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
        "doi": None,
        "regist_type": None,
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
        httpx.Response(200, content=wrapped(PAPER_FIX), headers=JSON_CT),
        PATENT_FIX.read_bytes(),  # 날 XML 로 와도 같다
        httpx.Response(200, content=wrapped(RELATED_FIX), headers=JSON_CT),  # JSON 안의 JSON
    ]
    src = NtisInsightSource(
        guarded(responses, reqs),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        outcome_path="/rndopen/openApi/public_result",
        related_path="/rndopen/openApi/ConnectionContent",
    )
    outcomes = await src.outcomes("1615007833")
    assert [o["kind"] for o in outcomes] == ["paper"] * 10 + ["patent"] * 2
    assert outcomes[0]["title"].startswith("철도궤도 하부구조물 평가를 위한") and outcomes[0][
        "venue"
    ].startswith("한국지반환경공학회논문집")
    assert outcomes[0]["result_id"] == "JNL-2015-0016669567" and outcomes[0]["year"] == "2015"
    assert outcomes[1]["doi"] == "10.7843/kgs.2015.31.11.25"
    assert outcomes[10]["venue"] == "한국철도기술연구원" and outcomes[10]["regist_type"] == "출원"
    assert outcomes[10]["registration_no"] == "10-2015-0033088"
    assert outcomes[11]["regist_type"] == "등록" and outcomes[11]["registration_no"].startswith(
        "10-"
    )
    assert all(o["project_no"] == "1615007833" for o in outcomes)  # ProjectID 로 대조
    assert "NAME-REMOVED" not in str(outcomes) and "Author" not in str(outcomes)
    q0, q1 = (parse_qs(urlsplit(str(r.url)).query) for r in reqs[:2])
    assert (
        q0["collection"] == ["rpaper"]
        and q0["addQuery"] == ["DBT=PAP"]
        and q0["SRWR"] == ["1615007833"]
    )
    assert q1["collection"] == ["rpatent"] and q1["addQuery"] == ["DBT=PAT"]
    related = await src.related("1615007833")
    assert reqs[2].url.path == "/rndopen/openApi/ConnectionContent"
    assert parse_qs(urlsplit(str(reqs[2].url)).query)["pjtId"] == ["1615007833"]
    assert [r["project_no"] for r in related][:3] == ["2610000277", "1615013189", "1615007523"]
    assert len(related) == 10 and all(0 < r["score"] < 1 and r["rank"] for r in related)
    assert related[0]["title"].startswith("신기술·신공법 대응 철도 형식승인")


async def test_outcomes_of_another_project_are_filtered_out():
    """성과 레코드의 ProjectID 가 조회 과제와 다르면 버린다 (검색이 번호를 본문에서 찾아 줄 때)."""
    src = NtisInsightSource(
        guarded([PAPER_FIX.read_bytes(), PATENT_FIX.read_bytes()], []),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        outcome_path="/rndopen/openApi/public_result",
        related_path="/rndopen/openApi/ConnectionContent",
    )
    assert await src.outcomes("1415171234") == []


def test_related_json_with_nan_and_double_wrapping():
    inner = '{"exist": true, "items": [{"PJT_ID": "1", "KOR_PJT_NM": "t", "similarity_score": NaN, '
    inner += '"rank": 2, "creat_dt": NaN}, {"PJT_ID": "2", "KOR_PJT_NM": "u", "similarity_score": '
    inner += '0.5, "rank": 1}], "count": 2}'
    payload = json.loads(unwrap_json_string(json.dumps(inner).encode()))
    assert normalize_related(payload) == [
        {"project_no": "1", "title": "t", "score": None, "rank": 2},  # NaN 점수는 없음으로
        {"project_no": "2", "title": "u", "score": 0.5, "rank": 1},
    ]
    assert json.loads(RELATED_FIX.read_text(encoding="utf-8"))["count"] == 10  # 녹화본은 푼 꼴


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


async def test_ip_error_is_a_source_ip_blocked_subtype_and_key_errors_are_not():
    """레인 I: IP 거부 본문은 NtisIpBlocked(SourceIpBlocked) — 호출자가 그 자료원만 건너뛴다."""
    from rra.adapters.sources.ntis import NtisIpBlocked
    from rra.domain.rules.source_ip import SourceIpBlocked

    src, _ = source_for([IP_ERROR])
    with pytest.raises(NtisIpBlocked) as info:
        await src.probe()
    assert isinstance(info.value, SourceIpBlocked) and isinstance(info.value, NtisError)
    assert KEY not in str(info.value)
    src, _ = source_for(["<error>유효한 인증키가 아닙니다.</error>"])
    with pytest.raises(NtisError) as info:
        await src.probe()
    assert not isinstance(info.value, SourceIpBlocked)


async def test_insight_source_probe_counts_without_bodies():
    """레인 I: `rra sources check --source ntis_insights` — 성과 2회 + 연관 1회, 건수만."""
    from rra.application.ports import ProbingSource

    reqs = []
    src = NtisInsightSource(
        guarded(
            [
                httpx.Response(200, content=wrapped(PAPER_FIX), headers=JSON_CT),
                httpx.Response(200, content=wrapped(PATENT_FIX), headers=JSON_CT),
                httpx.Response(200, content=wrapped(RELATED_FIX), headers=JSON_CT),
            ],
            reqs,
        ),
        apprv_key=SecretStr(KEY),
        base_url="https://www.ntis.go.kr",
        outcome_path="/rndopen/openApi/public_result",
        related_path="/rndopen/openApi/ConnectionContent",
    )
    assert isinstance(src, ProbingSource) and src.source == "ntis_insights"
    result = await src.probe()
    assert len(reqs) == 3 and result["probe_project_no"] == PROBE_PROJECT_NO == "1615007833"
    assert result == {"probe_project_no": "1615007833", "outcomes": 12, "related": 10}
    assert KEY not in str(result)
