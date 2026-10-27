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


def test_bare_less_than_before_space_is_repaired():
    # 2026-10-27 실응답(철도 궤도 2쪽·철도 안전 1쪽):
    # "R&amp;D 동향조사 < <span class=…>철도</span>교통" — 공백 앞의 맨 < 는 태그가 아니다.
    body = '<r><Korean>2019 R&amp;D 동향 < <span class="w">철도</span>교통 <\n</Korean></r>'.encode()
    with pytest.raises(XmlResponseError, match="ParseError"):
        parse(body)
    root = parse_response(body)
    assert root.find("Korean/span") is not None  # 진짜 태그는 그대로
    assert "".join(root.find("Korean").itertext()) == "2019 R&D 동향 < 철도교통 <\n"
