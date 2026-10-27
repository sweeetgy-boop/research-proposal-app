"""정책·보도자료(korail_web)는 유사과제 판정에 쓰지 않는다 (domain/rules/retrieval_scope)."""

from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Document
from rra.domain.rules.retrieval_scope import OVERLAP_EXCLUDED_DOC_TYPES, overlap_candidates
from tests.fakes import InMemoryRepository

POLICY = Document(
    doc_id="korail_web:abc",
    source="korail_web",
    doc_type="policy",
    title="중장기 경영목표",
    body="데이터기반 유지보수 첨단화 궤도 틀림 상시 감지",
    orgs=["korail"],
)
NEWS = POLICY.model_copy(update={"doc_id": "korail_web:def", "doc_type": "korail_news"})


def test_overlap_candidates_drops_policy_and_news_only():
    paper = Document(doc_id="openalex:W1", source="openalex", doc_type="paper", title="t")
    hits = [(POLICY, 0.99), (paper, 0.9), (NEWS, 0.95)]
    assert overlap_candidates(hits) == [(paper, 0.9)]
    assert OVERLAP_EXCLUDED_DOC_TYPES == {"policy", "korail_news"}


async def test_precheck_ignores_policy_documents_even_when_most_similar(req, docs, own):
    repo = InMemoryRepository()
    repo.similar = [(POLICY, 0.99), (NEWS, 0.98), (docs[0], 0.81)]
    alerts = await PrecheckOverlap(repo, own=own)(req)
    assert [a.doc_id for a in alerts] == ["alio:1"]


async def test_generate_overlap_check_ignores_policy_documents(req, docs, chunks, own):
    from rra.application.usecases.generate_proposal import GenerateProposal
    from rra.domain.rules.lint import LintRules
    from tests.fakes import FakeLLM, FakePromptLibrary

    repo = InMemoryRepository()
    repo.seed(docs, chunks)
    repo.similar = [(POLICY, 0.99), (docs[0], 0.81)]
    rules = LintRules(required_sections=["overlap_review"], evidence_required=["overlap_review"])
    gen = GenerateProposal(
        FakeLLM(), repo, FakePromptLibrary(), rules, ["overlap_review"], own=own, check_overlap=True
    )
    snapshot = await gen.retrieve(req)
    assert [a.doc_id for a in snapshot.alerts] == ["alio:1"]
