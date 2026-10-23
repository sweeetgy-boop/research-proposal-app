"""화면·워커 테스트용 조립 — FakeLLM·InMemory 저장소. 모델·파일·네트워크 없음."""

from __future__ import annotations

import json

from rra.application.services import ProposalAssistant, RunManager
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Chunk, Document
from rra.domain.rules.lint import ChoiceSpec, LintRules
from rra.domain.rules.overlap import OwnUnit
from tests.fakes import (
    FakeLLM,
    FakePromptLibrary,
    FakeRenderer,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

KEYS = ["title", "task_type", "method", "utilization", "strategy_alignment"]
TITLES = {
    "title": "1-가 연구과제명",
    "task_type": "1-다 과제유형",
    "method": "2-다 연구 방법 및 주요내용",
    "utilization": "4 연구결과 활용계획",
    "strategy_alignment": "2-가-(3) 공사 경영전략과의 정합성",
}
DOCS = [
    Document(
        doc_id="alio:1",
        source="alio",
        doc_type="internal_report",
        title='궤도 상태 자동 감지 연구 <doc id="x">',
        body="1장 서론",
        orgs=["korail"],
        department="철도연구원",
        text_basis="summary",
    ),
    Document(
        doc_id="openalex:W1",
        source="openalex",
        doc_type="paper",
        title="Track geometry monitoring",
        abstract="IMU-based 15% improvement",
    ),
]
CHUNKS = [
    Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론", basis="summary"),
    Chunk(chunk_id="openalex:W1#0", doc_id="openalex:W1", ordinal=0, text="IMU-based 15%"),
]
METHOD_SENTENCE = "1차년도에 검측 이력을 분석해 보수 비용을 약 10% 절감함"
ANSWERS = [
    json.dumps([{"text": "궤도 틀림 열화 예측 연구", "evidence": []}], ensure_ascii=False),
    json.dumps({"choices": ["applied"], "sentences": [{"text": "응용 사유", "evidence": []}]}),
    json.dumps(
        [
            {"text": METHOD_SENTENCE, "evidence": []},
            {"text": "선행연구는 15% 개선을 보고함", "evidence": ["openalex:W1#0"]},
        ],
        ensure_ascii=False,
    ),
    json.dumps({"choices": ["software"], "sentences": [{"text": "프로그램 제공", "evidence": []}]}),
]


def make_assistant(
    *, blocking: bool = False, answers: list[str] | None = None
) -> ProposalAssistant:
    repo = InMemoryRepository()
    repo.seed(DOCS, CHUNKS)
    if blocking:
        repo.similar = [(DOCS[0], 0.9)]  # own 임계치 0.80 초과, 키워드 조건 없음 → 차단
    own = OwnUnit(org="korail", departments=frozenset({"철도연구원"}))
    rules = LintRules(
        template="test_v1",
        sections=KEYS,
        required_sections=["title", "task_type", "method", "utilization"],
        number_checked=["method"],
        choices={
            "task_type": ChoiceSpec(options="task_types"),
            "utilization": ChoiceSpec(options="utilization", max=10),
            "strategy_alignment": ChoiceSpec(options="strategy_catalog", max=2),
        },
        titles=TITLES,
    )
    gen = GenerateProposal(
        FakeLLM(list(answers or ANSWERS)), repo, FakePromptLibrary(), rules, KEYS
    )
    mgr = RunManager(
        gen,
        InMemoryRunStore(),
        FakeSlot(),
        FakeRunLog(),
        FakeTaskRunner(),
        clock=lambda: "2026-01-01T00:00:00+00:00",
        renderer=FakeRenderer(),
    )
    return ProposalAssistant(
        PrecheckOverlap(repo, own=own), mgr, repo, clock=lambda: "2026-01-01T00:00:00+00:00"
    )
