"""CLI U2 structure · U4 compare · U5 brief · U7 runs submit-check · U8 usage report.

composition 을 monkeypatch 해 모델·DB 없이 배선만 검증한다."""

from __future__ import annotations

import json

from rra.domain.models import OverlapAlert, UsageRecord
from rra.domain.models.comparison import ComparisonColumn, ComparisonTable
from rra.domain.models.usage import Satisfaction
from rra.entrypoints import cli
from tests.application.test_review_manager import REQ, build, run
from tests.entrypoints.test_cli import SLOT_ARGS


class _NoLLM:
    async def aclose(self):
        return None


class StubStructure:
    llm = _NoLLM()

    async def __call__(self, text, *, title=""):
        from rra.domain.rules.structure import structured

        return structured({"current_state": text})


def test_structure_prints_fields_and_questions(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_structurer", lambda *a, **k: StubStructure())
    assert cli.main(["structure", "--text", "궤도 틀림이 잦음"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "현재 상황·문제: 궤도 틀림이 잦음" in out and "보완 질문" in out and "[발생 원인]" in out
    assert cli.main(["structure", "--text", "궤도 틀림이 잦음", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["questions"][0]["field"] == "root_cause"
    monkeypatch.setattr("rra.composition.build_structurer", lambda *a, **k: None)
    assert cli.main(["structure", "--text", "x"]) == cli.EXIT_USAGE


class StubCompare:
    async def __call__(self, req, alerts=None):
        return ComparisonTable(
            proposal=ComparisonColumn(
                title=req.title_hint,
                cells={"objective": req.goal, "differentiation": req.differentiation},
            ),
            projects=[
                ComparisonColumn(
                    doc_id="alio:1", title="과제", cells={"objective": "정보 없음(제목 기준)"}
                )
            ],
        )


def test_compare_prints_table(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_precheck", lambda *a, **k: object())
    monkeypatch.setattr("rra.composition.build_comparer", lambda *a, **k: StubCompare())
    assert cli.main(["compare", *SLOT_ARGS, "--differentiation", "범위 확장"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "[차별성 비교표] 유사과제 1건" in out
        and "정보 없음(제목 기준)" in out
        and "범위 확장" in out
    )
    assert cli.main(["compare", "--json"]) == cli.EXIT_USAGE  # 필수 슬롯 없음


class StubBrief:
    llm = _NoLLM()

    async def __call__(self, req):
        from rra.domain.models import BriefItem, GapCandidate, PriorWorkBrief

        return PriorWorkBrief(
            items=[
                BriefItem(
                    doc_id="openalex:W1",
                    chunk_id="openalex:W1#0",
                    title="Track",
                    source="openalex",
                    year=2023,
                    summary="열화율 보고함.",
                )
            ],
            years={"2023": 1},
            keywords=["궤도"],
            gaps=[GapCandidate(text="재래선 자료 없음.", evidence=["openalex:W1#0"])],
            provider="gemini",
            model="argon",
            calls=1,
        )


def test_brief_prints_items_years_gaps(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_briefer", lambda *a, **k: StubBrief())
    assert cli.main(["brief", *SLOT_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[선행연구 브리핑] 1건 (gemini/argon)" in out and "2023 1건" in out
    assert "연구 공백 후보" in out and "재래선 자료 없음." in out and "priority-evidence" in out


def test_submit_check_and_usage_report_cli(monkeypatch, capsys):
    import asyncio

    async def _prepare():
        mgr, store, _ = build()
        st = await run(mgr)

        async def _aclose():
            return None

        mgr.generate.llm.aclose = _aclose
        return mgr, store, st

    mgr, store, st = asyncio.run(_prepare())  # CLI 는 자기 이벤트 루프(asyncio.run)를 쓴다
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_run_manager", lambda *a, **k: mgr)
    assert cli.main(["runs", "submit-check", st.run_id]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "[제출 전 점검] 확인 필요" in out and "선택형 확정" in out and "→ section:task_type" in out
    )
    assert cli.main(["runs", "submit-check", st.run_id, "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["ok"] is False

    from rra.application.usecases.usage_report import UsageReport

    store.save_usage(
        "local",
        st.run_id,
        UsageRecord(
            run_id=st.run_id,
            rewrites=2,
            hwpx_success=True,
            satisfaction=Satisfaction(score=4),
            total_seconds=30,
        ),
    )
    monkeypatch.setattr("rra.composition.build_usage_report", lambda *a, **k: UsageReport(store))
    assert cli.main(["usage", "report"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "run 1건" in out and "AI 다시 쓰기 반영: 2회" in out and "평균 4.0" in out
    assert cli.main(["usage", "report", "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["hwpx_success"] == 1


def test_usage_report_empty(monkeypatch, capsys):
    from rra.application.usecases.usage_report import UsageReport
    from tests.fakes import InMemoryRunStore

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_usage_report", lambda *a, **k: UsageReport(InMemoryRunStore())
    )
    assert cli.main(["usage", "report"]) == cli.EXIT_OK
    assert "기록된 run 이 없습니다" in capsys.readouterr().out


def test_alert_model_still_used_by_cli_tests():
    assert (
        OverlapAlert(doc_id="a:1", title="t", tier="own", similarity=0.9, blocking=False).keywords
        == []
    )
    assert REQ.goal == "예측"
