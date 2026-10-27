"""POST /v1/ideas/notices · rra notices match · rra crawl rnd-notice · sources status 행."""

import json
from datetime import date

import httpx

from rra.composition import SOURCE_NAMES
from rra.domain.models import NoticeMatch
from rra.domain.rules.overlap import NON_OVERLAP_SOURCES, SOURCE_LABELS
from rra.entrypoints.cli import main
from tests.entrypoints.test_api import AUTH, SLOTS, build

MATCH = NoticeMatch(
    doc_id="rnd_notice:abc",
    title="2026년 국토교통연구기획 사업 제2차 시행 공고",
    agency="국토교통과학기술진흥원",
    program="국토교통연구기획",
    posted=date(2026, 7, 16),
    deadline=date(2026, 11, 18),
    days_left=22,
    url="https://www.kaia.re.kr/KAIA/contents/K30101000000.do?schM=view&id=1",
    similarity=0.83,
)


class _Match:
    def __init__(self):
        self.calls = []

    async def __call__(self, req):
        self.calls.append(req)
        return [MATCH]


def test_source_registered_with_label_and_excluded_from_overlap():
    assert "rnd_notice" in SOURCE_NAMES and "rnd_notice" in NON_OVERLAP_SOURCES
    assert SOURCE_LABELS["rnd_notice"] == "국토교통 R&D 사업공고(KAIA·IRIS)"


async def test_rest_notices(monkeypatch):
    import tests.entrypoints.test_api as harness

    original = harness.create_app
    match = _Match()
    monkeypatch.setattr(
        harness,
        "create_app",
        lambda **kw: original(
            **kw,
            notice_match=match,
            notice_snapshot_status=lambda: {"snapshot": "2026-10-27", "items": 120},
        ),
    )
    app, _ = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        r = await c.post("/v1/ideas/notices", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1 and body["notice"]
        item = body["items"][0]
        assert item["deadline"] == "2026-11-18" and item["days_left"] == 22
        assert item["agency"] == "국토교통과학기술진흥원" and item["similarity"] == 0.83
        assert match.calls[0].goal == SLOTS["goal"]
        assert (
            await c.post("/v1/ideas/notices", json={"goal": "x"}, headers=AUTH)
        ).status_code == 422
        rows = {
            s["source"]: s
            for s in (await c.get("/v1/sources/status", headers=AUTH)).json()["sources"]
        }
        assert rows["rnd_notice"]["snapshot_label"] == "정부 R&D 공고: 2026-10-27 기준 스냅샷"
        assert rows["rnd_notice"]["snapshot_items"] == 120 and "snapshot" not in rows["alio"]


async def test_rest_notices_disabled_is_503():
    app, _ = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        assert (await c.post("/v1/ideas/notices", json=SLOTS, headers=AUTH)).status_code == 503


def test_cli_notices_match(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.build_notice_match", lambda settings: _Match())
    args = ["notices", "match"] + [f"--{k.replace('_', '-')}={v}" for k, v in SLOTS.items()]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert (
        "1. 2026년 국토교통연구기획 사업 제2차 시행 공고 — 국토교통과학기술진흥원, "
        "마감 2026-11-18 (D-22" in out
    )
    assert main([*args, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["doc_id"] == "rnd_notice:abc"
    assert main(["notices", "match", "--goal", "x"]) == 2


def test_cli_crawl_rnd_notice_explore_and_download(monkeypatch, capsys):
    from rra.adapters.sources.rnd_notice.crawler import CrawlReport

    class Crawler:
        async def explore(self):
            return {
                "date": "2026-10-27",
                "since": "2024-10-28",
                "sites": [
                    {
                        "site": "kaia",
                        "base_url": "https://www.kaia.re.kr",
                        "robots": "allowed",
                        "total": 1224,
                        "sample": ["a"],
                    }
                ],
            }

        async def download(self, *, limit=None, incremental=False):
            return CrawlReport(
                snapshot="2026-10-27", since="2024-10-28", notices={"kaia": 3}, files=2, bytes=2048
            )

        async def aclose(self):
            return None

    monkeypatch.setattr("rra.composition.build_rnd_notice_crawler", lambda settings: Crawler())
    assert main(["crawl", "rnd-notice", "--explore"]) == 0
    assert "kaia (https://www.kaia.re.kr): robots allowed, 전체 1224" in capsys.readouterr().out
    assert main(["crawl", "rnd-notice", "--download", "--limit", "3"]) == 0
    assert "공고 3건 {'kaia': 3}" in capsys.readouterr().out


def test_cli_sources_status_prints_notice_snapshot_line(monkeypatch, capsys):
    class Repo:
        async def source_status(self):
            return {}

    monkeypatch.setattr("rra.composition.build_repository", lambda emb, settings: Repo())
    monkeypatch.setattr("rra.composition.build_embedding", lambda settings: None)
    monkeypatch.setattr(
        "rra.composition.build_korail_web_source",
        lambda settings: type("S", (), {"status": lambda self: {"snapshot": None}})(),
    )
    monkeypatch.setattr(
        "rra.composition.build_rnd_notice_source",
        lambda settings: type(
            "S",
            (),
            {"status": lambda self: {"snapshot": "2026-10-27", "items": 120, "duplicates": 4}},
        )(),
    )
    assert main(["sources", "status"]) == 0
    out = capsys.readouterr().out
    assert "- 국토교통 R&D 사업공고(KAIA·IRIS): 0건" in out
    assert "정부 R&D 공고: 2026-10-27 기준 스냅샷 (공고 120건, 중복 합침 4)" in out
