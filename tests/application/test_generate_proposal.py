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
    r.seed(docs, chunks)
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
async def test_retrieve_snapshot_fixes_the_evidence_set(req, repo, rules):
    snap = await make(FakeLLM(), repo, rules).retrieve(req)
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
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert [s.text for s in composed.section.sentences] == ["근거 있음"]
    assert len(composed.dropped) == 2
    assert len(composed.prompt_hash) == 16


async def test_non_required_section_keeps_proposer_input_sentences(req, repo, rules):
    uc = make(FakeLLM([_llm_json("제안자 입력 기반 문장", [])]), repo, rules)
    composed = await uc.compose_section("problem", req, await uc.retrieve(req))
    assert composed.section.sentences[0].evidence == [] and composed.dropped == []


async def test_prompt_hash_changes_with_prompt_not_with_input(req, repo, rules):
    uc = make(FakeLLM([_llm_json("a", []), _llm_json("b", [])]), repo, rules)
    snap = await uc.retrieve(req)
    h1 = (await uc.compose_section("problem", req, snap)).prompt_hash
    other = req.model_copy(update={"goal": "완전히 다른 목표"})
    h2 = (await uc.compose_section("problem", other, snap)).prompt_hash
    assert h1 == h2


async def test_finalize_lints(req, repo, rules):
    uc = make(FakeLLM(), repo, rules)
    draft, problems = uc.finalize("r1", req, await uc.retrieve(req), [])
    assert draft.run_id == "r1" and {p.code for p in problems} == {"missing"}


async def test_bare_fence_output_is_parsed_and_status_recorded(req, repo, rules):
    raw = "```\n" + _llm_json("선행", ['<doc id="alio:1#0">']) + "\n```"
    uc = make(FakeLLM([raw]), repo, rules)
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.parse.status == "ok" and composed.parse.raw_chars == len(raw)
    assert composed.section.sentences[0].evidence == ["alio:1#0"]


async def test_parse_failure_reason_is_kept(req, repo, rules):
    llm = FakeLLM(["결과:\n```json\n[]\n```", "두 번째도 설명:\n```json\n[]\n```"])
    uc = make(llm, repo, rules)
    composed = await uc.compose_section("problem", req, await uc.retrieve(req))
    assert composed.parse.status == "fence" and composed.section.sentences == []
    assert (
        composed.retries == 1 and composed.first_parse.status == "fence"
    )  # 두 번 실패 → 기존 처리
    assert len(llm.calls) == 2 and "[형식 교정" in llm.calls[1] and "코드블록" in llm.calls[1]


async def test_schema_error_is_retried_once_with_a_correction_hint(req, repo, rules):
    """첫 응답 스키마 오류 → 교정 문구를 붙여 같은 섹션 1회 재요청 → 성공. 재요청 횟수 기록."""
    llm = FakeLLM(['{"text": "객체 하나"}', _llm_json("선행", ['<doc id="alio:1#0">'])])
    uc = make(llm, repo, rules)
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.parse.ok and composed.retries == 1
    assert composed.first_parse.status == "schema" and not composed.first_parse.ok
    assert composed.section.sentences[0].text == "선행"
    assert llm.calls[1].startswith(llm.calls[0])  # 같은 프롬프트 + 교정 문구
    assert "객체 배열" in llm.calls[1] and "[형식 교정" in llm.calls[1]
    ok = FakeLLM([_llm_json("선행", ['<doc id="alio:1#0">'])])
    good = await make(ok, repo, rules).compose_section("prior_work", req, await uc.retrieve(req))
    assert good.retries == 0 and len(ok.calls) == 1  # 정상 응답은 재요청하지 않는다


async def test_choice_section_prompt_has_a_shape_example_with_fake_values(req, repo):
    """선택형 프롬프트의 모양 예시 1개 — 값은 가상이라 그대로 쓰면 대조에서 걸린다."""
    from rra.application.usecases.generate_proposal import CHOICE_EXAMPLE
    from rra.domain.rules.lint import ChoiceSpec, LintRules

    rules = LintRules(
        required_sections=["task_type"], choices={"task_type": ChoiceSpec(options="task_types")}
    )
    llm = FakeLLM([CHOICE_EXAMPLE])  # 모델이 예시를 그대로 베낀 경우
    uc = make(llm, repo, rules)
    uc.section_keys = ["task_type"]
    composed = await uc.compose_section("task_type", req, await uc.retrieve(req))
    assert "[출력 모양 예시" in llm.calls[0] and CHOICE_EXAMPLE in llm.calls[0]
    assert (
        "예시-id" not in llm.calls[0].split("[선택지")[1].split("[출력 모양 예시")[0]
    )  # 실제 선택지가 아니다
    assert composed.section.choices == []  # 가상 선택지는 버려진다
    assert composed.section.sentences == [] or all(
        s.evidence == [] for s in composed.section.sentences
    )  # 가짜 근거 id 는 근거 대조에서 걸린다
