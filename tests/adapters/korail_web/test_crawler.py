"""KorailWebCrawler — MockTransport 로 info.korail.com 을 흉내 낸다. 네트워크·DNS·대기 없음."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources.korail_web import CrawlConfig, KorailWebCrawler, MenuSpec
from rra.adapters.sources.korail_web.snapshot import (
    SnapshotDir,
    latest_snapshot,
    load_index,
    read_manifest,
)

FIX = Path(__file__).parents[2] / "fixtures" / "korail_web"
UA = "RRA research-proposal-app (internal research use) +https://github.com/x/y"
HOST = "https://info.korail.com"
HWP = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"hwp-body" * 10
JPG = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x64\x00\xc8" + b"\x00" * 20
PDF = b"%PDF-1.4 fake"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class Site:
    """경로 → 응답. 요청을 기록한다. 429 를 n 회 내도록 꾸밀 수 있다."""

    def __init__(self):
        self.requests: list[str] = []
        self.fail: dict[str, list[int]] = {}
        self.robots = ""
        self.list_pages = {1: _fx("board_list_press.html")}
        self.contents_html = _fx("contents_716.html")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        path = request.url.path
        q = dict(request.url.params)
        if path in self.fail and self.fail[path]:
            return httpx.Response(self.fail[path].pop(0))
        if path == "/robots.txt":
            return httpx.Response(200, text=self.robots, headers={"content-type": "text/plain"})
        if path == "/info/selectBbsNttList.do":
            page = int(q.get("pageIndex", "1"))
            html = self.list_pages.get(page)
            if html is None:  # 마지막 쪽 뒤: 행이 없는 목록
                html = (
                    "<html><head><title>x</title></head><body>"
                    '<div id="container">총게시물 : 0 건</div></body></html>'
                )
            return httpx.Response(
                200, text=html, headers={"content-type": "text/html; charset=UTF-8"}
            )
        if path == "/info/selectBbsNttView.do":
            return httpx.Response(
                200, text=_fx("board_view_press.html"), headers={"content-type": "text/html"}
            )
        if path == "/info/contents.do":
            return httpx.Response(
                200, text=self.contents_html, headers={"content-type": "text/html"}
            )
        if path == "/info/downloadBbsFile.do":
            no = q.get("atchmnflNo")
            if no == "28822":
                return httpx.Response(
                    200,
                    content=HWP,
                    headers={
                        "content-type": "application/x-msdownload",
                        "content-disposition": "attachment; filename=261022 x.hwp",
                    },
                )
            return httpx.Response(
                200,
                content=JPG,
                headers={
                    "content-type": "application/x-msdownload",
                    "content-disposition": "attachment; filename=photo.jpg",
                },
            )
        if path.startswith("/crosseditor_u/"):
            return httpx.Response(200, content=JPG, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)


def make(
    tmp_path: Path,
    site: Site,
    menus: list[MenuSpec],
    *,
    today=date(2026, 10, 27),
    sleeps=None,
    pdf_probe=None,
):
    sleeps = sleeps if sleeps is not None else []

    async def fake_sleep(sec):
        sleeps.append(sec)

    client = GuardedClient(
        ["info.korail.com"],
        transport=httpx.MockTransport(site),
        resolver=lambda host: False,
        sleep=fake_sleep,
        retries=0,
        user_agent=UA,
        accept="text/html,*/*",
    )
    cfg = CrawlConfig(user_agent=UA, menus=tuple(menus))
    return KorailWebCrawler(
        client,
        cfg,
        tmp_path / "korail_web",
        today=lambda: today,
        sleep=fake_sleep,
        pdf_probe=pdf_probe,
    )


PRESS = MenuSpec(
    id="press",
    path="홍보센터 > 홍보 > 보도자료",
    kind="board",
    key="911",
    bbs_no="199",
    doc_type="korail_news",
    attachment_images=False,
)
VALUE = MenuSpec(
    id="mgmt_value", path="공사소개 > 일반현황 > 경영가치체계", kind="contents", key="716"
)


async def test_user_agent_and_spacing_are_applied(tmp_path):
    site = Site()
    seen_agents = []
    inner = site

    def spy(request: httpx.Request) -> httpx.Response:
        seen_agents.append(request.headers.get("user-agent"))
        return inner(request)

    site_spy = Site()
    site_spy.__call__ = spy  # type: ignore[method-assign]
    crawler = make(tmp_path, site, [VALUE])
    crawler.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(spy), headers={"User-Agent": UA, "Accept": "text/html"}
    )
    crawler.client.min_interval = 2.0
    ticks = iter([0.0, 0.0, 0.5, 0.5, 2.6, 2.6, 2.6, 2.6, 10.0, 10.0, 10.0, 10.0])
    crawler.client._clock = lambda: next(ticks, 100.0)
    sleeps: list[float] = []

    async def fake_sleep(sec):
        sleeps.append(sec)

    crawler.client._sleep = fake_sleep
    report = await crawler.download()
    assert set(seen_agents) == {UA}
    assert report.items == {"mgmt_value": 1}
    assert any(s > 0 for s in sleeps), "같은 호스트 연속 요청 사이에 2초 간격을 기다려야 한다"


async def test_robots_disallow_blocks_board_but_not_contents(tmp_path):
    site = Site()
    site.robots = (FIX / "robots_disallow.txt").read_text()
    crawler = make(tmp_path, site, [PRESS, VALUE])
    report = await crawler.download()
    assert report.items["press"] == 0 and report.items["mgmt_value"] == 1
    assert report.held == [] and not any("selectBbsNttList" in u for u in site.requests)


async def test_download_writes_manifest_text_files_and_skips_photo_attachments(tmp_path):
    site = Site()
    crawler = make(tmp_path, site, [PRESS, VALUE])
    report = await crawler.download()
    snap = SnapshotDir(tmp_path / "korail_web", "2026-10-27")
    items = read_manifest(snap)
    assert report.items == {"press": 10, "mgmt_value": 1}
    rec = (
        items["bbs:199:27436"]
        if "bbs:199:27436" in items
        else next(r for r in items.values() if r["menu"] == "press")
    )
    assert rec["doc_type"] == "korail_news" and rec["menu_path"] == PRESS.path
    assert rec["posted"] == "2026-10-22" and rec["terms"].startswith("공공누리 제4유형")
    assert (snap.path / rec["text_file"]).read_text(encoding="utf-8").startswith("“운전은 쉬고")
    hwp = next(a for a in rec["attachments"] if a["ext"] == "hwp")
    assert (
        hwp["downloaded"]
        and hwp["bytes"] == len(HWP)
        and (snap.path / hwp["path"]).read_bytes() == HWP
    )
    assert hwp["served_name"] == "261022 x.hwp"
    photo = next(a for a in rec["attachments"] if a["ext"] == "jpg")
    assert photo["downloaded"] is False and photo["reason"] == "policy_images"
    # 같은 첨부(같은 URL)는 10개 게시글이 모두 가리켜도 한 번만 받는다
    assert sum(1 for u in site.requests if "atchmnflNo=28822" in u) == 1
    assert report.files == 1 and report.skipped_files["policy_images"] == 10
    value = items["contents:716"]
    assert value["images"][0]["downloaded"] and value["images"][0]["width"] == 200
    assert report.images == 1
    index = load_index(tmp_path / "korail_web")
    assert any(v["sha256"] == hwp["sha256"] for v in index.values())
    summary = json.loads((snap.path / "snapshot.json").read_text(encoding="utf-8"))
    assert summary["snapshot"] == "2026-10-27" and summary["user_agent"] == UA


async def test_since_cuts_old_posts(tmp_path):
    site = Site()
    menu = MenuSpec(**{**PRESS.__dict__, "since": "2026-10-16"})
    crawler = make(tmp_path, site, [menu])
    report = await crawler.download()
    assert report.items["press"] == 6  # 2026-10-16 이후 게시글만
    assert not any("pageIndex=2" in u for u in site.requests)


async def test_backoff_then_hold_and_retry_at_end(tmp_path):
    site = Site()
    site.fail["/info/contents.do"] = [429, 503, 429, 200]  # 3연속 실패 → 보류 → 끝에 재시도 성공
    sleeps: list[float] = []
    crawler = make(tmp_path, site, [VALUE], sleeps=sleeps)
    report = await crawler.download()
    assert sleeps[:2] == [2.0, 5.0] and 10.0 in sleeps
    assert report.held == [] and report.items["mgmt_value"] == 1


async def test_hold_remains_when_retry_fails(tmp_path):
    site = Site()
    site.fail["/info/contents.do"] = [403, 403, 403, 403, 403, 403]
    crawler = make(tmp_path, site, [VALUE])
    report = await crawler.download()
    assert report.held == ["https://info.korail.com/info/contents.do?key=716"]
    assert report.items["mgmt_value"] == 0


async def test_incremental_carries_unchanged_marks_removed_and_never_deletes(tmp_path):
    site = Site()
    first = make(tmp_path, site, [PRESS], today=date(2026, 10, 27))
    await first.download()
    views_first = sum(1 for u in site.requests if "selectBbsNttView" in u)
    assert views_first == 10
    # 다음 날: 목록에서 한 게시글이 사라지고 나머지는 그대로
    html = _fx("board_list_press.html")
    site.list_pages = {
        1: html.replace("nttNo=27408", "nttNo=99999")
    }  # 27408 → 사라짐, 99999 → 새 글
    second = make(tmp_path, site, [PRESS], today=date(2026, 10, 28))
    report = await second.download(incremental=True)
    assert report.carried["press"] == 9 and report.items["press"] == 10
    assert sum(1 for u in site.requests if "selectBbsNttView" in u) == views_first + 1
    assert report.removed == 1
    new = read_manifest(SnapshotDir(tmp_path / "korail_web", "2026-10-28"))
    gone = new["bbs:199:27408"]
    assert (
        gone["removed"] is True
        and gone["note"] == "원본 삭제됨"
        and gone["removed_noted"] == "2026-10-28"
    )
    assert (tmp_path / "korail_web" / "snapshots" / "2026-10-27" / gone["text_file"]).exists()
    assert new["bbs:199:27437"]["carried_from"] == "2026-10-27"
    assert latest_snapshot(tmp_path / "korail_web").day == "2026-10-28"


async def test_pdf_probe_flags_missing_text_layer(tmp_path):
    site = Site()

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info/downloadBbsFile.do":
            return httpx.Response(
                200,
                content=PDF,
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="scan.pdf"',
                },
            )
        return site(request)

    probes: list[Path] = []

    async def probe(path: Path):
        probes.append(path)
        return {"pages": 3, "text_chars": 5}

    crawler = make(
        tmp_path, site, [MenuSpec(**{**PRESS.__dict__, "attachment_images": True})], pdf_probe=probe
    )
    crawler.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(serve), headers={"User-Agent": UA}
    )
    report = await crawler.download()
    rec = next(iter(read_manifest(SnapshotDir(tmp_path / "korail_web", "2026-10-27")).values()))
    pdfs = [a for a in rec["attachments"] if a.get("ext") == "pdf"]
    assert pdfs and pdfs[0]["text_layer"] is False and pdfs[0]["pages"] == 3
    assert len(probes) == 1  # 같은 내용(sha256)은 한 번만 probe
    assert report.files == 2  # URL 은 둘(사진·문서 자리) — 내용이 같아 디스크에는 한 파일
    files = list((tmp_path / "korail_web" / "snapshots" / "2026-10-27" / "files").rglob("*.pdf"))
    assert len(files) == 1


async def test_attachment_without_extension_is_typed_by_served_name(tmp_path):
    """링크 글자가 '다운로드' 뿐인 첨부 — 받은 뒤 Content-Disposition 으로 형식을 정한다."""
    site = Site()
    site.contents_html = (
        '<html><head><title>A>B - 한국철도공사</title></head><body><div id="container">'
        '<div id="contents"><p>본문 ' + "가" * 100 + "</p>"
        '<a href="/downloadContentsFile.do?key=2973&fileNo=1">다운로드</a>'
        '<a href="/downloadContentsFile.do?key=2973&fileNo=2">다운로드</a>'
        "</div></div></body></html>"
    )

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/downloadContentsFile.do":
            if request.url.params.get("fileNo") == "1":
                return httpx.Response(
                    200,
                    content=HWP,
                    headers={
                        "content-type": "application/octer-stream",
                        "content-disposition": 'attachment;filename="guide.hwp"',
                    },
                )
            return httpx.Response(
                200,
                content=b"PK\x03\x04zip",
                headers={
                    "content-type": "application/octer-stream",
                    "content-disposition": 'attachment;filename="all.zip"',
                },
            )
        return site(request)

    crawler = make(tmp_path, site, [VALUE])
    crawler.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(serve), headers={"User-Agent": UA}
    )
    report = await crawler.download()
    rec = read_manifest(SnapshotDir(tmp_path / "korail_web", "2026-10-27"))["contents:716"]
    hwp, zipped = rec["attachments"]
    assert hwp["downloaded"] and hwp["ext"] == "hwp" and hwp["served_name"] == "guide.hwp"
    assert (
        zipped["downloaded"] is False and zipped["reason"] == "type"
    )  # zip 은 받지 않는다 (보안 B)
    assert report.files == 1


async def test_explore_reports_counts_dates_and_kinds(tmp_path):
    site = Site()
    crawler = make(tmp_path, site, [PRESS, VALUE])
    result = await crawler.explore()
    press = next(m for m in result["menus"] if m["id"] == "press")
    assert press["posts"] == 6380 and press["pages"] == 638 and press["latest"] == "2026-10-23"
    assert press["attachment_kinds_page1"]["hwp"] >= 1
    value = next(m for m in result["menus"] if m["id"] == "mgmt_value")
    assert value["posts"] == 1 and value["images"] == 1 and value["chars"] > 100
    assert result["robots_empty"] is True


def test_menu_spec_rejects_unknown_kind():
    with pytest.raises(ValueError):
        MenuSpec.from_config({"id": "x", "key": "1", "kind": "rss"})
