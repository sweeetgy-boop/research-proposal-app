"""suite 실행·문제 생성 유스케이스 (ADR 0058) — 가짜 precheck·recommender·메모리 저장소."""

from __future__ import annotations

from rra.application.usecases.eval_problems import ProblemGenerator, precheck_blocks, today_seed
from rra.application.usecases.evaluate_suite import EvaluateSuite, l2_from_quality
from rra.domain.models import Document, OverlapAlert, PrecheckResult
from rra.domain.models.eval_problem import EvalProblem, NovelTopic, ProblemMix, ProblemSource
from rra.domain.models.gap import JudgmentInfo
from rra.domain.models.novel import (
    Barrier,
    BarrierBasis,
    NovelRecommendation,
    NovelTitle,
)
from rra.domain.models.recommendation import RecommendationResult
from rra.domain.rules.keywords import KeywordRule
from tests.fakes import InMemoryRepository


def alert(doc_id, *, blocking=False, judgment=None, merged=()):
    return OverlapAlert(
        doc_id=doc_id,
        title="t",
        tier="own",
        similarity=0.9,
        blocking=blocking,
        judgment=judgment,
        judged_by="argon" if judgment else None,
        merged_ids=list(merged),
    )


class FakePrecheck:
    """문제 goal 글자에 따라 알림을 돌려준다. 호출마다 calls 를 센다."""

    def __init__(self):
        self.calls = 0

    async def run(self, req, *, ai=True, **_):
        self.calls += 1
        if "정답" in req.goal:
            alerts = [alert("own:x", judgment="different"), alert("own:ans", merged=["own:ans2"])]
        elif "차단" in req.goal:
            alerts = [alert("own:blk", blocking=True, judgment="same")]
        else:
            alerts = []
        return PrecheckResult(alerts=alerts, judgment=JudgmentInfo(status="ai", calls=1))


class FakeRecommender:
    async def __call__(self, req, alerts):
        if alerts:
            return RecommendationResult(calls=1)  # 차별화 갈래, 0건
        barrier = Barrier(
            type="수요",
            statement="s",
            basis=BarrierBasis(level="추정", doc_ids=[]),
            check="c",
        )
        rec = NovelRecommendation(
            approach="a",
            summary="s",
            maturity="연구 필요",
            barriers=[
                barrier,
                barrier.model_copy(
                    update={"basis": BarrierBasis(level="근거 있음", doc_ids=["d"])}
                ),
            ],
            titles=[NovelTitle(title="t", resolves=[0], reason="r")],
        )
        return RecommendationResult(mode="novel", novel=[rec], calls=1)


def problem(kind, goal, answers=()):
    return EvalProblem(
        id=f"{kind}-{goal}",
        kind=kind,
        request={"current_state": "c", "root_cause": "r", "limitation": "l", "goal": goal},
        answers=list(answers),
    )


async def test_suite_scores_each_kind_and_counts_calls():
    pre = FakePrecheck()
    suite = EvaluateSuite(
        pre,
        suite="l1",
        seed=5,
        repeats=2,
        label="가",
        commit="abc1234",
        config_flags={"facets.enabled": False},
        recommender=FakeRecommender(),
    )
    problems = [
        problem("reverse", "정답 있음", ["own:ans2"]),  # 합친 판(merged_ids)으로 적중
        problem("reverse", "정답 없음"),
        problem("trap", "차단되는 함정"),
        problem("trap", "안 걸리는 함정"),
        problem("novel", "새 영역"),
    ]
    result = await suite(problems)
    assert pre.calls == 10 and result.n == 5 and result.repeats == 2
    m = result.metrics
    assert m.recall_at5 == 0.5 and m.false_block == 0.5 and m.novel_rate == 1.0
    assert m.rec_zero_rate == 0.6  # 알림 있는 3건은 차별화 0건, 알림 없는 2건은 novel 안 있음
    assert m.novel_estimated_barrier_ratio == 0.5
    assert result.llm_calls == 20 and result.cache_hits == 0  # 판정 10 + 과제안 10
    assert result.label == "가" and result.commit == "abc1234"
    assert result.config_flags == {"facets.enabled": False}
    assert "recall_at5" in result.ci95 and result.sealed is False
    dumped = result.model_dump_json()
    assert "own:" not in dumped and "정답" not in dumped  # 결과에 doc_id·본문 없음


async def test_suite_subtracts_replay_hits_and_notes_budget():
    class Replay:
        hits, misses, recorded = 3, 1, 0

    suite = EvaluateSuite(
        FakePrecheck(), suite="l0", seed=1, replay=Replay(), budget_exhausted=lambda: True
    )
    result = await suite([problem("trap", "x")] * 4)
    assert result.llm_calls == 0 and result.cache_hits == 3  # 판정 4 − 적중 3 − 마른 미스 1
    assert any("캐시 재생 적중 3건" in n for n in result.notes)
    assert any("상한 소진" in n for n in result.notes)


async def test_recommender_failure_counts_as_zero_without_stopping():
    class Boom:
        async def __call__(self, req, alerts):
            raise RuntimeError("x")

    suite = EvaluateSuite(FakePrecheck(), suite="l1", seed=1, recommender=Boom())
    result = await suite([problem("novel", "새 영역")])
    assert result.metrics.rec_zero_rate == 1.0 and result.metrics.novel_rate == 1.0


# ── 문제 생성 ─────────────────────────────────────────
LONG_A = (
    "일반철도 구간의 궤도틀림은 궤도검측차가 분기마다 측정한다. "
    "측정 주기 사이의 급격한 틀림 진행은 점검원이 도보로 확인해야 알 수 있다. "
    "영업 차량 대차에 가속도 센서를 달아 진동 신호에서 틀림 징후를 추출한다. "
    "진행 속도를 추정해 보수 우선순위 목록을 만든다."
)
LONG_B = (
    "대형 역 주차장은 만차 여부를 입구 전광판으로만 안내한다. "
    "이용자가 빈자리를 찾아 주차장을 돌며 혼잡이 커진다. "
    "주차면 센서로 빈자리를 세어 앱으로 안내한다. 시간대별 혼잡을 예측해 요금 할인 시간을 정한다."
)


def _repo():
    repo = InMemoryRepository()
    docs = [
        Document(
            doc_id="own:1",
            source="own",
            doc_type="rnd_project",
            title="궤도틀림 감지",
            abstract=LONG_A,
        ),
        Document(
            doc_id="alio:2",
            source="alio",
            doc_type="internal_report",
            title="역 주차 안내",
            body=LONG_B,
        ),
        Document(
            doc_id="alio:3",
            source="alio",
            doc_type="internal_report",
            title="비공개",
            body=LONG_B,
            visibility="internal",
        ),
        Document(
            doc_id="ntis:4", source="ntis", doc_type="report", title="보고서", abstract=LONG_A
        ),  # doc_type 밖
        Document(
            doc_id="ntis:5",
            source="ntis",
            doc_type="rnd_project",
            title="주차 혼잡",
            abstract=LONG_B,
        ),
    ]
    repo.seed(docs, [])
    return repo


async def test_generator_uses_only_project_sources_and_skips_internal_and_blocked_topics():
    repo = _repo()
    seen: list[str] = []

    async def rule_check(req):
        seen.append(req.goal)
        return "막힘" in req.goal

    topics = [
        NovelTopic(
            title_hint="a", current_state="c", root_cause="r", limitation="l", goal="막힘 주제"
        ),
        NovelTopic(
            title_hint="b", current_state="c", root_cause="r", limitation="l", goal="새 주제"
        ),
    ]
    gen = ProblemGenerator(
        repo,
        sources=[
            ProblemSource(source="own"),
            ProblemSource(source="alio"),
            ProblemSource(source="ntis", doc_types=("rnd_project",)),
        ],
        topics=topics,
        keywords=KeywordRule(),
        rule_check=rule_check,
        min_text_chars=50,
    )
    materials = await gen.materials()
    assert [d.doc_id for d in materials] == ["alio:2", "ntis:5", "own:1"]  # internal·report 제외
    mix = ProblemMix(reverse=0.5, trap=0.25, novel=0.25)  # n=8 → reverse 4·trap 2·novel 2
    problems = await gen.generate(seed=11, n=8, mix=mix)
    kinds = sorted(p.kind for p in problems)
    assert kinds.count("reverse") == 3  # 재료 3건뿐
    assert kinds.count("novel") == 1 and "trap" in kinds  # 막힌 주제는 빠진다
    assert [p for p in problems if p.kind == "novel"][0].request["goal"] == "새 주제"
    assert sorted(seen) == ["막힘 주제", "새 주제"]
    again = await gen.generate(seed=11, n=8, mix=mix)
    assert [p.id for p in again] == [p.id for p in problems]  # 같은 seed → 같은 묶음


async def test_precheck_blocks_uses_rule_only_stage():
    class Pre:
        async def run(self, req, *, ai):
            assert ai is False
            return PrecheckResult(alerts=[alert("own:b", blocking=True)])

    assert await precheck_blocks(Pre())(problem("novel", "g").to_request()) is True


def test_today_seed_is_date_number():
    from datetime import date

    assert today_seed(date(2026, 11, 9)) == 20261109


def test_l2_from_quality_wraps_golden_result_and_samples_runs():
    data = {
        "label": "l2x",
        "started_at": "2026-11-09T01:00:00",
        "total_seconds": 900.0,
        "gemini_calls": 42,
        "totals": {"valid": 9},
        "ideas": [
            {"run_id": f"r{i}", "precheck_hit": i % 3 != 0, "precheck_seconds": float(i)}
            for i in range(10)
        ],
    }
    result, sample = l2_from_quality(data, seed=1, sample_ratio=0.1)
    assert result.suite == "l2" and result.n == 10 and result.metrics.recall_at5 == 0.6
    assert result.metrics.latency_p50 == 4.5 and result.llm_calls == 42 and result.label == "l2x"
    assert len(sample) == 1 and sample[0].startswith("r")
