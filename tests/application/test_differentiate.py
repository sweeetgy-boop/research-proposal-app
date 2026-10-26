"""기능 2 유스케이스 — FakeLLM: 전송 범위·검증·폐기·건너뜀, Agent 연결, manifest, 프롬프트 주입."""

import json

from rra.application.services import ProposalAssistant
from rra.application.usecases.differentiate import (
    SKIP_NO_CANDIDATES,
    SKIP_NO_DOCUMENTS,
    SKIP_PARSE_FAILED,
    Differentiate,
)
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.rules.lint import LintRules
from tests.entrypoints.ui.fake_app import make_assistant
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

REQ = ProposalRequest(
    current_state="역사 공조·조명 설비가 상시 가동됨",
    root_cause="설비별 전력 데이터가 없음",
    limitation="수동으로 켜고 끔",
    goal="AI 로 역사 설비 전기에너지를 최적화함",
)
DOCS = [
    Document(
        doc_id="own:1",
        source="own",
        doc_type="rnd_project",
        title="AI 기반 역사 설비 전기에너지 최적화",
        abstract="과제명: AI 기반 역사 설비 전기에너지 최적화\n[사내 과제] 제안 · 상태 미채택",
        orgs=["korail"],
        visibility="internal",
        raw={"status": "rejected"},
    ),
    Document(
        doc_id="alio:sum-1",
        source="alio",
        doc_type="internal_report",
        title="역사 에너지 관리 연구",
        body="연구목적: 역사 전력 사용 패턴 분석 2024년",
        orgs=["korail"],
        text_basis="summary",
    ),
]
ALERTS = [
    OverlapAlert(
        doc_id="own:1",
        title=DOCS[0].title,
        tier="own",
        similarity=0.89,
        blocking=True,
        status="rejected",
        keywords=["역사", "공조"],
    ),
    OverlapAlert(
        doc_id="alio:sum-1", title=DOCS[1].title, tier="own", similarity=0.76, blocking=False
    ),
    OverlapAlert(doc_id="x:far", title="먼 과제", tier="external", similarity=0.5, blocking=False),
]
GOOD = {
    "items": [
        {
            "doc_id": "own:1",
            "overlap_summary": "역사 설비 전기에너지 최적화 대상이 겹침",
            "build_on": "그 제안의 설비 데이터 수집 범위를 이어받음",
            "differentiation": [
                "열차 도착 연동 제어로 확장함",
                "1개 역사 실증으로 축소해 재제안함",
            ],
            "evidence": ["own:1"],
        },
        {
            "doc_id": "alio:sum-1",
            "overlap_summary": "전력 사용 패턴 분석이 겹침",
            "build_on": "2024년 분석 결과를 활용함",
            "differentiation": ["비용을 37% 절감함"],  # 자료에 없는 수치 → 폐기
            "evidence": ["alio:sum-1"],
        },
        {"doc_id": "x:far", "overlap_summary": "x", "differentiation": ["y"]},  # 후보 밖
    ]
}


def make_repo():
    r = InMemoryRepository()
    r.seed(DOCS, [])
    return r


def usecase(answer, **kw):
    return Differentiate(
        FakeLLM([answer]), FakePromptLibrary(), make_repo(), provider="gemini", model="argon", **kw
    )


async def test_candidates_are_sent_as_doc_blocks_and_items_are_validated():
    uc = usecase(json.dumps(GOOD, ensure_ascii=False))
    proposal = await uc(REQ, ALERTS)
    prompt = uc.llm.calls[0]
    assert (
        '<doc id="own:1" tier="own" status="rejected" similarity="0.89" keywords="역사,공조"'
        in prompt
    )
    assert '<doc id="alio:sum-1" tier="own" status="none"' in prompt and "x:far" not in prompt
    assert "[제안 입력]" in prompt and "보완 재제안" in prompt
    assert [i.doc_id for i in proposal.items] == ["own:1"]
    assert proposal.items[0].status == "rejected" and len(proposal.items[0].differentiation) == 2
    assert [(d["doc_id"], d["reason"]) for d in proposal.discarded] == [
        ("alio:sum-1", "ungrounded"),
        ("x:far", "unknown_doc"),
    ]
    assert proposal.public_doc_ids == ["alio:sum-1"] and proposal.internal_doc_ids == ["own:1"]
    assert proposal.calls == 1 and proposal.provider == "gemini" and not proposal.fallback_local
    t = proposal.transfer()
    assert t["items"] == 1 and t["discarded"] == 2 and t["public_doc_ids"] == ["alio:sum-1"]


async def test_include_internal_false_keeps_internal_docs_out_of_the_prompt():
    uc = usecase(json.dumps(GOOD, ensure_ascii=False), include_internal=False)
    proposal = await uc(REQ, ALERTS)
    assert "own:1" not in uc.llm.calls[0] and proposal.excluded_doc_ids == ["own:1"]
    assert proposal.internal_doc_ids == [] and proposal.public_doc_ids == ["alio:sum-1"]
    assert [d["reason"] for d in proposal.discarded if d["doc_id"] == "own:1"] == ["unknown_doc"]


async def test_skips_without_candidates_documents_or_parsable_output():
    uc = usecase("{}")
    assert (await uc(REQ, [ALERTS[2]])).skipped_reason == SKIP_NO_CANDIDATES
    only_internal = usecase("{}", include_internal=False)
    assert (await only_internal(REQ, [ALERTS[0]])).skipped_reason == SKIP_NO_DOCUMENTS
    garbage = usecase("JSON 아님")
    p = await garbage(REQ, ALERTS)
    assert p.skipped_reason == SKIP_PARSE_FAILED and p.calls == 1 and p.items == []
    assert len(garbage.llm.calls) == 1


async def test_assistant_logs_differentiate_and_records_transfer_in_manifest():
    assistant = make_assistant(blocking=True)
    assert isinstance(assistant, ProposalAssistant)
    res = await assistant.intake(REQ)
    assert any(d.tool == "rra_differentiate" for d in res.decisions)
    proposal = await assistant.differentiate(REQ, res.alerts)
    assert (
        proposal is not None and proposal.items and assistant.trace[-1].tool == "rra_differentiate"
    )
    chosen = REQ.model_copy(update={"differentiation": proposal.items[0].differentiation[0]})
    state = await assistant.proceed(chosen, res.alerts, acknowledged=True, differentiation=proposal)
    await assistant.manager.wait(assistant.user, state.run_id)
    manifests = [m for _, m in assistant.manager.run_log.records]
    assert manifests[-1]["differentiation"]["chosen"] is True
    assert manifests[-1]["differentiation"]["items"] == 1
    from rra.adapters.logging import check_manifest

    for m in manifests:
        check_manifest(m)


async def test_assistant_without_differentiator_skips_and_logs():
    assistant = make_assistant(blocking=True, differentiate=None)
    res = await assistant.intake(REQ)
    assert await assistant.differentiate(REQ, res.alerts) is None
    assert "건너뜀" in assistant.trace[-1].summary


async def test_chosen_direction_is_injected_into_objective_method_and_overlap_prompts(req):
    keys = ["title", "objective", "method", "overlap_review"]
    rules = LintRules(required_sections=keys)
    repo = make_repo()
    llm = FakeLLM(['[{"text": "x", "evidence": []}]'] * 4)
    gen = GenerateProposal(llm, repo, FakePromptLibrary(), rules, keys)
    chosen = req.model_copy(update={"differentiation": "열차 도착 연동 제어로 확장함"})
    await gen(chosen)
    by_key = dict(zip(keys, llm.calls, strict=True))
    assert "[제안자가 정한 차별화 방향" in by_key["objective"]
    assert (
        "열차 도착 연동 제어로 확장함" in by_key["method"]
        and "[제안자가 정한 차별화 방향" in by_key["overlap_review"]
    )
    assert "[제안자가 정한 차별화 방향" not in by_key["title"]
    assert (
        '"differentiation": "열차 도착 연동 제어로 확장함"' in by_key["title"]
    )  # 입력 JSON 에는 있다
    plain = FakeLLM(['[{"text": "x", "evidence": []}]'] * 4)
    await GenerateProposal(plain, repo, FakePromptLibrary(), rules, keys)(req)
    assert all("[제안자가 정한 차별화 방향" not in c for c in plain.calls)
