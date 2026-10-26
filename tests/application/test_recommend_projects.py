"""차별화 과제 추천 유스케이스 — FakeLLM.

0건 사유, 1건, 5건 초과, 중복, 지어낸 id·수치, 자기 중복, 전부 제외, 키 없음(로컬),
include_internal, 프롬프트 주입·전송 범위.
"""

from __future__ import annotations

import json

from rra.application.usecases.recommend_projects import (
    SKIP_NO_DOCUMENTS,
    SKIP_NO_INPUT,
    SKIP_PARSE_FAILED,
    RecommendProjects,
)
from rra.domain.models import Chunk, Document, OverlapAlert, ProposalRequest, RetrievalSnapshot
from rra.domain.rules import recommendation as rule
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

REQ = ProposalRequest(
    current_state="경부선 궤도 틀림은 분기별로 측정함",
    root_cause="구간별 진행 속도가 다름",
    limitation="보수 우선순위 근거가 없음",
    goal="운행 차량 센서로 궤도 틀림을 상시 감지함",
)
DOCS = [
    Document(
        doc_id="own:1",
        source="own",
        doc_type="rnd_project",
        title="궤도 검측 이력 분석",
        abstract="과제명: 궤도 검측 이력 분석\n검측차 이력으로 보수 시기를 정함",
        orgs=["korail"],
        raw={"status": "completed"},
    ),
    Document(
        doc_id="alio:sum-1",
        source="alio",
        doc_type="internal_report",
        title="궤도 보수 우선순위 연구",
        body="연구목적: 궤도 보수 우선순위 산정",
        orgs=["korail"],
        text_basis="summary",
        visibility="internal",
    ),
    Document(
        doc_id="openalex:W1",
        source="openalex",
        doc_type="paper",
        title="Track geometry degradation",
        abstract="Track geometry degradation from inspection history",
        orgs=["external"],
    ),
]
CHUNKS = [
    Chunk(
        chunk_id="openalex:W1#0",
        doc_id="openalex:W1",
        ordinal=0,
        text="Track geometry degradation from inspection history",
        similarity=0.85,
    ),
    Chunk(
        chunk_id="alio:sum-1#0",
        doc_id="alio:sum-1",
        ordinal=0,
        text="궤도 보수 우선순위 산정",
        similarity=0.84,
        visibility="internal",
    ),
]
ALERTS = [
    OverlapAlert(
        doc_id="own:1",
        title=DOCS[0].title,
        tier="own",
        similarity=0.88,
        blocking=True,
        status="completed",
        keywords=["궤도", "검측"],
    ),
    OverlapAlert(
        doc_id="alio:sum-1", title=DOCS[1].title, tier="own", similarity=0.76, blocking=False
    ),
]


def rec(title, **kw):
    base = {
        "title": title,
        "summary": f"{title} 을 검측차 이력과 근거로 수행함",
        "differentiation": "기존 과제는 검측 주기 안의 변화를 보지 못함",
        "reasons": ["own:1 은 검측차 이력 분석에 그침"],
        "build_on": "",
        "risks": "센서 설치 승인 확인",
        "compared_with": ["own:1"],
        "evidence": ["own:1", "openalex:W1"],
    }
    return {**base, **kw}


def reply(recs, reason=None):
    return json.dumps(
        {"recommendations": recs, "no_recommendation_reason": reason}, ensure_ascii=False
    )


class StubPrecheck:
    """자기 중복 검사용. 가제에 'overlap' → 원래(0.88)보다 가까운 0.9 로 차단, 'near' → 같은 문서를
    0.85 로 차단(원래보다 멀어짐 → 통과), 'new' → 원래 차단되지 않던 문서 차단(→ 자기 중복)."""

    def __init__(self):
        self.calls: list[ProposalRequest] = []

    async def __call__(self, req):
        self.calls.append(req)
        t = req.title_hint

        def hit(doc, sim, blocking=True):
            return [
                OverlapAlert(doc_id=doc, title="t", tier="own", similarity=sim, blocking=blocking)
            ]

        if "overlap" in t:
            return hit("own:1", 0.9)
        if "near" in t:
            return hit("own:1", 0.85)
        if "new" in t:
            return hit("alio:9", 0.9)
        return hit("own:1", 0.7, blocking=False)


def make(answers, *, include_internal=True, chunks=None, fallback=False):
    repo = InMemoryRepository()
    repo.seed(DOCS, CHUNKS)
    precheck = StubPrecheck()

    async def retrieve(req):
        return RetrievalSnapshot.of(req.search_text(), list(CHUNKS if chunks is None else chunks))

    llm = FakeLLM(list(answers))
    uc = RecommendProjects(
        llm,
        FakePromptLibrary(),
        repo,
        precheck=precheck,
        retrieve=retrieve,
        include_internal=include_internal,
        provider="mlx" if fallback else "gemini",
        model="qwen" if fallback else "argon",
        fallback_local=fallback,
    )
    return uc, llm, precheck


async def test_one_recommendation_validated_and_transfer_recorded():
    uc, llm, precheck = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])])
    out = await uc(REQ, ALERTS)
    assert len(out.recommendations) == 1 and out.no_recommendation_reason is None
    r = out.recommendations[0]
    assert r.compared_with == ["own:1"] and r.evidence == ["own:1", "openalex:W1"]
    assert out.calls == 1 and out.provider == "gemini" and out.model == "argon"
    assert out.public_doc_ids == ["own:1", "openalex:W1"] and out.internal_doc_ids == ["alio:sum-1"]
    assert out.excluded_doc_ids == []
    # 자기 중복 검사는 추천마다 한 번, 추천 글(가제·요약·차별점·위험)만으로 — 원래 4칸은 섞지 않는다
    probe = precheck.calls[0]
    assert len(precheck.calls) == 1 and probe.title_hint == r.title
    assert probe.current_state == r.summary and probe.root_cause == r.differentiation
    assert REQ.current_state not in probe.search_text() and probe.differentiation == ""
    # 프롬프트: 유사과제 <doc> + 근거 <chunk> + 제안 입력, 시스템 프롬프트는 recommend
    prompt = llm.calls[0]
    assert '<doc id="own:1" tier="own" status="completed"' in prompt and 'blocking="true"' in prompt
    assert '<chunk id="openalex:W1#0" doc="openalex:W1">' in prompt
    assert "경부선 궤도 틀림" in prompt and "RECOMMEND" in llm.systems[0]
    t = out.transfer()
    assert t["recommendations"] == 1 and t["discarded"] == 0 and t["calls"] == 1


async def test_zero_recommendations_keep_the_model_reason():
    uc, _, precheck = make([reply([], "아이디어가 이미 기존 과제와 충분히 다름")])
    out = await uc(REQ, ALERTS)
    assert (
        out.recommendations == []
        and out.no_recommendation_reason == "아이디어가 이미 기존 과제와 충분히 다름"
    )
    assert precheck.calls == [] and out.skipped_reason is None


async def test_more_than_five_are_capped_and_duplicates_collapse():
    topics = [
        "승강장 혼잡",
        "전차선 마모",
        "신호기 고장",
        "화물 적재",
        "베어링 진동",
        "터널 누수",
        "분기기 틀림",
    ]
    recs = [
        rec(f"{t} 진단 과제", summary=f"{t} 자료로 상태를 봄", differentiation=f"{t} 관점이 다름")
        for t in topics
    ]
    recs.insert(
        1,
        rec(
            "승강장 혼잡 진단 과제 (변형)",
            summary="승강장 혼잡 자료로 상태를 봄",
            differentiation="승강장 혼잡 관점이 다름",
        ),
    )
    uc, _, _ = make([reply(recs)])
    out = await uc(REQ, ALERTS)
    assert len(out.recommendations) == 5
    reasons = [d["reason"] for d in out.discarded]
    assert (
        reasons.count(rule.DISCARD_DUPLICATE) == 1 and reasons.count(rule.DISCARD_OVER_LIMIT) == 2
    )


async def test_made_up_ids_and_numbers_are_discarded_with_reasons():
    uc, _, _ = make(
        [
            reply(
                [
                    rec("좋은 과제", evidence=["own:1"]),
                    rec("지어낸 id", compared_with=["own:999"]),
                    rec("논문과 비교", compared_with=["openalex:W1"], summary="논문과 비교해 다름"),
                    rec("지어낸 근거", evidence=["openalex:W777"]),
                    rec("지어낸 수치", summary="비용을 37% 절감함"),
                ]
            )
        ]
    )
    out = await uc(REQ, ALERTS)
    assert [r.title for r in out.recommendations] == ["좋은 과제", "논문과 비교"]
    assert {d["title"]: d["reason"] for d in out.discarded} == {
        "지어낸 id": rule.DISCARD_COMPARED,
        "지어낸 근거": rule.DISCARD_EVIDENCE,
        "지어낸 수치": rule.DISCARD_NUMBER,
    }


async def test_self_overlap_is_a_warning_by_default_and_an_exclusion_in_exclude_mode():
    """warn(기본): 더 가까워진 추천도 남기되 overlap_warning 에 문서 id. exclude: 추천에서 뺀다."""
    answers = [
        reply(
            [
                rec("overlap 과제"),
                rec(
                    "new 과제",
                    summary="역사 설비 자료로 다른 대상을 봄",
                    differentiation="대상 설비가 다름",
                ),
                rec("지어낸 수치", summary="40% 절감"),
            ]
        )
    ]
    uc, _, precheck = make(list(answers))
    out = await uc(REQ, ALERTS)
    assert [r.title for r in out.recommendations] == ["overlap 과제", "new 과제"]
    assert out.recommendations[0].overlap_warning == ["own:1"]  # 같은 문서, 더 가까워짐
    assert out.recommendations[1].overlap_warning == ["alio:9"]  # 원래 차단되지 않던 문서
    assert [d["reason"] for d in out.discarded] == [rule.DISCARD_NUMBER]
    assert len(precheck.calls) == 2  # 검증에서 떨어진 것은 자기 중복 검사를 하지 않는다
    uc, _, _ = make(list(answers))
    uc.self_overlap_mode = "exclude"
    out = await uc(REQ, ALERTS)
    assert out.recommendations == []
    reasons = [d["reason"] for d in out.discarded]
    assert reasons.count(rule.DISCARD_SELF_OVERLAP) == 2 and rule.DISCARD_NUMBER in reasons
    assert out.no_recommendation_reason.endswith("검증에서 제외됨 3건")


async def test_recommendation_that_moved_away_from_the_blocking_project_has_no_warning():
    """같은 문서에 아직 차단되더라도 원래 아이디어(0.88)보다 멀어졌으면(0.85) 경고도 없다."""
    uc, _, _ = make([reply([rec("near 과제")])])
    out = await uc(REQ, ALERTS)
    assert [r.title for r in out.recommendations] == ["near 과제"] and out.discarded == []
    assert out.recommendations[0].overlap_warning == []


async def test_parse_failure_and_empty_inputs_are_skipped():
    uc, _, _ = make(["not json"])
    out = await uc(REQ, ALERTS)
    assert out.skipped_reason == SKIP_PARSE_FAILED and out.calls == 1
    uc, llm, _ = make([reply([])], chunks=[])
    out = await uc(REQ, [])
    assert out.skipped_reason == SKIP_NO_INPUT and llm.calls == []
    uc, llm, _ = make([reply([])], chunks=[], include_internal=False)
    out = await uc(REQ, [ALERTS[1]])  # internal 문서 하나뿐 → 보낼 것이 없다
    assert out.skipped_reason == SKIP_NO_DOCUMENTS and out.excluded_doc_ids == ["alio:sum-1"]
    assert llm.calls == []


async def test_include_internal_false_excludes_internal_docs_and_chunks():
    uc, llm, _ = make([reply([rec("과제")])], include_internal=False)
    out = await uc(REQ, ALERTS)
    assert out.internal_doc_ids == [] and out.excluded_doc_ids == ["alio:sum-1"]
    assert "alio:sum-1" not in llm.calls[0] and "own:1" in llm.calls[0]


async def test_without_key_runs_on_local_model_and_marks_fallback():
    uc, _, _ = make([reply([rec("과제")])], fallback=True)
    out = await uc(REQ, ALERTS)
    assert out.fallback_local is True and out.provider == "mlx" and len(out.recommendations) == 1
