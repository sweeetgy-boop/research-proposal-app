"""REST POST /v1/precheck/ntis-outcomes — 응답 모양(프론트엔드 계약)·503·비신뢰 표시."""

import httpx
import pytest

from rra.application.usecases.ntis_insights import NtisProjectInsights
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from tests.entrypoints.test_api import AUTH, TOKEN, build
from tests.entrypoints.test_api import SLOTS as REQ


class FakeOutcomes:
    async def outcomes(self, project_no):
        return [
            {
                "kind": "paper",
                "title": "논문  2023",
                "year": "2023",
                "venue": "학회지",
                "result_id": "PAP-1",
            }
        ]


class FakeRelated:
    async def related(self, project_no):
        return [{"project_no": "1415199001", "title": "새 과제", "score": 0.9, "rank": 1}]


class FakePrecheck:
    async def __call__(self, req):
        from rra.domain.models import OverlapAlert

        return [
            OverlapAlert(
                doc_id="ntis:1415171234",
                title="궤도 과제",
                tier="national_rnd",
                similarity=0.86,
                blocking=True,
            )
        ]


def make_app(insights):
    app, a = build()
    # precheck·ntis_insights 를 바꿔 끼운 앱 — create_app 인자로 직접 만든다
    from rra.adapters.security import SessionStore
    from rra.composition import api_middlewares
    from rra.entrypoints.api import create_app
    from rra.entrypoints.api.app import SessionAuth
    from rra.settings import Settings

    sessions = SessionStore()
    mws = api_middlewares(Settings(_env_file=None), TOKEN, sessions=sessions)
    return create_app(
        manager=a.manager,
        precheck=FakePrecheck(),
        repo=a.repo,
        user=a.user,
        middlewares=mws,
        session_auth=SessionAuth(TOKEN, sessions),
        ntis_insights=insights,
    )


@pytest.fixture
async def client():
    app = make_app(NtisProjectInsights(FakeOutcomes(), FakeRelated()))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        yield c


async def test_ntis_outcomes_shape(client):
    r = await client.post("/v1/precheck/ntis-outcomes", json=REQ, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notice"] == UNTRUSTED_NOTICE
    (p,) = body["projects"]
    assert p["project_no"] == "1415171234" and p["doc_id"] == "ntis:1415171234"
    assert (
        p["tier"] == "national_rnd" and p["tier_label"] == "국가R&D 과제" and p["blocking"] is True
    )
    assert p["outcomes"] == [
        {
            "kind": "paper",
            "title": "논문 2023",
            "year": "2023",
            "venue": "학회지",
            "result_id": "PAP-1",
            "registration_no": None,
        }
    ]
    assert body["ntis_recommended"] == [
        {
            "project_no": "1415199001",
            "title": "새 과제",
            "url": "https://www.ntis.go.kr/project/pjtInfo.do?pjtId=1415199001",
            "score": 0.9,
            "rank": 1,
            "source_project_no": "1415171234",
        }
    ]


async def test_ntis_outcomes_503_without_key():
    app = make_app(NtisProjectInsights(None, None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        r = await c.post("/v1/precheck/ntis-outcomes", json=REQ, headers=AUTH)
    assert r.status_code == 503


async def test_fake_mode_serves_ntis_outcomes_for_the_seeded_national_rnd_alert(tmp_path):
    """가짜 모드(RRA_FAKE_LLM=1): precheck 에 national_rnd 알림 1건 + ntis-outcomes 200 (e2e)."""
    from pydantic import SecretStr

    from rra.composition import build_api
    from rra.settings import Settings

    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never.sqlite",
        static_dir=tmp_path / "no-dist",
    )
    app = build_api(settings, sse_poll_sec=0.01)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        pre = (await c.post("/v1/precheck", json=REQ, headers=AUTH)).json()
        ntis_alerts = [a for a in pre["alerts"] if a["tier"] == "national_rnd"]
        assert [a["doc_id"] for a in ntis_alerts] == ["ntis:fake-1"]
        assert ntis_alerts[0]["tier_label"] == "국가R&D 과제"
        r = await c.post("/v1/precheck/ntis-outcomes", json=REQ, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notice"] == UNTRUSTED_NOTICE
    (p,) = body["projects"]
    assert p["doc_id"] == "ntis:fake-1" and p["tier_label"] == "국가R&D 과제"
    assert [o["kind"] for o in p["outcomes"]] == ["paper", "patent"]
    assert all("(가짜)" in o["title"] for o in p["outcomes"])
    assert [r["project_no"] for r in body["ntis_recommended"]] == ["fake-rel-1", "fake-rel-2"]
    assert all(r["url"].startswith("https://www.ntis.go.kr/") for r in body["ntis_recommended"])
