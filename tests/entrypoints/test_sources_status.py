"""GET /v1/sources/status 의 공사 홈페이지 스냅샷 표시 + `rra sources status`."""

import httpx

from rra.entrypoints.cli import main
from tests.entrypoints.test_api import AUTH, build


async def test_sources_status_carries_korail_web_snapshot_label(monkeypatch):
    import rra.entrypoints.api.app as app_module

    original = app_module.create_app

    def with_snapshot(**kw):
        return original(
            **kw, snapshot_status=lambda: {"snapshot": "2026-10-27", "items": 61, "removed": 0}
        )

    monkeypatch.setattr("tests.entrypoints.test_api.create_app", with_snapshot)
    app, _ = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        rows = {
            s["source"]: s
            for s in (await c.get("/v1/sources/status", headers=AUTH)).json()["sources"]
        }
    row = rows["korail_web"]
    assert row["label"] == "공사 홈페이지 정책·보도자료" and row["count"] == 0
    assert row["snapshot"] == "2026-10-27" and row["snapshot_items"] == 61
    assert row["snapshot_label"] == "공사 홈페이지 자료: 2026-10-27 기준 스냅샷"
    assert "snapshot" not in rows["alio"]


def test_cli_sources_status_prints_snapshot_line(monkeypatch, capsys):
    class Repo:
        async def source_status(self):
            return {"alio": {"count": 3, "last_ingested": "2026-10-26"}}

    class Src:
        def status(self):
            return {"snapshot": "2026-10-27", "items": 61, "removed": 2}

    monkeypatch.setattr("rra.composition.build_embedding", lambda settings: None)
    monkeypatch.setattr("rra.composition.build_repository", lambda emb, settings: Repo())
    monkeypatch.setattr("rra.composition.build_korail_web_source", lambda settings: Src())
    assert main(["sources", "status"]) == 0
    out = capsys.readouterr().out
    assert "알리오 공시 연구보고서: 3건, 최근 적재 2026-10-26" in out
    assert "공사 홈페이지 자료: 2026-10-27 기준 스냅샷 (항목 61건, 삭제 표시 2)" in out
