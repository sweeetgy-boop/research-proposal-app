"""국토교통부 정책자료 어댑터 — fixture(이름·전화 제거)와 MockTransport. 샌드박스는 가짜 runner."""

from pathlib import Path

import httpx

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.molit import MolitPolicySource, normalize_molit_item
from rra.adapters.sources.molit._html import parse_detail, parse_list
from rra.domain.rules.editions import mark_editions, plan_family

FIX = Path(__file__).parents[2] / "fixtures" / "molit"
BASE = "https://www.molit.go.kr/USR/policyData/m_34681/lst.jsp?search=철도"
PDF = b"%PDF-1.4 " + b"x" * 100


def test_parse_list_rows_total_and_pages():
    rows, total, last = parse_list((FIX / "list_rail.html").read_text(encoding="utf-8"), BASE)
    assert total == 48 and last == 5 and len(rows) == 10
    row = next(r for r in rows if "국가철도망" in r.title)
    assert row.id == "4687" and row.posted == "2023-03-30" and row.category == "도로철도>철도정책"
    assert (
        row.url.startswith("https://www.molit.go.kr/USR/policyData/m_34681/dtl.jsp?")
        and "id=4687" in row.url
    )


def test_parse_detail_attachments_department_and_no_names():
    d = parse_detail((FIX / "detail_4305.html").read_text(encoding="utf-8"), BASE)
    assert d.title == "2016년 철도업무편람" and d.posted == "2021-02-08"
    assert d.department == "철도정책과" and d.category == "도로철도 > 철도정책"
    assert d.attachments == [
        (
            "2016년 철도 업무 편람(1).pdf",
            "https://www.molit.go.kr/portal/common/download/DownloadMltm2.jsp"
            "?FilePath=portal/DextUpload/201801/20180118_141832_187.pdf"
            "&FileName=2016년 철도 업무 편람(1).pdf",
        )
    ]
    assert d.body.strip() == "2016년 철도업무편람입니다."


def test_plan_family_and_editions():
    assert plan_family("제4차 국가철도망 구축계획(2021~2030)") == ("국가철도망 구축계획", 4)
    assert plan_family("제3차 철도산업발전기본계획 2016-2020") == ("철도산업발전기본계획", 3)
    assert plan_family("철도업무편람") is None
    items = [
        {"id": "a", "title": "제3차 국가철도망 구축계획(2016~2025)", "posted": "2016-06-20"},
        {"id": "b", "title": "제4차 국가철도망 구축계획(2021~2030)", "posted": "2023-03-30"},
        {"id": "c", "title": "제4차 철도안전종합계획", "posted": "2022-01-01"},
    ]
    out = mark_editions(items)
    assert out[0]["edition"] == {
        "family": "국가철도망 구축계획",
        "no": 3,
        "status": "구판",
        "superseded_by": 4,
        "valid_until": "2023-03-30",
    }
    assert out[1]["edition"] == {"family": "국가철도망 구축계획", "no": 4, "status": "현행"}
    assert out[2]["edition"]["status"] == "현행"


def test_normalize_sets_policy_type_edition_and_strips_pii():
    doc = normalize_molit_item(
        {
            "id": "1",
            "kind": "attachment",
            "sha256": "a" * 64,
            "fmt": "pdf",
            "file_name": "plan.pdf",
            "file_url": "https://www.molit.go.kr/x.pdf",
            "url": "https://www.molit.go.kr/USR/policyData/m_34681/dtl.jsp?id=1",
            "title": "제3차 국가철도망 구축계획(2016~2025)",
            "posted": "2016-06-20",
            "category": "도로철도 > 철도정책",
            "department": "철도정책과",
            "edition": {
                "family": "국가철도망 구축계획",
                "no": 3,
                "status": "구판",
                "superseded_by": 4,
                "valid_until": "2023-03-30",
            },
            "text": "담당자 홍길동 044-201-1234. 국가철도망 구축계획 본문.",
            "toc": ["1장"],
            "pages": 10,
        }
    )
    assert doc.source == "molit" and doc.doc_type == "policy" and doc.visibility == "public"
    assert doc.doc_id == "molit:" + "a" * 16 and str(doc.valid_until) == "2023-03-30"
    assert "홍길동" not in doc.body and "044" not in doc.body
    assert doc.raw["edition"]["status"] == "구판" and doc.raw["department"] == "철도정책과"
    assert doc.pub_date.isoformat() == "2016-06-20" and doc.url == "https://www.molit.go.kr/x.pdf"


async def test_source_search_lists_details_and_parses_attachments(tmp_path):
    calls: list[str] = []

    def site(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("lst.jsp"):
            return httpx.Response(
                200,
                text=(FIX / "list_rail.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        if path.endswith("dtl.jsp"):
            return httpx.Response(
                200,
                text=(FIX / "detail_4305.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        if "DownloadMltm2" in path:
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(404)

    async def runner(fd, fmt, limits):
        assert fmt == "pdf"
        return {"text": "국가철도망 구축계획 본문. " * 10, "toc": [], "pages": 3}

    async def no_sleep(_s):
        return None

    client = GuardedClient(
        ["www.molit.go.kr"],
        transport=httpx.MockTransport(site),
        resolver=lambda h: False,
        sleep=no_sleep,
    )
    src = MolitPolicySource(
        client,
        queries=["국가철도망 구축계획"],
        store_dir=tmp_path / "molit",
        limits=SandboxLimits(),
        max_pages=1,
        runner=runner,
    )
    raws = await src.search(None, 3)
    assert len(raws) == 3 and all(r["kind"] == "attachment" for r in raws)
    docs = [src.normalize(r) for r in raws]
    assert {d.source for d in docs} == {"molit"} and all(d.doc_type == "policy" for d in docs)
    assert (
        len({d.doc_id for d in docs}) == 1
    )  # 같은 PDF(같은 sha) → 같은 doc_id (dedup 은 ingest 가)
    assert list((tmp_path / "molit").iterdir())[0].suffix == ".pdf"
    assert (
        sum(1 for c in calls if "lst.jsp" in c) == 1
        and sum(1 for c in calls if "dtl.jsp" in c) == 3
    )
    await src.aclose()
