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


# ── 관련도 하한 (이슈 #2) ──────────────────────────────────
def _scored(repo, scores):
    repo.chunks = [c.model_copy(update={"similarity": scores[c.chunk_id]}) for c in repo.chunks]


async def test_relevance_floor_drops_low_similarity_chunks_from_the_snapshot(req, repo, rules):
    from rra.domain.rules.relevance import RelevanceFloor

    _scored(repo, {"alio:1#0": 0.90, "openalex:W1#0": 0.70})
    gen = make(FakeLLM(), repo, rules)
    gen.relevance = RelevanceFloor(min_similarity=0.79, min_keyword_hits=0)
    snap = await gen.retrieve(req)
    assert [c.chunk_id for c in snap.chunks] == ["alio:1#0"]
    assert snap.dropped_chunks == {"openalex:W1#0": "similarity"}
    assert "openalex:W1#0" not in snap.retrieved_ids  # 폐기된 청크는 근거로 인용할 수 없다


async def test_without_a_floor_the_snapshot_is_unchanged(req, repo, rules):
    _scored(repo, {"alio:1#0": 0.1, "openalex:W1#0": 0.1})
    snap = await make(FakeLLM(), repo, rules).retrieve(req)
    assert len(snap.chunks) == 2 and snap.dropped_chunks == {}


async def test_no_relevant_evidence_skips_llm_for_required_sections_and_warns(req, repo, rules):
    from rra.domain.rules.relevance import RelevanceFloor

    _scored(repo, {"alio:1#0": 0.5, "openalex:W1#0": 0.5})
    llm = FakeLLM([_llm_json("문제 서술", [])])
    gen = make(llm, repo, rules)
    gen.relevance = RelevanceFloor()
    snap = await gen.retrieve(req)
    assert snap.chunks == [] and len(snap.dropped_chunks) == 2
    composed = await gen.compose_section("prior_work", req, snap)
    assert composed.mode == "skipped" and composed.section.sentences == []
    problem = await gen.compose_section("problem", req, snap)  # 근거 선택 섹션은 그대로 생성
    assert problem.mode == "llm" and len(llm.calls) == 1
    draft, problems = gen.finalize("r", req, snap, [problem.section, composed.section])
    assert [(p.section, p.code, p.severity) for p in problems] == [
        ("prior_work", "no_relevant_evidence", "warning")
    ]


async def test_overlap_review_is_exempt_when_overlap_was_checked(req, repo, rules, own):
    from rra.domain.rules.relevance import RelevanceFloor

    _scored(repo, {"alio:1#0": 0.5, "openalex:W1#0": 0.5})
    rules = LintRules(required_sections=["overlap_review"], evidence_required=["overlap_review"])
    gen = GenerateProposal(
        FakeLLM(), repo, FakePromptLibrary(), rules, ["overlap_review"], own=own, check_overlap=True
    )
    gen.relevance = RelevanceFloor()
    snap = await gen.retrieve(req)
    assert snap.chunks == [] and snap.overlap_checked
    assert gen.evidence_skipped(snap) == {}
    composed = await gen.compose_section("overlap_review", req, snap)
    assert composed.mode == "app" and composed.section.sentences  # 앱 확정 문장


async def test_retrieve_searches_wide_and_balances_sources(req, repo, rules):
    from rra.domain.models import Chunk
    from rra.domain.rules.relevance import RelevanceFloor

    repo.chunks = [
        Chunk(chunk_id=f"own:{i}#0", doc_id=f"own:{i}", ordinal=0, text="english", similarity=0.9)
        for i in range(6)
    ] + [
        Chunk(
            chunk_id=f"openalex:W{i}#0",
            doc_id=f"openalex:W{i}",
            ordinal=0,
            text="english",
            similarity=0.85,
        )
        for i in range(6)
    ]
    gen = make(FakeLLM(), repo, rules)
    gen.k = 4
    gen.relevance = RelevanceFloor(min_keyword_hits=0, min_per_source=2, search_multiplier=3)
    snap = await gen.retrieve(req)
    wide = [c for c in repo.calls if c[0] == "hybrid_search"][0]
    assert wide[1]["k"] == 12 and wide[1]["sources"] is None  # k × search_multiplier
    assert sorted(c.doc_id.split(":")[0] for c in snap.chunks) == [
        "openalex",
        "openalex",
        "own",
        "own",
    ]


async def test_retrieve_tops_up_a_source_the_wide_search_crowded_out(req, repo, rules):
    """넓은 검색(k×n) 안에도 영어 논문이 없으면 그 자료원만으로 다시 검색해 보장분을 채운다."""
    from rra.domain.models import Chunk, Document
    from rra.domain.rules.relevance import RelevanceFloor

    def chunk(src, i, sim):
        return Chunk(
            chunk_id=f"{src}:{i}#0", doc_id=f"{src}:{i}", ordinal=0, text="english", similarity=sim
        )

    repo.docs = {
        f"{src}:{i}": Document(doc_id=f"{src}:{i}", source=src, doc_type="paper", title="t")
        for src in ("own", "openalex", "alio")
        for i in range(3)
    }
    # 융합 순위: own 20건 → 그 뒤에야 openalex. alio 는 전부 하한 미달(0.5).
    repo.chunks = (
        [chunk("own", i, 0.9) for i in range(20)]
        + [chunk("openalex", i, 0.85) for i in range(3)]
        + [chunk("alio", i, 0.5) for i in range(3)]
    )
    gen = make(FakeLLM(), repo, rules)
    gen.k = 6
    gen.relevance = RelevanceFloor(min_keyword_hits=0, min_per_source=2, search_multiplier=2)
    snap = await gen.retrieve(req)
    searches = [c[1] for c in repo.calls if c[0] == "hybrid_search"]
    assert searches[0] == {"queries": [req.search_text()], "k": 12, "orgs": None, "sources": None}
    # own 은 이미 충분 → 재검색 없음. alio·openalex 만 자료원 필터로 min_per_source×multiplier.
    assert [(s["sources"], s["k"]) for s in searches[1:]] == [(["alio"], 4), (["openalex"], 4)]
    by = sorted(c.doc_id.split(":")[0] for c in snap.chunks)
    assert by == ["openalex", "openalex", "own", "own", "own", "own"]
    assert [c.chunk_id for c in snap.chunks if c.doc_id.startswith("openalex")] == [
        "openalex:0#0",
        "openalex:1#0",
    ]
    assert len(snap.chunks) == 6
    # 자료원 재검색에서 하한에 걸린 청크도 이유가 남는다
    assert {k: v for k, v in snap.dropped_chunks.items() if k.startswith("alio")} == {
        "alio:0#0": "similarity",
        "alio:1#0": "similarity",
        "alio:2#0": "similarity",
    }


# ── 표 사실 (P2-8) ───────────────────────────────────────
async def test_snapshot_carries_table_facts_and_numbers_lint_uses_them(req, repo, rules):
    from decimal import Decimal

    from rra.application.usecases import generate_proposal as mod
    from rra.domain.models import TableFact

    facts = [
        TableFact(
            item=f"항목{i}",
            value=Decimal(1500 + i),
            value_text=f"1,5{i:02d}",
            doc_id="alio:1",
            unit="대",
            year=2026 if i % 2 else None,
        )
        for i in range(12)
    ]
    await repo.replace_facts("alio:1", facts)
    number_rules = LintRules(
        required_sections=KEYS, evidence_required=["prior_work"], number_checked=["prior_work"]
    )
    gen = make(FakeLLM(), repo, number_rules)
    snap = await gen.retrieve(req)
    assert set(snap.facts) == {"alio:1"} and len(snap.facts["alio:1"]) == 12
    assert snap.facts["alio:1"][0].year == 2026  # 연도·단위 있는 사실을 앞세운다
    # 인용 문서의 표 칸 수치는 근거 있는 수치 — 인용하지 않은 수치만 경고
    llm = FakeLLM(
        [_llm_json("문제", []), _llm_json("설비는 1,501대이고 9,999대 추가", ["alio:1#0"])]
    )
    draft = await make(llm, repo, number_rules)(req)
    codes = [(p.code, p.message) for p in gen.lint_draft(draft, snap)]
    assert codes == [
        ("unsupported_number", "입력·근거에 없는 수치 9,999대: 설비는 1,501대이고 9,999대 추가")
    ]
    # 사실 없는 스냅샷(옛 run)은 종전과 같다
    bare = snap.model_copy(update={"facts": {}})
    [bare_problem] = gen.lint_draft(draft, bare)
    assert bare_problem.message.startswith("입력·근거에 없는 수치 1,501대, 9,999대")
    # 상한: 문서당 MAX_FACTS_PER_DOC
    old = mod.MAX_FACTS_PER_DOC
    mod.MAX_FACTS_PER_DOC = 5
    try:
        capped = await gen.retrieve(req)
    finally:
        mod.MAX_FACTS_PER_DOC = old
    assert len(capped.facts["alio:1"]) == 5 and all(f.year == 2026 for f in capped.facts["alio:1"])
