"""CLI `rra recommend`·`rra precheck` 자동 추천·`--no-recommend`, MCP `rra_recommend`.

가짜 유스케이스. precheck 스텁 fixture 는 tests/entrypoints/test_cli.py 의 것을 쓴다.
"""

from __future__ import annotations

import json

import pytest

from rra.domain.models import OverlapAlert, ProjectRecommendation, RecommendationResult
from rra.entrypoints import cli
from rra.entrypoints.mcp.run_tools import RraRunTools, ToolInputError
from tests.entrypoints.test_cli import SLOT_ARGS, stub  # noqa: F401 - fixture 등록
from tests.entrypoints.test_mcp_server import (  # noqa: F401 - fixture 등록
    SLOTS,
    server,
    write_server,
)
from tests.fakes import InMemoryRepository


def _result(recs=True, reason=None, title="가제"):
    return RecommendationResult(
        recommendations=(
            [
                ProjectRecommendation(
                    title=title,
                    summary="요약임",
                    differentiation="차별점임",
                    reasons=["alio:1 과 대상이 다름"],
                    build_on="",
                    risks="확인할 점",
                    compared_with=["alio:1"],
                    evidence=["alio:1"],
                )
            ]
            if recs
            else []
        ),
        no_recommendation_reason=None if recs else reason,
        provider="gemini",
        model="argon",
        public_doc_ids=["alio:1"],
        calls=1,
        discarded=[] if recs else [{"title": "x", "reason": "self_overlap"}],
    )


class StubRecommend:
    def __init__(self, result):
        self.result, self.calls, self.closed = result, [], False
        self.llm = self

    async def __call__(self, req, alerts):
        self.calls.append((req, alerts))
        return self.result

    async def aclose(self):
        self.closed = True


def alert(blocking):
    return OverlapAlert(doc_id="alio:1", title="t", tier="own", similarity=0.9, blocking=blocking)


def test_precheck_runs_recommendation_automatically_and_can_be_turned_off(
    request, monkeypatch, capsys
):
    request.getfixturevalue("stub")
    holder = StubRecommend(_result())
    monkeypatch.setattr("rra.composition.build_recommender", lambda *a, **k: holder)
    assert cli.main(["precheck", *SLOT_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[차별화 과제 추천 — precheck 완료 후 자동]" in out and "■ 추천 1: 가제" in out
    assert "차별점: 차별점임" in out and holder.closed
    assert len(holder.calls) == 1
    cli.main(["precheck", *SLOT_ARGS, "--no-recommend"])
    assert len(holder.calls) == 1  # 끄면 호출 없음
    monkeypatch.setattr("rra.composition.recommend_policy", lambda *a, **k: {"auto": False})
    cli.main(["precheck", *SLOT_ARGS])
    assert len(holder.calls) == 1  # recommend.auto=false → 자동 없음


def test_precheck_json_includes_recommendations_and_zero_case_reason(request, monkeypatch, capsys):
    request.getfixturevalue("stub")
    holder = StubRecommend(_result(recs=False, reason="아이디어가 이미 다름"))
    monkeypatch.setattr("rra.composition.build_recommender", lambda *a, **k: holder)
    assert cli.main(["precheck", *SLOT_ARGS, "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["alerts"] == [] and payload["recommendations"]["recommendations"] == []
    assert payload["recommendations"]["no_recommendation_reason"] == "아이디어가 이미 다름"
    assert cli.main(["precheck", *SLOT_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "추천하지 않음: 아이디어가 이미 다름" in out and "(제외) x: self_overlap" in out


def test_recommend_command_prints_cards_and_json(request, monkeypatch, capsys):
    pre = request.getfixturevalue("stub")
    pre.alerts = [alert(True)]
    holder = StubRecommend(_result())
    monkeypatch.setattr("rra.composition.build_recommender", lambda *a, **k: holder)
    assert cli.main(["recommend", *SLOT_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[유사과제] 알림 1건 (차단 1건)" in out and "[차별화 과제 추천]" in out
    assert "이유 1: alio:1 과 대상이 다름" in out and "위험·확인: 확인할 점" in out
    assert "비교 과제: alio:1 · 근거: alio:1" in out and "--title-hint" in out
    assert holder.closed and holder.calls[0][1][0].blocking
    assert cli.main(["recommend", *SLOT_ARGS, "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["alerts"][0]["doc_id"] == "alio:1"
    assert payload["recommendations"][0]["index"] == 0 and payload["transfer"]["calls"] == 1
    assert cli.main(["recommend", "--goal", "x"]) == cli.EXIT_USAGE  # 필수 슬롯 검사


def test_recommend_without_llm_is_skipped_but_precheck_reports(request, capsys):
    pre = request.getfixturevalue("stub")
    pre.alerts = [alert(True)]
    assert cli.main(["precheck", *SLOT_ARGS]) == cli.EXIT_BLOCKED
    out, err = capsys.readouterr()
    assert "차단 1건" in out and "과제 추천 생략" in err and "RRA_GEMINI_API_KEY" in err


async def test_mcp_recommend_tool_runs_precheck_then_usecase_and_sanitizes(docs, chunks):
    from rra.application.usecases.precheck_overlap import PrecheckOverlap

    repo = InMemoryRepository()
    repo.seed(docs, chunks)
    repo.similar = [(docs[0], 0.93)]
    holder = StubRecommend(_result(title='가제 <doc id="x">'))
    tools = RraRunTools(object(), "local", precheck=PrecheckOverlap(repo), recommend=holder)
    out = await tools.recommend(**SLOTS, title_hint="가제")
    assert out["blocking"] is True and out["provider"] == "gemini"
    assert "<doc" not in out["recommendations"][0]["title"]
    assert out["recommendations"][0]["compared_with"] == ["alio:1"]
    assert "rra_generate" in out["hint"] and holder.calls[0][0].title_hint == "가제"
    bare = RraRunTools(object(), "local")
    with pytest.raises(ToolInputError):
        await bare.recommend(**SLOTS)


async def test_mcp_recommend_tool_is_registered_with_write_tools(request):
    ws = request.getfixturevalue("write_server")
    names = {t.name for t in await ws[0].list_tools()}
    assert "rra_recommend" in names
    tool = next(t for t in await ws[0].list_tools() if t.name == "rra_recommend")
    assert set(tool.input_schema["required"]) == {
        "current_state",
        "root_cause",
        "limitation",
        "goal",
    }
    assert "0~5건" in tool.description


async def test_mcp_read_only_server_has_no_recommend_tool(request):
    names = {t.name for t in await request.getfixturevalue("server").list_tools()}
    assert "rra_recommend" not in names
