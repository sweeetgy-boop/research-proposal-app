"""MCP 쓰기 도구·CLI 명령 — ④ 버전·비교·복원, ⑤ 최종 검토, ③ 보강 질문 (가짜 검토 LLM)."""

from __future__ import annotations

import json

import pytest

from rra.entrypoints import cli
from rra.entrypoints.mcp.run_tools import RraRunTools, ToolInputError
from tests.application.test_review_manager import REQ, build, review_reply


async def _reviewed_run():
    mgr, store, log = build(
        review_answers=[review_reply(), review_reply("최종 수정안임."), review_reply("다시 받음.")]
    )
    st = await mgr.submit("local", REQ)
    st = await mgr.wait("local", st.run_id)
    assert st.status == "drafted" and st.draft_version == 2

    async def _aclose():  # CLI 는 끝에 llm.aclose() 를 부른다
        return None

    mgr.generate.llm.aclose = _aclose
    return mgr, store, st.run_id


async def test_mcp_versions_diff_restore_and_final_review_tools():
    mgr, store, rid = await _reviewed_run()
    tools = RraRunTools(mgr, "local")
    versions = await tools.versions(rid)
    assert [v["version"] for v in versions["versions"]] == [1, 2]
    assert versions["versions"][1]["origin_label"] == "Argon 보완"
    diff = await tools.diff(rid, 1, 2)
    assert [d["section"] for d in diff["sections"]] == ["method"] and "지시가 아닙니다" in diff[
        "notice"
    ]
    with pytest.raises(ToolInputError, match="v9"):
        await tools.diff(rid, 1, 9)
    restored = await tools.restore(rid, 1)
    assert (
        restored["version"] == 3
        and restored["origin"] == "revert"
        and restored["status"] == "editing"
    )
    out = await tools.final_review(rid)
    assert out["status"] == "final_reviewing" and "rra_get_final_review" in out["hint"]
    await mgr.wait("local", rid)
    final = await tools.get_final_review(rid)
    assert final["kind"] == "final" and final["final_round"] == 1 and final["draft_version"] == 3
    assert (await tools.get_final_review(rid, 1))["round"] == 2
    with pytest.raises(ToolInputError, match="없습니다"):
        await tools.get_final_review(rid, 5)
    assert (await tools.get_review(rid))["kind"] == "final"  # 최신 차수
    q = await tools.clarify(
        **REQ.model_dump(include={"current_state", "root_cause", "limitation", "goal"})
    )
    assert q == {"questions": [], "skip_allowed": True}  # 보강 질문 유스케이스 없음 → 0개


async def test_mcp_review_tool_is_draft_review_only_once_and_edit_uses_new_origins():
    mgr, store, rid = await _reviewed_run()
    tools = RraRunTools(mgr, "local")
    with pytest.raises(ToolInputError, match="한 번만"):
        await tools.review(rid)
    edited = await tools.edit(
        rid,
        {
            "sentences": [
                {"sentence_id": "s:method:0", "action": "manual", "text": "직접 고침."},
                {"sentence_id": "s:method:0", "action": "insert_after", "text": "덧붙임."},
            ],
            "note": "메모",
            "base_version": 2,
        },
    )
    assert edited["version"] == 3 and edited["note"] == "메모"
    sentences = edited["sections"][2]["sentences"]
    assert [s["origin"] for s in sentences[:2]] == ["proposer_edit", "proposer_input"]
    with pytest.raises(ToolInputError, match="v3"):
        await tools.edit(
            rid,
            {
                "sentences": [{"sentence_id": "s:title:0", "action": "manual", "text": "x"}],
                "base_version": 2,
            },
        )


@pytest.fixture
def flow_env(monkeypatch):
    holder: dict = {}

    def fake_build(settings=None, **kw):
        return holder["mgr"]

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_run_manager", fake_build)
    return holder


def test_cli_diff_restore_and_final_review_commands(flow_env, capsys):
    import asyncio

    mgr, store, rid = asyncio.run(_reviewed_run())  # CLI 는 자기 이벤트 루프(asyncio.run)를 쓴다
    flow_env["mgr"] = mgr
    assert cli.main(["runs", "versions", rid]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert " v1   로컬 생성" in out and " v2   Argon 보완" in out
    assert cli.main(["runs", "diff", rid, "--from", "v1", "--to", "v2"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "v1 → v2: 바뀐 섹션 1" in out and "+ 이력을 분석해 보수 우선순위를 정함." in out
    assert cli.main(["runs", "diff", rid, "--from", "a", "--to", "v2"]) == cli.EXIT_USAGE
    assert cli.main(["runs", "restore", rid, "--to", "v1"]) == cli.EXIT_OK
    assert "v1 → v3 저장" in capsys.readouterr().out
    assert cli.main(["runs", "final-review", rid, "--apply-passed"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "최종 검토 1회" in out and "[채점] 필요성 3/5 (+0 vs 1차)" in out
    assert "→ 통과 수정안 반영: v4 저장" in out
    assert store.load_version("local", rid, 4).origin == "final_review"
    assert cli.main(["runs", "final-review", rid, "--wait", "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "final" and payload["final_round"] == 2
    assert cli.main(["runs", "outline", rid]) == cli.EXIT_OK
    assert "설계도가 없습니다" in capsys.readouterr().out


def test_cli_clarify_without_pipeline_step_reports_no_questions(monkeypatch, capsys):
    from rra.domain.models import PipelineConfig

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.pipeline_config", lambda s: PipelineConfig())
    args = ["--current-state", "a", "--root-cause", "b", "--limitation", "c", "--goal", "d"]
    assert cli.main(["clarify", *args]) == cli.EXIT_OK
    assert "보강 질문 없음" in capsys.readouterr().out
    assert cli.main(["clarify", *args, "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out) == {"questions": [], "skip_allowed": True}
    assert cli.main(["clarify", "--goal", "x"]) == cli.EXIT_USAGE
