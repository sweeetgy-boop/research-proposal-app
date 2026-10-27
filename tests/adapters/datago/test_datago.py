"""공공데이터포털 파일데이터 어댑터.

실페이지 발췌·실JSON·실CSV 머리 fixture, MockTransport, 가짜 runner(txt)."""

from pathlib import Path

import httpx

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.alio.extract.csv_catalog import decode
from rra.adapters.sources.datago import DataGoKrFileSource, normalize_datago_item
from rra.adapters.sources.datago._html import parse_dataset_page
from rra.adapters.sources.datago._table import csv_lines_to_table
from rra.domain.rules.retrieval_scope import overlap_candidates

FIX = Path(__file__).parents[2] / "fixtures" / "datago"
INST = [{"name": "한국철도공사", "tag": "korail"}]


def test_parse_dataset_page_meta_and_download_args():
    page = parse_dataset_page((FIX / "dataset_15122753.html").read_text(encoding="utf-8"))
    assert page is not None
    assert page.public_data_pk == "15122753" and page.file_sn == "1" and page.hist_sn == "1"
    assert (
        page.detail_pk.startswith("uddi:")
        and page.title == "국토교통부_철도사고 발생 현황_20231231"
    )
    assert page.institution == "국토교통부" and page.updated == "2024-09-04"
    assert page.ext == "CSV" and page.rows == 79 and page.cycle == "연간"
    assert page.description and page.description.startswith("철도사고 : 2006년")


def test_csv_lines_to_table_caps_rows():
    lines = decode((FIX / "railroad_accidents_head.csv").read_bytes()).splitlines()
    table, rows = csv_lines_to_table(lines, max_rows=2)
    assert rows == 5 and table.splitlines()[0].startswith("일시 | 요일 | 철도구분")
    assert "전체 5행 중 2행만" in table and len(table.splitlines()) == 4


async def test_source_two_step_download_and_statistics_doc(tmp_path):
    calls: list[str] = []
    csv_bytes = (FIX / "railroad_accidents_head.csv").read_bytes()

    def site(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("/data/15122753/fileData.do"):
            return httpx.Response(
                200,
                text=(FIX / "dataset_15122753.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html;charset=UTF-8"},
            )
        if path.endswith("selectFileDataDownload.do"):
            assert dict(request.url.params)["publicDataDetailPk"].startswith("uddi:")
            return httpx.Response(  # 실서버는 JSON 을 text/html 로 준다
                200,
                content=(FIX / "download_15122753.json").read_bytes(),
                headers={"content-type": "text/html;charset=UTF-8"},
            )
        if path.endswith("fileDownload.do"):
            assert dict(request.url.params) == {
                "atchFileId": "FILE_000000003014148",
                "fileDetailSn": "1",
            }
            return httpx.Response(
                200,
                content=csv_bytes,
                headers={
                    "content-type": "application/octet-stream",
                    "content-disposition": (  # 실서버는 UTF-8 그대로 보낸다; 테스트는 RFC 5987 표기
                        "attachment; filename*=UTF-8''"
                        "%EC%B2%A0%EB%8F%84%EC%82%AC%EA%B3%A0%EB%B0%9C%EC%83%9D%ED%98%84%ED%99%A9.csv"
                    ),
                },
            )
        return httpx.Response(404)

    async def runner(fd, fmt, limits):
        assert fmt == "txt"
        return {"lines": decode(csv_bytes).splitlines()}

    async def no_sleep(_s):
        return None

    client = GuardedClient(
        ["www.data.go.kr"],
        transport=httpx.MockTransport(site),
        resolver=lambda h: False,
        sleep=no_sleep,
    )
    src = DataGoKrFileSource(
        client,
        datasets=[{"pk": 15122753, "topic": "safety", "label": "국토교통부_철도사고 발생 현황"}],
        store_dir=tmp_path / "datago",
        limits=SandboxLimits(),
        institutions=INST,
        max_rows=3,
        runner=runner,
    )
    raws = await src.search(None, 5)
    assert (
        len(raws) == 1 and raws[0]["file_name"] == "철도사고발생현황.csv" and raws[0]["rows"] == 5
    )
    assert list((tmp_path / "datago").iterdir())[0].suffix == ".csv"
    doc = src.normalize(raws[0])
    assert (
        doc.doc_id == "datago:15122753" and doc.doc_type == "statistics" and doc.source == "datago"
    )
    assert (
        doc.title == "국토교통부_철도사고 발생 현황_20231231"
        and doc.pub_date.isoformat() == "2024-09-04"
    )
    assert doc.body.startswith(
        "[통계 표] 국토교통부_철도사고 발생 현황_20231231\n제공기관: 국토교통부"
    )
    assert "일시 | 요일 | 철도구분" in doc.body and "전체 5행 중 3행만" in doc.body
    assert doc.raw["topic"] == "safety" and doc.raw["declared_rows"] == 79 and doc.orgs == []
    assert overlap_candidates([(doc, 0.99)]) == []  # 통계는 유사과제 판정에서 빠진다
    assert [c for c in calls if "fileData.do" in c] == [
        "https://www.data.go.kr/data/15122753/fileData.do"
    ]
    await src.aclose()


def test_query_filters_by_topic_label_and_korail_tag():
    doc = normalize_datago_item(
        {
            "pk": "3050961",
            "topic": "transport",
            "label": "한국철도공사_연도별 수송실적",
            "title": "한국철도공사_연도별 수송실적_20251231",
            "institution": "한국철도공사",
            "updated": "2026-09-29",
            "table": "연도 | 열차종 | 인원\n2025 | KTX | 100",
            "rows": 1,
        },
        institutions=INST,
    )
    assert doc.orgs == ["korail"] and doc.raw["topic"] == "transport"
