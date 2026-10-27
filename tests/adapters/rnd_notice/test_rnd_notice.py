"""정부 R&D 공고(KAIA·IRIS) 어댑터 — fixture 해석, 스냅샷 수집(MockTransport), 마감→valid_until,
개인정보 제거, 중복 합침.

fixture 의 담당자 이름·전화는 가짜 값이다. 샌드박스는 가짜 runner."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.sources.korail_web.snapshot import SnapshotDir, read_manifest, read_summary
from rra.adapters.sources.rnd_notice import NoticeConfig, RndNoticeCrawler, RndNoticeSource
from rra.adapters.sources.rnd_notice._html import (
    parse_iris_detail,
    parse_iris_list,
    parse_kaia_detail,
    parse_kaia_list,
)
from rra.adapters.sources.rnd_notice.source import normalize_notice

FIX = Path(__file__).parents[2] / "fixtures" / "rnd_notice"
KAIA_LIST = "https://www.kaia.re.kr/KAIA/contents/K30101000000.do"
IRIS_VIEW = "https://www.iris.go.kr/contents/retrieveBsnsAncmView.do"
PDF = b"%PDF-1.4 " + b"x" * 200
TODAY = date(2026, 10, 27)
KAIA_ID = "20260716111420013221"
IRIS_DUP = {  # KAIA 공고와 같은 제목·기관·공고일 → 한 문서로 합쳐져야 한다
    "ancmId": "024999",
    "sorgnNm": "국토교통과학기술진흥원",
    "blngGovdSeNm": "국토교통부",
    "ancmTl": "2026년 국토교통연구기획 사업 제2차 시행 공고",
    "ancmDe": "2026-07-16",
    "rcveStrDe": "2026.07.16",
    "rcveEndDe": "2026.08.18",
    "pbofrTpSeNmLst": "자유공모",
    "rcveStt": "마감",
    "ancmNo": "국토교통부 공고 제2026-29호",
}

CONFIG = NoticeConfig.from_config(
    {
        "since_days": 730,
        "max_notices": 500,
        "sites": {
            "kaia": {
                "base_url": "https://www.kaia.re.kr",
                "list_path": "/KAIA/contents/K30101000000.do",
                "agency": "국토교통과학기술진흥원",
                "max_pages": 3,
            },
            "iris": {
                "base_url": "https://www.iris.go.kr",
                "list_path": "/contents/retrieveBsnsAncmBtinSituList.do",
                "view_path": "/contents/retrieveBsnsAncmView.do",
                "ministry_code": "AR4004",
                "statuses": [
                    "ancmPre",
                    "ancmEnd",
                ],  # 예정 목록의 2022년 행이 마감 목록을 막으면 안 된다
                "max_pages": 3,
            },
        },
    }
)


# ── 해석 (순수) ───────────────────────────────────────────
def test_parse_kaia_list_rows_total_pages():
    rows, total, last = parse_kaia_list((FIX / "kaia_list_p1.html").read_text(), KAIA_LIST)
    assert total == 1224 and last == 10 and len(rows) == 10
    row = next(r for r in rows if r.id == KAIA_ID)
    assert row.title.startswith("(공고-국-제29호) 2026년 국토교통연구기획")
    assert row.posted == "2026-07-16" and row.period == "2026-07-16 ~ 2026-08-18"
    assert row.program == "국토교통연구기획" and row.url == f"{KAIA_LIST}?schM=view&id={KAIA_ID}"


def test_parse_kaia_detail_period_and_attachments():
    d = parse_kaia_detail((FIX / "kaia_view_20260716.html").read_text(), KAIA_LIST)
    assert d.posted == "2026-07-16" and d.period == "2026-07-16 ~ 2026-08-18"
    names = [a["name"] for a in d.attachments]
    assert names[0].endswith("공고문.pdf") and names[2].endswith(".zip")
    assert d.attachments[0]["url"] == "https://www.kaia.re.kr/afile/fileDownload/Bb7mn"
    assert d.attachments[0]["size"] == 134 * 1024 and d.body == ""  # 본문은 PDF 뷰어뿐


def test_parse_iris_list_and_detail_without_contact_fields():
    rows, total, pages = parse_iris_list(
        json.loads((FIX / "iris_list_p1.json").read_text()), IRIS_VIEW
    )
    assert total == 16 and pages == 2 and len(rows) == 3
    assert rows[0].id == "024477" and rows[0].agency == "한국연구재단"
    assert rows[0].period == "2026-10-16 ~ 2026-11-17" and rows[0].ministry == "과학기술정보통신부"
    d = parse_iris_detail((FIX / "iris_view_024477.html").read_text())
    assert d.posted == "2026-10-16" and d.period == "2026-10-16 ~ 2026-11-17"
    assert d.info["전문기관"] == "한국연구재단" and not any("담당자" in k for k in d.info)
    assert "김철수" not in json.dumps(d.info, ensure_ascii=False)
    assert d.body.startswith("과학기술정보통신부 공고 제2026-1007호")
    assert [a["name"][-4:] for a in d.attachments] == ["hwpx", ".zip"]
    assert d.attachments[0]["url"] is None and d.attachments[0]["file_id"] == "FILEID1111=="


# ── 수집 (MockTransport) ──────────────────────────────────
class Site:
    """두 사이트를 흉내 내는 transport. 요청 URL 을 기록한다."""

    def __init__(self, *, fail_detail: int = 0):
        self.urls: list[str] = []
        self.fail_detail = fail_detail
        iris = json.loads((FIX / "iris_list_p1.json").read_text())
        iris["listBsnsAncmBtinSitu"].append(IRIS_DUP)
        self.iris_json = iris

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.urls.append(url)
        host, path, query = request.url.host, request.url.path, parse_qs(request.url.query.decode())
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /wklounge/\n")
        if host == "www.kaia.re.kr":
            if path.startswith("/afile/fileDownload/"):
                return httpx.Response(
                    200,
                    content=PDF,
                    headers={
                        "content-type": "application/octet-stream",
                        "content-disposition": (
                            "attachment; filename*=UTF-8''%EA%B3%B5%EA%B3%A0.pdf"
                        ),
                    },
                )
            if query.get("schM") == ["view"]:
                if self.fail_detail:
                    self.fail_detail -= 1
                    return httpx.Response(503)
                return httpx.Response(200, text=(FIX / "kaia_view_20260716.html").read_text())
            page = query.get("page", ["1"])[0]
            if page == "1":
                return httpx.Response(200, text=(FIX / "kaia_list_p1.html").read_text())
            return httpx.Response(200, text="<html><body><table></table></body></html>")
        if host == "www.iris.go.kr":
            if request.method == "POST":
                form = parse_qs(request.content.decode())
                assert form["blngGovdSeArr"] == ["AR4004"] and form["ancmPrg"][0] in (
                    "ancmPre",
                    "ancmEnd",
                )
                assert "sorgnIdArr" not in form and "techFildArr" not in form  # 빈 Arr → 0건
                if form["ancmPrg"] == ["ancmPre"]:  # 접수예정에 2년 밖 행 1건 (실사이트와 같음)
                    old = {
                        **IRIS_DUP,
                        "ancmId": "001234",
                        "ancmDe": "2022-01-14",
                        "ancmTl": "옛 공고",
                    }
                    return httpx.Response(
                        200,
                        json={
                            "listBsnsAncmBtinSitu": [old],
                            "paginationInfo": {"totalPageCount": 1},
                        },
                    )
                if form["pageIndex"] == ["1"]:
                    return httpx.Response(200, json=self.iris_json)
                return httpx.Response(
                    200, json={"listBsnsAncmBtinSitu": [], "paginationInfo": {"totalPageCount": 2}}
                )
            if path == "/contents/retrieveBsnsAncmView.do":
                return httpx.Response(200, text=(FIX / "iris_view_024477.html").read_text())
        return httpx.Response(404)


async def _sleep(_s):
    return None


def make_crawler(tmp_path: Path, site: Site, *, today=TODAY, config=CONFIG, retries=0):
    client = GuardedClient(
        ["www.kaia.re.kr", "www.iris.go.kr"],
        transport=httpx.MockTransport(site),
        resolver=lambda host: False,
        retries=retries,
        sleep=_sleep,
    )
    return RndNoticeCrawler(client, config, root=tmp_path / "rnd_notice", today=today, sleep=_sleep)


async def test_download_writes_manifest_dedups_and_strips_pii(tmp_path):
    site = Site()
    crawler = make_crawler(tmp_path, site)
    report = await crawler.download(limit=50)
    await crawler.aclose()
    snap = SnapshotDir(tmp_path / "rnd_notice", "2026-10-27")
    recs = read_manifest(snap)
    assert report.notices == {"kaia": 10, "iris": 3} and report.duplicates == 1
    assert "iris:001234" not in recs  # 2년 밖 행은 건너뛰고 다음 상태(마감) 목록은 계속 받는다
    kaia = recs[f"kaia:{KAIA_ID}"]
    assert kaia["deadline"] == "2026-08-18" and kaia["start"] == "2026-07-16"
    assert kaia["agency"] == "국토교통과학기술진흥원" and kaia["ministry"] == "국토교통부"
    assert kaia["program"] == "국토교통연구기획" and kaia["terms"].startswith("KAIA")
    atts = kaia["attachments"]
    assert [a["downloaded"] for a in atts] == [True, True, False] and atts[2]["reason"] == "type"
    assert atts[0]["ext"] == "pdf" and (snap.path / atts[0]["path"]).read_bytes() == PDF
    assert kaia["text_file"] is None  # KAIA 본문은 PDF 뷰어뿐
    dup = recs["iris:024999"]
    assert dup["duplicate_of"] == f"kaia:{KAIA_ID}" and dup["key"] == kaia["key"]
    iris = recs["iris:024477"]
    assert iris["deadline"] == "2026-11-17" and iris["agency"] == "한국연구재단"
    assert iris["attachments"][0]["reason"] == "post_download"
    text = (snap.path / iris["text_file"]).read_text()
    assert "김철수" not in text and "0212345678" not in text and "공고 제2026-1007호" in text
    assert report.skipped_files == {"type": 13, "post_download": 3}  # zip 10+3
    summary = read_summary(snap)
    assert summary["terms"]["iris"] and summary["config"]["since_days"] == 730
    # 요청은 허용목록 호스트로만, robots 는 사이트마다 1회
    assert all(
        u.startswith(("https://www.kaia.re.kr", "https://www.iris.go.kr")) for u in site.urls
    )
    assert sum(u.endswith("/robots.txt") for u in site.urls) == 2


async def test_download_stops_at_since_cutoff(tmp_path):
    crawler = make_crawler(tmp_path, Site(), today=date(2029, 1, 1))  # 모든 공고가 2년 밖
    report = await crawler.download()
    assert report.notices == {"kaia": 0, "iris": 0}


async def test_detail_failures_back_off_then_hold_and_retry_once(tmp_path):
    sleeps: list[float] = []

    async def record(s):
        sleeps.append(s)

    site = Site(fail_detail=3)  # 첫 상세 3회 연속 503 → 보류 → 끝에 1회 재시도(성공)
    client = GuardedClient(
        ["www.kaia.re.kr", "www.iris.go.kr"],
        transport=httpx.MockTransport(site),
        resolver=lambda host: False,
        retries=0,
        sleep=record,
    )
    crawler = RndNoticeCrawler(client, CONFIG, root=tmp_path / "r", today=TODAY, sleep=record)
    report = await crawler.download(limit=50)
    assert sleeps[:2] == [2.0, 5.0] and 10.0 in sleeps  # 백오프 2s·5s, 끝에 10s 간격 재시도
    assert report.notices["kaia"] == 10 and report.held == []


async def test_robots_disallow_blocks_site_path(tmp_path):
    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /KAIA/\n")
        return httpx.Response(200, text=(FIX / "kaia_list_p1.html").read_text())

    cfg = NoticeConfig.from_config({"sites": {"kaia": CONFIG.sites[0].__dict__}})
    client = GuardedClient(
        ["www.kaia.re.kr"], transport=httpx.MockTransport(transport), resolver=lambda h: False
    )
    crawler = RndNoticeCrawler(client, cfg, root=tmp_path / "r", today=TODAY, sleep=_sleep)
    report = await crawler.download()
    assert report.notices == {"kaia": 0} and report.errors == 1


# ── 적재 (스냅샷 → Document) ──────────────────────────────
async def fake_runner(fd, fmt, limits):
    return {
        "text": "공고문 본문. 사업 개요: 철도 상태기반 유지보수 기술개발. " * 5,
        "toc": [],
        "pages": 2,
    }


async def test_source_reads_snapshot_merges_duplicates_and_sets_valid_until(tmp_path):
    crawler = make_crawler(tmp_path, Site())
    await crawler.download(limit=50)
    await crawler.aclose()
    source = RndNoticeSource(tmp_path / "rnd_notice", limits=SandboxLimits(), runner=fake_runner)
    assert source.status()["items"] == 13 and source.status()["duplicates"] == 1
    raws = await source.search(None, 100)
    by_id = {r["native_id"]: r for r in raws}
    assert "iris:024999" not in by_id and f"kaia:{KAIA_ID}" in by_id
    doc = source.normalize(by_id[f"kaia:{KAIA_ID}"])
    assert doc.source == "rnd_notice" and doc.doc_type == "rnd_notice"
    assert doc.valid_until == date(2026, 8, 18) and doc.pub_date == date(2026, 7, 16)
    assert doc.is_valid_on(date(2026, 8, 18)) and not doc.is_valid_on(date(2026, 8, 19))
    assert doc.visibility == "public" and doc.orgs == ["molit"]
    assert doc.raw["notice"]["agency"] == "국토교통과학기술진흥원"
    assert doc.raw["notice"]["deadline"] == "2026-08-18" and doc.raw["notice"]["program"]
    assert doc.raw["notice"]["also_in"] == [f"{IRIS_VIEW}?ancmId=024999"]
    assert doc.body.startswith("[첨부:") and "공고문.pdf]" in doc.body.splitlines()[0]
    assert doc.doc_id == "rnd_notice:" + by_id[f"kaia:{KAIA_ID}"]["key"]
    iris = source.normalize(by_id["iris:024477"])
    assert iris.valid_until == date(2026, 11, 17) and iris.orgs == [] and "김철수" not in iris.body


def test_normalize_strips_pii_and_requires_text():
    doc = normalize_notice(
        {
            "key": "abc",
            "title": "공고",
            "text": "담당자 홍길동 과장 (02-123-4567, a@b.kr) 문의. 본문입니다.",
            "deadline": "2026-12-31",
            "agency": "KAIA",
        }
    )
    assert "홍길동" not in doc.body and "02-123-4567" not in doc.body and "a@b.kr" not in doc.body
    assert doc.valid_until == date(2026, 12, 31)
    with pytest.raises(ValueError):
        normalize_notice({"key": "x", "title": "t", "text": "  "})
