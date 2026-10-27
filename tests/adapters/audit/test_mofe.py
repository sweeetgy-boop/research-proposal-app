"""기획재정부 경영평가 결과 보도자료 어댑터.

실페이지 발췌 fixture(담당자 정보는 가짜 값)·MockTransport·가짜 runner."""

from pathlib import Path

import httpx

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.audit import MofeEvaluationSource, normalize_mofe_item
from rra.adapters.sources.audit.mofe import parse_detail, parse_list
from rra.domain.rules.retrieval_scope import overlap_candidates

FIX = Path(__file__).parents[2] / "fixtures" / "mofe"
PDF = b"%PDF-1.4 " + b"x" * 100


def test_parse_list_rows():
    rows = parse_list((FIX / "list_eval.html").read_text(encoding="utf-8"))
    assert [r.ntt_id for r in rows] == [
        "MOSF_000000000078271",
        "MOSF_000000000074194",
        "MOSF_000000000069373",
    ]
    assert rows[1].title == "2024년도 공공기관 경영실적 평가 결과 발표"
    assert rows[1].posted == "2025-06-20" and rows[1].department == "평가분석과"


def test_parse_detail_files_without_zip_and_jsessionid():
    d = parse_detail((FIX / "detail_2024.html").read_text(encoding="utf-8"), "https://mofe.go.kr/x")
    assert d.title == "2024년도 공공기관 경영실적 평가 결과 발표" and d.posted == "2025-06-20"
    assert [n for n, _ in d.files] == [
        "250620 (보도자료) 2024년도 경영평가 결과.hwpx",
        "250620 (보도자료) 2024년도 경영평가 결과.pdf",
    ]
    assert all("jsessionid" not in u and "AtchZip" not in u for _, u in d.files)
    assert d.files[1][1].endswith("FileDown.do?atchFileId=ATCH_000000000029266&fileSn=2")


def test_normalize_audit_doc_and_strips_contact():
    doc = normalize_mofe_item(
        {
            "id": "MOSF_000000000074194",
            "url": "https://mofe.go.kr/nw/nes/detailNesDtaView.do?searchNttId=MOSF_000000000074194",
            "title": "2024년도 공공기관 경영실적 평가 결과 발표",
            "posted": "2025-06-20",
            "department": "평가분석과",
            "sha256": "b" * 64,
            "fmt": "pdf",
            "file_name": "x.pdf",
            "file_url": "https://mofe.go.kr/com/cmm/fms/FileDown.do?atchFileId=A&fileSn=2",
            "text": "한국철도공사 D 등급. 담당자 홍길동 044-215-0000 test@korea.kr",
            "toc": [],
            "pages": 20,
        }
    )
    assert doc.doc_id == "mofe:MOSF_000000000074194" and doc.doc_type == "audit"
    assert doc.raw["evaluation_year"] == 2024 and doc.raw["kind"] == "management_evaluation"
    assert "홍길동" not in doc.body and "044" not in doc.body and "korea.kr" not in doc.body
    assert overlap_candidates([(doc, 0.95)]) == []  # 감사·평가 문서는 유사과제 판정에서 빠진다


async def test_source_picks_pdf_over_hwpx(tmp_path):
    calls: list[str] = []

    def site(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("nesdta.do"):
            return httpx.Response(
                200,
                text=(FIX / "list_eval.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        if path.endswith("detailNesDtaView.do"):
            return httpx.Response(
                200,
                text=(FIX / "detail_2024.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        if "FileDown.do" in path:
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(404)

    async def runner(fd, fmt, limits):
        assert fmt == "pdf"
        return {"text": "경영실적 평가 결과 본문. " * 10, "toc": [], "pages": 2}

    async def no_sleep(_s):
        return None

    client = GuardedClient(
        ["mofe.go.kr"],
        transport=httpx.MockTransport(site),
        resolver=lambda h: False,
        sleep=no_sleep,
    )
    src = MofeEvaluationSource(
        client, store_dir=tmp_path / "mofe", limits=SandboxLimits(), runner=runner
    )
    raws = await src.search(None, 10)
    assert len(raws) == 3 and all(r["fmt"] == "pdf" for r in raws)
    assert all("fileSn=2" in r["file_url"] for r in raws)  # pdf 가 hwpx 보다 우선, 글마다 1개
    assert sum("searchKeyword1" in c for c in calls) == 1
    docs = [src.normalize(r) for r in raws]
    assert {d.doc_type for d in docs} == {"audit"} and {d.source for d in docs} == {"mofe"}
    await src.aclose()
