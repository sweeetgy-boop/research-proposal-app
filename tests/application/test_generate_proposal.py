import json

import pytest

from rra.application.usecases.generate_proposal import DraftInvalid, GenerateProposal
from rra.domain.rules.lint import LintRules
from tests.fakes import FakeLLM, FakeRenderer, FakeRunLog, InMemoryRepository


def _llm_json(text, ev):
    return json.dumps([{"text": text, "evidence": ev}], ensure_ascii=False)


@pytest.fixture
def usecase(docs, chunks):
    repo = InMemoryRepository()
    repo.upsert(docs, chunks)
    rules = LintRules(required_sections=["problem", "prior_work"], evidence_required=["prior_work"])
    return repo, rules


async def test_happy_path(req, usecase):
    repo, rules = usecase
    llm = FakeLLM([_llm_json("문제 서술", []), _llm_json("선행연구 요약", ["alio:1#0"])])
    log = FakeRunLog()
    uc = GenerateProposal(llm, repo, FakeRenderer(), log, rules, ["problem", "prior_work"])
    draft, out = await uc(req)
    assert draft.section("prior_work").sentences[0].evidence == ["alio:1#0"]
    assert b"prior_work" in out
    manifest = log.records[0][1]
    assert "query_hash" in manifest and "궤도" not in json.dumps(manifest)  # I: 원문 미기록


async def test_injected_evidence_is_dropped_and_lint_fails(req, usecase):
    repo, rules = usecase
    llm = FakeLLM([_llm_json("문제", []), _llm_json("주입된 문장", ["evil:1"])])
    uc = GenerateProposal(llm, repo, FakeRenderer(), FakeRunLog(), rules, ["problem", "prior_work"])
    with pytest.raises(DraftInvalid) as e:
        await uc(req)
    assert e.value.dropped and e.value.problems[0].code == "missing"


async def test_non_json_output_rejected(req, usecase):
    repo, rules = usecase
    llm = FakeLLM(["자유 텍스트 응답", "또 자유 텍스트"])
    uc = GenerateProposal(llm, repo, FakeRenderer(), FakeRunLog(), rules, ["problem", "prior_work"])
    with pytest.raises(DraftInvalid):
        await uc(req)
