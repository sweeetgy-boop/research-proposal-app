"""② 유사과제 흐름 유스케이스 (2026-10-28 레인 A) — FakeLLM.

AI 같음 판정(같다/다르다/실패 → 로컬 → 규칙), reranker 점수 중심 precheck·메모·[다시 시도], 비교표
([유사함] 만·원문 추출·정보 없음), [AI로 다듬기], 선택이 ③ 5. 특이사항 프롬프트로 들어가는 경로.
"""

from __future__ import annotations

import json

from rra.application.usecases.compare_projects import CompareProjects
from rra.application.usecases.extract_cells import CellExtractor
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.judge_sameness import SameJudge
from rra.application.usecases.polish_field import PolishField
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.live_search import LiveKeywords
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.lint import LintRules
from rra.domain.rules.overlap import RerankRule
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

IDEA = ProposalRequest(
    title_hint="폐철도역사 유휴 공간 활용",
    current_state="폐 역사 이용 방안 마련이 필요한 상황",
    root_cause="노선 변경으로 폐 철도역사가 생김",
    limitation="방치되고 활용 인식이 부족함",
    goal="폐철도역사 유휴 공간 활용 유형과 정책적 해결책 제시",
)
GENERIC = ["부족", "정책", "상황", "인식", "필요한", "이용", "방치", "해결책", "마련"]
DOCS = [
    Document(
        doc_id="own:station",
        source="own",
        doc_type="rnd_project",
        title="폐철도역사 유휴 공간 문화시설 활용 방안",
        body="폐철도역사 유휴 공간을 지역 문화시설로 활용하는 방안을 연구함.",
    ),
    Document(
        doc_id="alio:proc",
        source="alio",
        doc_type="internal_report",
        title="철도 산업 발전을 위한 해외 철도차량 조달정책 분석",
        body="해외 조달정책 분석. 국내 상황과 인식이 부족하고 정책 마련이 필요한 상황.",
        text_basis="summary",
    ),
    Document(
        doc_id="ntis:tunnel",
        source="ntis",
        doc_type="rnd_project",
        title="철도 터널내 바닥 여굴 채움재에 따른 궤도 진동영향 저감방안 제시",
        abstract="터널 여굴 채움재가 궤도 진동에 주는 영향을 분석하고 저감 방안을 제시함.",
    ),
]


class Scorer:
    """reranker 점수 대역 — doc_id → 점수."""

    model_name = "fake/scorer"

    def __init__(self, scores):
        self.scores = scores

    async def score_documents(self, query, docs):
        return [self.scores.get(d.doc_id, 0.0) for d, _ in docs]


def _repo(sims=(0.85, 0.86, 0.86)):
    repo = InMemoryRepository()
    repo.seed(DOCS, [])
    repo.similar = list(zip(DOCS, sims, strict=True))
    return repo


def verdicts(*rows):
    return json.dumps(
        {"items": [{"doc_id": d, "verdict": v, "reason": r} for d, v, r in rows]},
        ensure_ascii=False,
    )


async def _keywords(req):
    return LiveKeywords(ko=["폐철도역사 활용", "유휴 공간"], origin="argon")


def _precheck(repo, judge=None):
    return PrecheckOverlap(
        repo,
        keywords=KeywordRule().with_extra_generic(GENERIC),
        reranker=Scorer({"own:station": 0.97, "alio:proc": 0.06, "ntis:tunnel": 0.02}),
        rerank=RerankRule(threshold=0.5),
        same_judge=judge,
        keyword_source=_keywords,
    )


async def test_pilot_false_blocks_are_gone_with_reranker_and_core_keywords():
    """시범: 일반어가 겹친 조달정책·터널 여굴 과제가 차단 → reranker 점수·핵심 키워드로 차단
    아님."""
    result = await _precheck(_repo()).run(IDEA)
    by = {a.doc_id: a for a in result.alerts}
    assert by["own:station"].blocking and by["own:station"].keywords == [
        "폐철도역사",
        "유휴",
        "공간",
    ]
    assert not by["alio:proc"].blocking and by["alio:proc"].keywords == []
    assert not by["ntis:tunnel"].blocking
    assert (
        result.core_keywords == ["폐철도역사 활용", "유휴 공간"]
        and result.keyword_origin == "argon"
    )


async def test_same_judgment_blocks_only_same_and_memo_serves_follow_up_calls():
    argon = FakeLLM(
        [
            verdicts(
                ("own:station", "same", "폐역사 유휴 공간 활용으로 대상·문제·방법이 같음"),
                ("alio:proc", "different", "조달정책 분석으로 대상이 다름"),
                ("ntis:tunnel", "different", "터널 진동 저감으로 대상이 다름"),
            )
        ]
    )
    repo = _repo()
    judge = SameJudge(primary=argon, repo=repo, provider="gemini", model="argon")
    pre = _precheck(repo, judge)
    result = await pre.run(IDEA)
    assert result.judgment.status == "ai" and result.judgment.judged_by == "argon"
    by = {a.doc_id: a for a in result.alerts}
    assert by["own:station"].blocking and by["own:station"].judgment == "same"
    assert by["alio:proc"].judgment == "different" and by["alio:proc"].judgment_reason
    assert '<doc id="alio:proc">' in argon.calls[0] and "[아이디어 — 제안자 입력]" in argon.calls[0]
    # 후속 경로(비교표·생성 게이트)는 메모 — LLM 을 다시 부르지 않는다
    assert [a.doc_id for a in await pre(IDEA) if a.blocking] == ["own:station"]
    assert len(argon.calls) == 1


async def test_argon_failure_goes_to_local_then_rule_with_reason_and_retry():
    repo = _repo()
    argon = FakeLLM([], fail_at={0, 1})
    local = FakeLLM(["해석할 수 없는 응답", verdicts(("own:station", "partial", "일부 겹침"))])
    judge = SameJudge(primary=argon, local=local, repo=repo)
    pre = _precheck(repo, judge)
    result = await pre.run(IDEA)
    assert result.judgment.status == "rule_fallback" and result.judgment.judged_by == "rule"
    assert result.judgment.errors == ["argon:timeout", "local:parse"]
    assert all(a.judged_by == "rule" for a in result.alerts)
    assert [a.doc_id for a in result.alerts if a.blocking] == ["own:station"]  # 규칙 판정 그대로
    retried = await pre.rejudge(IDEA)  # [다시 시도] — Argon 은 또 실패, 로컬이 이번엔 판정
    assert retried.judgment.status == "ai" and retried.judgment.judged_by == "local"
    assert not any(a.blocking for a in retried.alerts)  # partial 은 차단 아님


async def test_internal_documents_are_not_sent_to_argon_when_excluded():
    repo = _repo()
    repo.docs["own:station"] = DOCS[0].model_copy(update={"visibility": "internal"})
    argon = FakeLLM([verdicts(("alio:proc", "different", "다름"))])
    judge = SameJudge(primary=argon, repo=repo, include_internal=False)
    _, info = await judge(
        IDEA,
        [
            OverlapAlert(doc_id=d, title="t", tier="own", similarity=0.8, blocking=False)
            for d in ("own:station", "alio:proc")
        ],
    )
    assert "own:station" not in argon.calls[0] and info.excluded_doc_ids == ["own:station"]


async def test_comparison_uses_only_similar_rows_and_extracts_cells_from_source():
    repo = _repo()
    alerts = [
        OverlapAlert(doc_id=d.doc_id, title=d.title, tier="own", similarity=0.8, blocking=False)
        for d in DOCS
    ]
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "items": [
                        {
                            "doc_id": "own:station",
                            "objective": "폐철도역사 유휴 공간을 지역 문화시설로 활용하는 방안을 연구함",
                            # 원문 밖 → 규칙 칸
                            "method": "드론과 인공지능으로 교량을 촬영함",
                            "scope": "",
                            "outcome": "",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        ]
    )
    uc = CompareProjects(repo, extractor=CellExtractor(primary=llm))
    empty = await uc(IDEA, alerts, similar_only=True)
    assert empty.projects == [] and empty.empty_reason.startswith("유사한 과제를 고르면")
    req = ProposalRequest(
        **IDEA.model_dump(exclude={"similar_choices"}),
        similar_choices=[
            {"doc_id": "own:station", "choice": "similar"},
            {"doc_id": "alio:proc", "choice": "unrelated"},
        ],
    )
    table = await uc(req, alerts, similar_only=True)
    (col,) = table.projects
    assert col.doc_id == "own:station" and table.extraction == "ai"
    assert col.cells["objective"].startswith("폐철도역사 유휴 공간을")
    assert "드론" not in col.cells["method"] and col.cells["scope"] == "정보 없음"
    assert table.proposal.title == "폐철도역사 유휴 공간 활용"
    await uc(req, alerts, similar_only=True)
    assert len(llm.calls) == 1  # 같은 문서는 메모


async def test_polish_field_argon_then_local_then_keep_original_with_reason():
    good = PolishField(primary=FakeLLM(['{"text": "폐철도역사 유휴 공간 활용 유형을 제시함"}']))
    out = await good(IDEA, "goal", IDEA.goal)
    assert (
        out.changed and out.by == "argon" and out.text == "폐철도역사 유휴 공간 활용 유형을 제시함"
    )
    bad = PolishField(
        primary=FakeLLM([], fail_at={0}),
        local=FakeLLM(['{"text": "비용을 30% 절감함"}']),
    )
    kept = await bad(IDEA, "goal", IDEA.goal)
    assert not kept.changed and kept.text == IDEA.goal and "수치" in kept.reason
    none = await PolishField()(IDEA, "goal", IDEA.goal)
    assert none.text == IDEA.goal and none.reason  # 빈 결과로 끝내지 않는다


async def test_choices_flow_into_overlap_review_prompt(own):
    repo = _repo((0.81, 0.82, 0.81))
    llm = FakeLLM([json.dumps([{"text": "기존 과제와 다름.", "evidence": []}])])
    rules = LintRules(required_sections=["overlap_review"])
    gen = GenerateProposal(
        llm,
        repo,
        FakePromptLibrary(),
        rules,
        ["overlap_review"],
        own=own,
        check_overlap=True,
        keywords=KeywordRule(min_hits=1),
    )
    req = ProposalRequest(
        **IDEA.model_dump(exclude={"similar_choices"}),
        similar_choices=[
            {"doc_id": "own:station", "choice": "similar"},
            {"doc_id": "alio:proc", "choice": "unrelated"},
        ],
    )
    snap = await gen.retrieve(req)
    ids = {a.doc_id: a for a in snap.overlap}
    assert "alio:proc" not in ids and ids["own:station"].blocking
    assert ids["own:station"].choice == "similar"
    await gen.compose_section("overlap_review", req, snap)
    prompt = llm.calls[-1]
    assert "id=own:station" in prompt and "제안자판단=유사함" in prompt
    assert "id=alio:proc" not in prompt
    # 모두 [관련 없음] 이면 앱이 "중복 기준 이상 없음" 확정 문장을 쓴다
    none = ProposalRequest(
        **IDEA.model_dump(exclude={"similar_choices"}),
        similar_choices=[{"doc_id": d.doc_id, "choice": "unrelated"} for d in DOCS],
    )
    snap2 = await gen.retrieve(none)
    composed = await gen.compose_section("overlap_review", none, snap2)
    assert composed.mode == "app"
