"""[5] 통합 측정(`rra eval --final-review --finalize --concurrent N`) — 가짜 LLM·저장소·렌더러만.

- ⑤ 최종 검토 점수·시간, ⑥ 마무리 HWPX 검증·그림 배치 수, 마무리 거부 기록
- 품질: 유효·빈 초안·수치 알림·근거 불일치(검토 support·local_check)
- 실시간 인용 비율(live_citations)·자료원별 합계(source_stats)
- 동시 모드: 묶음 벽시계 < 건별 생성 시간 합
- 비교표: 새 항목이 없는 예전 JSON(기준선)은 "-"
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from rra.application.usecases.evaluate import (
    EvalIdea,
    EvalResult,
    EvaluateQuality,
    live_citations,
    live_sources,
    source_stats,
)
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.review_draft import ReviewDraft
from rra.domain.models import Document
from rra.domain.rules.lint import ChoiceSpec, LintRules
from rra.entrypoints.views import eval_markdown
from tests.application.test_argon_writer import (
    FINAL_REPLY,
    CountingPool,
    KeyedLLM,
    _verdict,
    js,
    manager,
)
from tests.application.test_evaluate import FakePrecheck
from tests.application.test_run_manager_quality import REQ, build, reply
from tests.fakes import FakePromptLibrary, InMemoryRepository

KEYS3 = ["problem", "prior_work", "task_type"]
CHOICE = '{"choices": ["applied"], "sentences": [{"text": "응용임.", "evidence": []}]}'


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    live_docs = [
        d.model_copy(update={"raw": {"live": True}}) if d.doc_id == "openalex:W1" else d
        for d in docs
    ]
    r.seed(live_docs, chunks)
    return r


def gen(repo, remote, local=None, *, keys=KEYS3, **kw):
    rules = LintRules(
        template="v2026",
        sections=list(keys),
        required_sections=[k for k in keys if k != "task_type"],
        evidence_required=[],
        choices={"task_type": ChoiceSpec(options="task_types")} if "task_type" in keys else {},
        number_checked=["problem"],
    )
    return GenerateProposal(
        local or KeyedLLM(prefix="로컬 "),
        repo,
        FakePromptLibrary(),
        rules,
        list(keys),
        writer_llm=remote,
        writer_provider="gemini",
        writer_model="gemini-4-argon",
        local_provider="mlx",
        local_model="qwen-7b",
        compose_concurrency=4,
        **kw,
    )


def reviewer_for(g, answers):
    from tests.fakes import FakeLLM

    return ReviewDraft(
        FakeLLM(list(answers)), FakePromptLibrary(), g.rules, provider="gemini", model="argon"
    )


def remote_answers(**extra):
    return {
        "problem": js("궤도 점검의 42% 를 줄임."),  # 입력·근거에 없는 수치 → unsupported_number
        "prior_work": js("선행 연구가 있음.", ["openalex:W1#0", "alio:1#0"]),
        "task_type": CHOICE,
        **extra,
    }


# ── ⑤ 최종 검토 + ⑥ 마무리 ────────────────────────────────
async def test_final_review_and_finalize_are_recorded_with_quality_and_live_share(req, repo):
    g = gen(repo, KeyedLLM(remote_answers()), KeyedLLM(check=_verdict("불일치")), local_check=True)
    mgr, _ = manager(g, reviewer=reviewer_for(g, [FINAL_REPLY]), first_pass=False)
    checked: list[bytes] = []
    ev = EvaluateQuality(
        mgr,
        FakePrecheck(),
        label="C",
        pipeline={},
        final_review=True,
        finalize=True,
        verify_hwpx=lambda data: checked.append(data) or data.startswith(b"{"),
    )
    result = await ev([("01", req)])
    (a,) = result.ideas
    assert a.status == "drafted" and a.valid and a.final_status == "finalized"
    assert a.precheck_seconds is not None and a.draft_seconds is not None
    assert a.final_review_status == "done" and a.final_review_seconds is not None
    assert a.final_scores == {"필요성": 4, "차별성": 3, "실현가능성": 4, "기대효과": 4}
    assert a.final_score_avg == 3.75
    assert a.finalized and a.hwpx_ok and a.hwpx_bytes > 0 and checked
    assert a.figure_placements == 0 and a.finalize_error is None
    # 품질 — 수치 알림 1(problem), local_check 불일치 → 로컬 근거 불일치 경고
    assert a.number_alerts == 1 and not a.empty_draft and a.empty_required_sections == []
    assert a.local_check_mismatches >= 1 and a.local_evidence_mismatch >= 1
    assert a.local_check_skipped == 0 and a.review_mismatch == 0  # 최종 검토는 support 없음
    # 실시간 — 인용 문서 2개(alio:1, openalex:W1) 중 openalex:W1 만 raw.live
    assert (a.live_cited, a.cited_docs) == (1, 2)
    assert a.live_sources == {} and a.live_status is None  # 레인 C 전 run — 필드 없음
    # Gemini 단계별 — 작성 3섹션 + 최종 검토 1
    assert a.gemini_by_stage == {"compose": 3, "review": 1, "figures": 0, "total": 4}
    t = result.totals()
    assert t["valid"] == 1 and t["valid_rate"] == 1.0 and t["empty_drafts"] == 0
    assert t["final_score_avg"] == 3.75 and t["final_scores_avg"]["차별성"] == 3.0
    assert t["live_share"] == 0.5 and t["hwpx_ok"] == 1 and t["finalize_tried"] == 1
    assert t["gemini_compose"] == 3 and t["gemini_review"] == 1 and t["number_alerts"] == 1
    assert result.config["writer"] == "gemini" and result.config["local_check"] is True
    assert result.mode == "sequential" and result.batches == []
    data = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
    assert data["ideas"][0]["final_scores"]["필요성"] == 4


async def test_finalize_without_final_review_records_rejection_and_bad_hwpx(req, repo):
    g = gen(repo, KeyedLLM(remote_answers()))
    mgr, _ = manager(g, reviewer=reviewer_for(g, [FINAL_REPLY]), first_pass=False)
    ev = EvaluateQuality(mgr, FakePrecheck(), label="x", pipeline={}, finalize=True)
    (a,) = (await ev([("01", req)])).ideas
    assert a.finalized is False and a.hwpx_ok is False and a.finalize_error == "FinalizeRejected"
    assert a.final_status == "drafted" and a.final_review_status is None
    # 검증기가 거부하면 hwpx_ok False (마무리 자체는 됨)
    g2 = gen(repo, KeyedLLM(remote_answers()))
    mgr2, _ = manager(g2, reviewer=reviewer_for(g2, [FINAL_REPLY]), first_pass=False)
    ev2 = EvaluateQuality(
        mgr2,
        FakePrecheck(),
        label="y",
        pipeline={},
        final_review=True,
        finalize=True,
        verify_hwpx=lambda data: False,
    )
    (b,) = (await ev2([("01", req)])).ideas
    assert b.finalized is True and b.hwpx_ok is False


async def test_empty_draft_and_review_support_mismatch_from_the_draft_review():
    mgr, store, _ = build(
        review=reply("A", support=[{"sentence_id": "s:method:0", "support": "불일치"}])
    )
    (a,) = (await EvaluateQuality(mgr, FakePrecheck(), label="q", pipeline={})([("01", REQ)])).ideas
    assert a.valid and a.review_mismatch == 1 and not a.empty_draft
    # 버전이 없는 상태(invalid run) 는 빈 초안
    idea = EvalIdea(name="n", run_id=a.run_id, status="invalid", seconds=0)
    state = SimpleNamespace(
        problems=[],
        local_check=None,
        draft_version=0,
        writers={},
        fallback_sections=[],
        figures=[],
        status="invalid",
    )
    ev = EvaluateQuality(mgr, FakePrecheck(), label="q", pipeline={})
    await ev._quality(idea, state)
    assert idea.empty_draft and idea.cited_docs == 0


# ── 실시간 검색 ─────────────────────────────────────────
async def test_live_citations_count_documents_by_citation_flag_or_document_raw():
    docs = {
        "a": Document(
            doc_id="a", source="openalex", doc_type="paper", title="t", raw={"live": True}
        ),
        "b": Document(doc_id="b", source="openalex", doc_type="paper", title="t"),
    }

    async def get_document(doc_id):
        return docs.get(doc_id)

    cites = [
        SimpleNamespace(id="a#0", doc_id="a"),
        SimpleNamespace(id="a#1", doc_id="a"),  # 같은 문서는 1
        SimpleNamespace(id="b#0", doc_id="b"),
        SimpleNamespace(id="c#0", doc_id="c", live=True),  # 인용 표시(레인 C payload)
        SimpleNamespace(id="d#0", doc_id="d"),  # 저장소에 없는 문서
    ]
    assert await live_citations(cites, get_document) == (2, 4)
    assert await live_citations([], get_document) == (0, 0)


def test_live_sources_and_per_source_aggregation():
    state_live = {
        "status": "ok",
        "keywords": ["궤도"],
        "sources": [
            {"source": "scienceon", "status": "ok", "count": 5, "seconds": 1.0, "notice": None},
            {"source": "ntis", "status": "timeout", "count": 0, "seconds": 8.0},
            {"status": "ok"},  # source 없는 행은 버린다
        ],
    }
    one = live_sources(state_live)
    assert one == {
        "scienceon": {"status": "ok", "count": 5, "seconds": 1.0},
        "ntis": {"status": "timeout", "count": 0, "seconds": 8.0},
    }
    assert live_sources(None) == {} and live_sources({"status": "off"}) == {}
    two = {"scienceon": {"status": "ok", "count": 3, "seconds": 2.0}, "ntis": {"status": "ok"}}
    stats = source_stats([one, two, {}])
    assert stats["scienceon"] == {
        "runs": 2,
        "failures": 0,
        "failure_rate": 0.0,
        "seconds_avg": 1.5,
        "count_sum": 8,
    }
    assert stats["ntis"]["failures"] == 1 and stats["ntis"]["failure_rate"] == 0.5
    assert stats["ntis"]["seconds_avg"] == 8.0
    ideas = [
        EvalIdea(name="1", run_id="r1", status="drafted", seconds=1, live_sources=one),
        EvalIdea(name="2", run_id="r2", status="drafted", seconds=1, live_sources=two),
    ]
    totals = EvalResult(
        label="b", pipeline={}, ideas=ideas, total_seconds=2, started_at=""
    ).totals()
    assert totals["live_sources"] == stats


# ── 동시 모드 ───────────────────────────────────────────
async def test_concurrent_mode_batch_wall_clock_is_below_the_sum_of_draft_times(req, repo):
    remote = KeyedLLM(remote_answers(), delay=0.05)
    remote.answers = {}  # 답 목록을 나눠 쓰지 않게 — 기본 문장(근거 alio:1#0)
    g = gen(repo, remote, keys=["problem", "prior_work"])
    pool = CountingPool(3)
    mgr, _ = manager(g, run_slot=pool)
    ev = EvaluateQuality(
        mgr,
        FakePrecheck(),
        label="concurrent",
        pipeline={},
        concurrent=3,
        expected={"01": ["own:1"]},
        clock=time.perf_counter,
    )
    ideas = [(f"0{i}", req) for i in range(1, 5)]  # 3 + 1 → 묶음 2개
    result = await ev(ideas)
    assert result.mode == "concurrent" and result.concurrent == 3
    assert [b["ideas"] for b in result.batches] == [["01", "02", "03"], ["04"]]
    assert [i.batch for i in result.ideas] == [0, 0, 0, 1]
    assert pool.max_active == 3  # run 이 실제로 겹쳤다
    first = result.batches[0]
    per_idea = sum(i.draft_seconds for i in result.ideas[:3])
    assert first["draft_seconds"] < per_idea and first["draft_seconds"] <= first["seconds"]
    assert all(i.valid for i in result.ideas)
    # 정답이 있는 묶음만 본보기 제외를 바꾼다 (정답 없는 04 묶음은 그대로 — 순차 모드와 같다)
    assert mgr.generate.exemplar_exclude == frozenset({"own:1"})
    t = result.totals()
    assert t["batch_draft_seconds_avg"] is not None and t["batch_seconds_avg"] is not None


async def test_sequential_mode_is_unchanged_by_default(req, repo):
    remote = KeyedLLM(delay=0.01)
    mgr, _ = manager(gen(repo, remote, keys=["problem", "prior_work"]), run_slot=CountingPool(3))
    result = await EvaluateQuality(mgr, FakePrecheck(), label="s", pipeline={})(
        [("01", req), ("02", req)]
    )
    assert result.mode == "sequential" and result.batches == []
    assert all(i.batch is None for i in result.ideas)
    assert mgr.run_slot.max_active == 1  # 차례로


# ── 비교표 ─────────────────────────────────────────────
BASELINE = {  # 오늘 아침 로컬 작성 측정(f1_fallback2) 모양 — [5] 항목 없음
    "label": "baseline",
    "pipeline": {"section_search": True},
    "model": "qwen",
    "review_model": "argon",
    "ideas": [
        {
            "name": "01",
            "status": "drafted",
            "seconds": 190.0,
            "gemini_calls": 1,
            "fallback_calls": 1,
            "v1_alerts": 1,
            "sentences_v1": 3,
            "sentences_v2": 4,
            "irrelevant_citations": 0,
            "applied": 1,
            "additions_applied": 0,
            "precheck_alerts": 10,
            "precheck_hit": True,
        },
        {
            "name": "02",
            "status": "invalid",
            "seconds": 200.0,
            "gemini_calls": 0,
            "v1_alerts": 0,
            "sentences_v1": 0,
            "sentences_v2": 0,
            "irrelevant_citations": 0,
            "applied": 0,
            "additions_applied": 0,
            "precheck_alerts": 10,
            "precheck_hit": False,
        },
    ],
    "totals": {
        "ideas": 2,
        "invalid": 1,
        "precheck_hits": 1,
        "precheck_known": 2,
        "seconds_avg": 195.0,
        "gemini_calls": 2,
    },
}


async def test_report_compares_new_result_with_a_baseline_missing_new_fields(req, repo):
    g = gen(repo, KeyedLLM(remote_answers()))
    mgr, _ = manager(g, reviewer=reviewer_for(g, [FINAL_REPLY]), first_pass=False)
    new = await EvaluateQuality(
        mgr, FakePrecheck(), label="B", pipeline={}, final_review=True, finalize=True
    )([("01", req)])
    data = json.loads(json.dumps(new.to_dict(), ensure_ascii=False))
    data["totals"]["live_sources"] = {
        "scienceon": {"runs": 1, "failures": 0, "failure_rate": 0.0, "seconds_avg": 1.25},
        "ntis": {"runs": 1, "failures": 1, "failure_rate": 1.0, "seconds_avg": None},
    }
    text = eval_markdown([BASELINE, data], date="2026-10-28")
    assert "### [5] 통합 비교" in text and "### 아이디어별 [5] 통합 측정" in text
    section = text.split("### [5] 통합 비교", 1)[1].split("###", 1)[0]
    rows = {
        line.split(" | ")[0].strip("| "): line
        for line in section.splitlines()
        if line.startswith("| baseline |") or line.startswith("| B |")
    }
    base = rows["baseline"].split(" | ")
    assert base[1] == "-" and base[2] == "-" and base[3] == "-"  # 실행·②·생성 완료: 없음
    assert base[4] == "195.0" and base[5] == "50% (1/2)"  # 전체 시간·유효율(ideas − invalid)
    assert base[7] == "-" and base[10] == "-"  # 최종 점수·실시간 비율
    assert base[11] == "1/2" and base[14] == "1·1·-"  # 유사과제 적중·Gemini(대체·검토·그림)
    b = rows["B"].split(" | ")
    assert b[1] == "순차" and b[5] == "100% (1/1)" and b[7] == "3.75"
    assert "scienceon 1.2s·실패 0%" in b[12] and "ntis -s·실패 100%" in b[12]
    assert b[14] == "3·1·0" and b[15].startswith("1/1")
    assert "최종 검토 기준별 평균: B 필요성 4.00" in text
    # 기존 상세 표도 그대로
    assert "### 합계 (골든셋 전체)" in text and "### 아이디어별" in text
    assert "| baseline | 02 | invalid |" in text


def test_concurrent_mode_text_in_report():
    r = {
        "label": "c3",
        "mode": "concurrent",
        "concurrent": 3,
        "ideas": [],
        "totals": {"batch_draft_seconds_avg": 12.5, "batch_seconds_avg": 30.0},
    }
    text = eval_markdown([r], date="d")
    assert "동시 3건 (묶음 생성 12.5s·전체 30.0s)" in text


async def test_slow_fake_llm_keeps_runs_overlapping():
    """KeyedLLM 지연이 실제로 겹치는지 — 동시 모드 시험의 전제."""
    llm = KeyedLLM(delay=0.05)
    t = time.perf_counter()
    await asyncio.gather(*(llm.complete(f"[섹션: k{i}]") for i in range(3)))
    assert time.perf_counter() - t < 0.15 and llm.max_active == 3
