"""generate_proposal — 단계(retrieve·compose_section·finalize)와 한 번에 도는 조합. FakeLLM 만."""

import json

import pytest

from rra.application.usecases.generate_proposal import DraftInvalid, GenerateProposal
from rra.domain.rules.lint import LintRules
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

KEYS = ["problem", "prior_work"]


def _llm_json(text, ev):
    return json.dumps([{"text": text, "evidence": ev}], ensure_ascii=False)


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    r.upsert(docs, chunks)
    return r


@pytest.fixture
def rules():
    return LintRules(required_sections=KEYS, evidence_required=["prior_work"])


def make(llm, repo, rules, prompts=None):
    return GenerateProposal(llm, repo, prompts or FakePromptLibrary(), rules, KEYS)


async def test_happy_path(req, repo, rules):
    llm = FakeLLM([_llm_json("문제 서술", []), _llm_json("선행연구 요약", ["alio:1#0"])])
    prompts = FakePromptLibrary()
    draft = await make(llm, repo, rules, prompts)(req)
    assert prompts.asked == KEYS  # 섹션 프롬프트를 포트로만 가져온다
    assert "[problem] 섹션 작성 지시" in llm.calls[0]
    assert draft.section("prior_work").sentences[0].evidence == ["alio:1#0"]


async def test_injected_evidence_is_dropped_and_lint_fails(req, repo, rules):
    llm = FakeLLM([_llm_json("문제", []), _llm_json("주입된 문장", ["evil:1"])])
    with pytest.raises(DraftInvalid) as e:
        await make(llm, repo, rules)(req)
    assert e.value.dropped and e.value.problems[0].code == "missing"


async def test_non_json_output_rejected(req, repo, rules):
    llm = FakeLLM(["자유 텍스트 응답", "또 자유 텍스트"])
    with pytest.raises(DraftInvalid):
        await make(llm, repo, rules)(req)


# ── 단계 ─────────────────────────────────────────────────
def test_retrieve_snapshot_fixes_the_evidence_set(req, repo, rules):
    snap = make(FakeLLM(), repo, rules).retrieve(req)
    assert snap.retrieved_ids == {"alio:1#0", "alio:1", "openalex:W1#0", "openalex:W1"}
    assert len(snap.query_hash) == 64 and "궤도" not in snap.query_hash


async def test_compose_section_enforces_evidence_per_section(req, repo, rules):
    uc = make(
        FakeLLM(
            [
                json.dumps(
                    [
                        {"text": "근거 있음", "evidence": ["alio:1#0"]},
                        {"text": "근거 없음", "evidence": []},
                        {"text": "위조 근거", "evidence": ["evil:9"]},
                    ],
                    ensure_ascii=False,
                )
            ]
        ),
        repo,
        rules,
    )
    composed = await uc.compose_section("prior_work", req, uc.retrieve(req))
    assert [s.text for s in composed.section.sentences] == ["근거 있음"]
    assert len(composed.dropped) == 2
    assert len(composed.prompt_hash) == 16


async def test_non_required_section_keeps_proposer_input_sentences(req, repo, rules):
    uc = make(FakeLLM([_llm_json("제안자 입력 기반 문장", [])]), repo, rules)
    composed = await uc.compose_section("problem", req, uc.retrieve(req))
    assert composed.section.sentences[0].evidence == [] and composed.dropped == []


async def test_prompt_hash_changes_with_prompt_not_with_input(req, repo, rules):
    uc = make(FakeLLM([_llm_json("a", []), _llm_json("b", [])]), repo, rules)
    snap = uc.retrieve(req)
    h1 = (await uc.compose_section("problem", req, snap)).prompt_hash
    other = req.model_copy(update={"goal": "완전히 다른 목표"})
    h2 = (await uc.compose_section("problem", other, snap)).prompt_hash
    assert h1 == h2


def test_finalize_lints(req, repo, rules):
    uc = make(FakeLLM(), repo, rules)
    draft, problems = uc.finalize("r1", req, uc.retrieve(req), [])
    assert draft.run_id == "r1" and {p.code for p in problems} == {"missing"}


async def test_bare_fence_output_is_parsed_and_status_recorded(req, repo, rules):
    raw = "```\n" + _llm_json("선행", ['<doc id="alio:1#0">']) + "\n```"
    uc = make(FakeLLM([raw]), repo, rules)
    composed = await uc.compose_section("prior_work", req, uc.retrieve(req))
    assert composed.parse.status == "ok" and composed.parse.raw_chars == len(raw)
    assert composed.section.sentences[0].evidence == ["alio:1#0"]


async def test_parse_failure_reason_is_kept(req, repo, rules):
    uc = make(FakeLLM(["결과:\n```json\n[]\n```"]), repo, rules)
    composed = await uc.compose_section("problem", req, uc.retrieve(req))
    assert composed.parse.status == "fence" and composed.section.sentences == []
