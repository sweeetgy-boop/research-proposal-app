"""[4] RunManager 와 실시간 검색 — 같은 입력의 세션을 이어 쓰고, 요약·doc_id 를 run 에 남기며,
manifest 에는 건수·상태만 (키워드 없음)."""

from __future__ import annotations

import json

from rra.adapters.logging import check_manifest
from rra.adapters.runs import AsyncioTaskRunner
from rra.application.services import RunManager
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.live_search import LiveKeywordMaker, LiveSearch
from rra.domain.models import Document
from rra.domain.models.live_search import LiveSearchConfig
from rra.domain.rules.lint import LintRules
from tests.fakes import (
    FakeLLM,
    FakePromptLibrary,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

KEYS = ["background", "problem", "prior_work", "objective"]
KW = json.dumps({"ko": ["궤도 틀림 감지"], "en": ["track geometry"]}, ensure_ascii=False)


class Src:
    def __init__(self, source, lang, docs):
        self.source, self.lang, self.docs, self.calls = source, lang, docs, 0

    async def fetch(self, queries, limit):
        self.calls += 1
        return list(self.docs)


def _sentence(text, ev=()):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


async def test_run_reuses_precheck_session_and_records_summary(req):
    repo = InMemoryRepository()
    doc = Document(
        doc_id="openalex:W1",
        source="openalex",
        doc_type="paper",
        title="Track geometry defect detection",
        abstract="궤도 틀림 감지 자동 검측",
        text_basis="abstract",
    )
    src = Src("openalex", "en", [doc])
    live = LiveSearch(
        LiveSearchConfig(enabled=True),
        repo,
        AsyncioTaskRunner(),
        sources={"openalex": src},
        keywords=LiveKeywordMaker(primary=FakeLLM([KW])),
    )
    before = await live.prepare("local", req)  # ② precheck 가 먼저 돌린 세션
    assert before.doc_ids == ["openalex:W1"]

    rules = LintRules(required_sections=KEYS, evidence_required=["prior_work"])
    llm = FakeLLM(
        [
            _sentence("배경"),
            _sentence("문제"),
            _sentence("선행", ["openalex:W1#0"]),
            _sentence("목표"),
        ]
    )
    gen = GenerateProposal(llm, repo, FakePromptLibrary(), rules, KEYS)
    log = FakeRunLog()
    mgr = RunManager(
        gen,
        InMemoryRunStore(),
        FakeSlot(),
        log,
        FakeTaskRunner(),
        clock=lambda: "2026-10-28T00:00:00+00:00",
        live_search=live,
    )
    state = await mgr.submit("local", req)
    state = await mgr.wait("local", state.run_id)
    assert src.calls == 1  # 같은 입력 → 세션을 이어 쓴다 (다시 검색하지 않음)
    assert state.live_search is not None and state.live_search["status"] == "partial"
    assert state.live_search["keywords"]["ko"][0] == "궤도 틀림 감지"  # 규칙으로 3개까지 채움
    assert state.live_doc_ids == ["openalex:W1"]
    manifest = log.records[-1][1]
    check_manifest(manifest)
    assert manifest["live_search"]["keywords"] == {"ko": 3, "en": 1}
    assert "궤도" not in json.dumps(manifest["live_search"], ensure_ascii=False)
    view = await mgr.get_draft("local", state.run_id)
    from rra.entrypoints.views import draft_payload, run_state_payload

    cites = draft_payload(view)["citations"]
    assert {c["doc_id"]: c["live"] for c in cites}.get("openalex:W1") is True
    assert run_state_payload(state)["live_search"]["status"] == "partial"


async def test_run_without_live_search_is_unchanged(req):
    repo = InMemoryRepository()
    rules = LintRules(required_sections=KEYS, evidence_required=[])
    gen = GenerateProposal(FakeLLM([_sentence("a")] * 4), repo, FakePromptLibrary(), rules, KEYS)
    log = FakeRunLog()
    mgr = RunManager(gen, InMemoryRunStore(), FakeSlot(), log, FakeTaskRunner())
    state = await mgr.submit("local", req)
    state = await mgr.wait("local", state.run_id)
    assert state.live_search is None and state.live_doc_ids == []
    assert log.records[-1][1]["live_search"] is None
    check_manifest(log.records[-1][1])
