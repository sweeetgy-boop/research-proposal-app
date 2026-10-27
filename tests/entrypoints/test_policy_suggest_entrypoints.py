"""POST /v1/ideas/policy-suggestions · rra policy-suggest — 제안자가 고를 목록만 준다."""

import json

import httpx

from rra.domain.models import PolicySuggestion
from rra.entrypoints.cli import main
from tests.entrypoints.test_api import AUTH, SLOTS, build

SUGGESTION = PolicySuggestion(
    doc_id="korail_web:p1",
    title="중장기 경영목표",
    year=2026,
    page="표 전략과제",
    quote="데이터기반 유지보수 첨단화",
    url="https://info.korail.com/info/contents.do?key=1900",
    keywords=["유지보수"],
    similarity=0.8,
)


class _Suggest:
    def __init__(self):
        self.calls = []

    async def __call__(self, req):
        self.calls.append(req)
        return [SUGGESTION]


async def test_rest_policy_suggestions(monkeypatch):
    import tests.entrypoints.test_api as harness

    original = harness.create_app
    suggest = _Suggest()
    monkeypatch.setattr(harness, "create_app", lambda **kw: original(**kw, policy_suggest=suggest))
    app, _ = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        r = await c.post("/v1/ideas/policy-suggestions", json=SLOTS, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1 and body["notice"]
        row = body["suggestions"][0]
        assert (
            row["title"] == "중장기 경영목표"
            and row["year"] == 2026
            and row["keywords"] == ["유지보수"]
        )
        assert row["policy_basis_text"].startswith(
            "“데이터기반 유지보수 첨단화” (중장기 경영목표, 2026, 표 전략과제"
        )
        assert suggest.calls[0].goal == SLOTS["goal"]
        r = await c.post("/v1/ideas/policy-suggestions", json={"goal": "x"}, headers=AUTH)
        assert r.status_code == 422


async def test_rest_policy_suggestions_disabled_is_503():
    app, _ = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        assert (
            await c.post("/v1/ideas/policy-suggestions", json=SLOTS, headers=AUTH)
        ).status_code == 503


def test_cli_policy_suggest_lists_and_pick_merges(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.build_policy_suggest", lambda settings: _Suggest())
    args = ["policy-suggest"] + [f"--{k.replace('_', '-')}={v}" for k, v in SLOTS.items()]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "1. 중장기 경영목표 (2026, 표 전략과제)" in out and "--pick N" in out
    assert main([*args, "--pick", "1", "--policy-basis", "기존"]) == 0
    merged = json.loads(capsys.readouterr().out)
    assert merged["policy_basis"].startswith("기존\n“데이터기반 유지보수 첨단화”")
    assert main([*args, "--pick", "9"]) == 2
