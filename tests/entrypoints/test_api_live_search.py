"""[4] REST 실시간 자료 검색 — 가짜 모드(RRA_FAKE_LLM=1, 가짜 자료원·메모리 저장소, 네트워크 없음).

POST /v1/precheck 의 live_search 요약·알림/관련 연구의 live, run 상태의 live_search,
초안 인용·근거의 live, 꺼짐(off) 은 종전 동작. 가짜 모드는 live_search.yaml fake_mode 로만 켠다.
"""

from __future__ import annotations

import asyncio

import httpx
from pydantic import SecretStr

from rra.domain.models.live_search import LiveSearchConfig
from rra.settings import Settings

TOKEN = "api-live-token"  # noqa: S105 — 테스트용
AUTH = {"Authorization": f"Bearer {TOKEN}"}
REQ = {
    "title_hint": "궤도 상태 실시간 감지",
    "current_state": "궤도 틀림 반복",
    "root_cause": "노반 침하",
    "limitation": "임계치만 봄",
    "goal": "궤도 상태 감지 자동화",
}


def _app(tmp_path, monkeypatch=None, *, enabled=True):
    import rra.config_loader as loader
    from rra.composition import build_api

    if monkeypatch is not None:
        cfg = LiveSearchConfig(enabled=enabled, fake_mode=True)
        monkeypatch.setattr(loader, "live_search_config", lambda s: cfg)

    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never.sqlite",
        static_dir=tmp_path / "no-dist",
        data_dir=tmp_path / "data",
    )
    return build_api(settings, sse_poll_sec=0.01)


async def _wait_drafted(c, run_id):
    for _ in range(400):
        state = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()
        if state["status"] in ("drafted", "failed"):
            return state
        await asyncio.sleep(0.01)
    return state


async def test_precheck_and_run_carry_live_search(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        pre = (await c.post("/v1/precheck", json=REQ, headers=AUTH)).json()
        live = pre["live_search"]
        assert live["status"] == "done"
        assert live["keywords"]["ko"][0] == "궤도 상태 감지"  # 가짜 키워드 LLM
        assert [s["source"] for s in live["sources"]] == ["scienceon", "ntis", "openalex"]
        for row in live["sources"]:
            assert row["status"] == "ok" and row["count"] == 2
            assert {"source", "status", "count", "seconds", "notice"} <= set(row)
        alerts = {a["doc_id"]: a for a in pre["alerts"]}
        assert alerts["ntis:FAKELIVE001"]["live"] is True  # NTIS 과제 → ② 유사과제 후보
        assert all(a["live"] is False for d, a in alerts.items() if "FAKELIVE" not in d)
        related = {r["doc_id"]: r for r in pre["related_research"]}
        assert related and all(r["doc_type"] != "rnd_project" for r in related.values())
        assert any(r["live"] for r in related.values())  # 논문·보고서·특허 → 관련 연구

        r = await c.post("/v1/runs", json={**REQ, "acknowledged": True}, headers=AUTH)
        run_id = r.json()["run_id"]
        state = await _wait_drafted(c, run_id)
        assert state["live_search"]["status"] == "done"
        assert state["live_search"]["keywords"] == live["keywords"]  # 같은 입력 → 같은 세션
        draft = (await c.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
        cites = draft["citations"]
        assert cites and all("live" in x for x in cites)
        live_cites = [x for x in cites if x["live"]]
        sid = next(
            (
                f"s:{sec['key']}:{i}"
                for sec in draft["sections"]
                for i, s in enumerate(sec["sentences"])
                if s["evidence"]
            ),
            None,
        )
        if sid is not None:
            ev = (await c.get(f"/v1/runs/{run_id}/sentences/{sid}/evidence", headers=AUTH)).json()
            assert all("live" in e for e in ev["evidence"])
        assert isinstance(live_cites, list)


async def test_live_search_off_is_old_behaviour(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, enabled=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        pre = (await c.post("/v1/precheck", json=REQ, headers=AUTH)).json()
        assert pre["live_search"] == {
            "status": "off",
            "keywords": {"ko": [], "en": []},
            "sources": [],
        }
        assert not any("FAKELIVE" in a["doc_id"] for a in pre["alerts"])
        assert all(a["live"] is False for a in pre["alerts"])
        r = await c.post("/v1/runs", json={**REQ, "acknowledged": True}, headers=AUTH)
        state = await _wait_drafted(c, r.json()["run_id"])
        assert state["live_search"] is None


async def test_fake_mode_default_keeps_live_search_off(tmp_path):
    app = _app(tmp_path)  # 저장소 config/live_search.yaml — fake_mode 없음
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        pre = (await c.post("/v1/precheck", json=REQ, headers=AUTH)).json()
        assert pre["live_search"]["status"] == "off"
