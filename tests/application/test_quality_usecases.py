"""[Q] 유스케이스 — Q2 OutlineSections, Q1 ClarifyInput, GenerateProposal 의 Q3·Q4·Q6·Q7·Q8,
PrecheckOverlap 의 Q8. 가짜 LLM·저장소만."""

import json

from rra.application.usecases.clarify_input import ClarifyInput, apply_answers, validate_questions
from rra.application.usecases.generate_proposal import EXEMPLAR_DROP, GenerateProposal
from rra.application.usecases.outline import OutlineSections
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Chunk, Document, ProposalRequest, RetrievalSnapshot, Section, Sentence
from rra.domain.models.outline import Outline, SectionPlan
from rra.domain.rules.lint import LintRules
from tests.fakes import FakeLLM, FakePromptLibrary, FakeReranker, InMemoryRepository

KEYS = ["title", "method", "utilization"]
REQ = ProposalRequest(
    current_state="궤도 틀림 반복",
    root_cause="노반",
    limitation="임계치",
    goal="열화 예측",
    constraints="연구기간 1년 이내",
)
EXEMPLAR = Document(
    doc_id="own:ex",
    source="own",
    doc_type="internal_report",
    title="채택 과제",
    body="연구목적: 궤도 틀림을 예측함.\n연구내용: 검측 이력을 분석함.",
    orgs=["korail"],
    text_basis="summary",
    raw={"status": "completed"},
)
CHUNKS = [
    Chunk(chunk_id="openalex:W1#0", doc_id="openalex:W1", ordinal=0, text="track geometry history"),
    Chunk(chunk_id="openalex:W2#0", doc_id="openalex:W2", ordinal=0, text="degradation model"),
    Chunk(chunk_id="own:ex#0", doc_id="own:ex", ordinal=0, text="검측 이력을 분석함."),
]


def repo():
    r = InMemoryRepository()
    r.seed(
        [
            Document(doc_id="openalex:W1", source="openalex", doc_type="paper", title="t1"),
            Document(doc_id="openalex:W2", source="openalex", doc_type="paper", title="t2"),
            EXEMPLAR,
        ],
        CHUNKS,
    )
    return r


def gen(llm, r=None, **kw):
    rules = LintRules(
        template="t", sections=KEYS, required_sections=["title"], number_checked=["method"]
    )
    kw.setdefault("k", 2)
    return GenerateProposal(llm, r or repo(), FakePromptLibrary(), rules, KEYS, **kw)


# ── Q2 설계도 ──────────────────────────────────────────────
async def test_outline_retries_once_with_correction_and_returns_validated_outline():
    llm = FakeLLM(
        [
            "not json",
            json.dumps(
                {
                    "sections": {
                        "method": {"message": "이력 분석", "evidence": ["openalex:W1#0"]},
                        "bogus": {"message": "x"},
                    }
                }
            ),
        ]
    )
    use = OutlineSections(llm, FakePromptLibrary(), KEYS, {"method": "연구방법"})
    snap = RetrievalSnapshot.of("q", CHUNKS[:1])
    outline = await use(REQ, snap)
    assert outline.retries == 1 and [s.key for s in outline.sections] == ["method"]
    assert outline.discarded == [{"key": "bogus", "reason": "unknown_section"}]
    assert "[형식 교정" in llm.calls[1] and "method: 연구방법" in llm.calls[0]
    assert llm.systems[0].startswith("OUTLINE")


async def test_outline_gives_up_after_retry_and_excludes_app_sections():
    llm = FakeLLM(["[]", "{}"])
    use = OutlineSections(llm, FakePromptLibrary(), [*KEYS, "overlap_review"], {})
    assert await use(REQ, RetrievalSnapshot.of("q", [])) is None
    assert "overlap_review" not in llm.calls[0] and len(llm.calls) == 2


# ── Q1 보강 질문 ──────────────────────────────────────────
async def test_clarify_validates_questions_and_applies_answers_as_supplement():
    llm = FakeLLM(
        ['{"questions": ["대상 노선은?", "日本語?", "대상 노선은?", "", 5, "예산은?", "기간은?"]}']
    )
    questions = await ClarifyInput(llm, FakePromptLibrary())(REQ)
    assert questions == ["대상 노선은?", "예산은?", "기간은?"]
    assert validate_questions("nope") == [] and validate_questions({"questions": "하나?"}) == [
        "하나?"
    ]
    req2 = apply_answers(REQ, {"대상 노선은?": "경부선", "예산은?": "  "})
    assert req2.supplement == "대상 노선은?: 경부선" and REQ.supplement == ""
    assert (
        apply_answers(req2, {"기간은?": "1년"}).supplement == "대상 노선은?: 경부선\n기간은?: 1년"
    )
    assert apply_answers(REQ, {}) is REQ


# ── Q8 reranker ───────────────────────────────────────────
async def test_retrieve_reranks_before_cutting_to_k_and_section_search_uses_it_too():
    rr = FakeReranker()
    g = gen(FakeLLM(), reranker=rr, section_search=True)
    snap = await g.retrieve(REQ)
    assert [c.chunk_id for c in snap.chunks] == ["openalex:W2#0", "openalex:W1#0"]  # 뒤집힌 상위 2
    snap = await g.retrieve_sections(REQ, snap)
    assert set(snap.section_chunks) == {"method", "utilization"}  # 제목은 전체 근거
    assert snap.section_chunks["method"] == ["own:ex#0", "openalex:W2#0", "openalex:W1#0"]
    assert {c.chunk_id for c in snap.chunks} == {
        c.chunk_id for c in CHUNKS
    }  # 새 청크는 스냅샷에 더해짐
    assert len(rr.calls) == 3 and all(q for q, _ in rr.calls)
    assert [c.chunk_id for c in snap.chunks_for("title")] == [c.chunk_id for c in snap.chunks]


async def test_section_search_is_a_noop_when_disabled():
    g = gen(FakeLLM())
    snap = await g.retrieve(REQ)
    assert (await g.retrieve_sections(REQ, snap)).section_chunks == {}


async def test_precheck_with_reranker_widens_then_reranks_and_keeps_similarity():
    r = InMemoryRepository()
    docs = [
        Document(doc_id=f"openalex:W{i}", source="openalex", doc_type="paper", title=f"t{i}")
        for i in range(4)
    ]
    r.similar = [(d, 0.9 - i * 0.1) for i, d in enumerate(docs)]
    rr = FakeReranker()
    alerts = await PrecheckOverlap(r, k=2, reranker=rr, rerank_multiplier=2)(REQ)
    assert r.calls[-1][1]["k"] == 4 and rr.calls == [(REQ.search_text(), 4)]
    assert [a.doc_id for a in alerts] == ["openalex:W3", "openalex:W2"] or {
        a.doc_id for a in alerts
    } == {"openalex:W3", "openalex:W2"}
    assert {a.similarity for a in alerts} == {0.6, 0.7}


# ── Q4 본보기 ──────────────────────────────────────────────
async def test_exemplars_are_picked_in_retrieve_and_copied_sentences_are_dropped():
    r = repo()
    r.similar = [(EXEMPLAR, 0.93)]
    llm = FakeLLM(
        [
            json.dumps(
                [
                    {"text": "이력을 분석해 열화를 예측함.", "evidence": ["openalex:W1#0"]},
                    {"text": "검측 이력을 분석함.", "evidence": []},  # 본보기 문장 그대로
                    {"text": "본보기 과제를 근거로 씀.", "evidence": ["own:ex#0"]},  # 인용은 허용
                ],
                ensure_ascii=False,
            )
        ]
    )
    g = gen(llm, r, exemplars=True, check_overlap=False, k=3)
    snap = await g.retrieve(REQ)
    assert snap.exemplars[0]["doc_id"] == "own:ex" and not snap.overlap_checked
    composed = await g.compose_section("method", REQ, snap)
    assert [s.text for s in composed.section.sentences] == [
        "이력을 분석해 열화를 예측함.",
        "본보기 과제를 근거로 씀.",  # 검색 근거에 든 본보기 doc 인용은 막지 않는다
    ]
    assert sum(EXEMPLAR_DROP in d for d in composed.dropped) == 1
    assert (
        "[본보기" in llm.calls[0]
        and "own:ex" not in llm.calls[0].split("[본보기")[1].split("[자료]")[0]
    )


async def test_exemplars_exclude_golden_answer_doc():
    r = repo()
    r.similar = [(EXEMPLAR, 0.93)]
    g = gen(FakeLLM(), r, exemplars=True, exemplar_exclude=frozenset({"own:ex"}))
    assert (await g.retrieve(REQ)).exemplars == []


# ── Q2·Q7 프롬프트 ────────────────────────────────────────
async def test_compose_prompt_carries_outline_plan_summary_and_candidate_a():
    llm = FakeLLM(["[]", "[]"])
    g = gen(llm)
    snap = await g.retrieve(REQ)
    outline = Outline(
        sections=[
            SectionPlan(
                key="method", message="이력 분석", evidence=["openalex:W1#0"], links=["title"]
            ),
            SectionPlan(key="title", message="예측 연구"),
        ]
    )
    await g.compose_section("method", REQ, snap, outline=outline)
    p = llm.calls[0]
    assert "[이 섹션의 설계" in p and "이력 분석" in p and "우선 근거: openalex:W1#0" in p
    assert "[전체 설계 요약" in p and "title: 예측 연구" in p
    a = Section(key="method", sentences=[Sentence(text="후보 A 문장임.")])
    await g.compose_section("method", REQ, snap, candidate=a)
    assert "[후보 B 작성]" in llm.calls[1] and "- 후보 A 문장임." in llm.calls[1]
    assert "[후보 B" not in p


# ── Q6 규칙 검사 ──────────────────────────────────────────
def test_finalize_unifies_endings_removes_duplicates_and_warns_the_rest():
    g = gen(FakeLLM())
    snap = RetrievalSnapshot.of("q", CHUNKS[:1])
    sections = [
        Section(key="title", sentences=[Sentence(text="궤도 틀림 예측 연구")]),
        Section(
            key="method",
            sentences=[
                Sentence(text="이력을 분석한다.", evidence=["openalex:W1#0"]),
                Sentence(
                    text="이력을 분석함", evidence=["openalex:W1#0"]
                ),  # 어미 통일 뒤 완전 중복
                Sentence(text="2차년도에 현장 검증을 하는 것이다."),  # 연차 불일치 + 서술형(통일됨)
                Sentence(text="긴 문장 " * 40),
            ],
        ),
        Section(key="utilization", sentences=[]),
    ]
    draft, problems = g.finalize("r", REQ, snap, sections)
    texts = [s.text for s in draft.section("method").sentences]
    assert texts[0] == "이력을 분석함." and len(texts) == 3
    codes = sorted((p.code, p.sentence) for p in problems if p.severity == "warning")
    assert ("period_mismatch", 1) in codes and ("long_sentence", 2) in codes
    assert all(
        p.severity == "warning" for p in problems if p.code in ("period_mismatch", "long_sentence")
    )
    g.rule_check = False
    draft2, _ = g.finalize("r", REQ, snap, sections)
    assert [s.text for s in draft2.section("method").sentences][0] == "이력을 분석한다."


# ── 근거 구성 규칙(retrieval_mix) ──────────────────────────
async def test_section_search_keeps_scholarly_minimum_and_filters_policy_docs():
    from rra.domain.rules.retrieval_mix import RetrievalMix, SectionMix

    r = InMemoryRepository()
    docs = [
        Document(doc_id=f"own:{i}", source="own", doc_type="rnd_project", title=f"o{i}")
        for i in range(6)
    ]
    docs += [
        Document(doc_id=f"openalex:W{i}", source="openalex", doc_type="paper", title=f"p{i}")
        for i in range(3)
    ]
    docs += [
        Document(doc_id="alio:pol", source="alio", doc_type="internal_report", title="policy-like")
    ]
    chunks = [
        Chunk(chunk_id=f"{d.doc_id}#0", doc_id=d.doc_id, ordinal=0, text=f"궤도 {d.title}")
        for d in docs
    ]
    r.seed(docs, chunks)
    mix = RetrievalMix(
        section_min_per_source=1,
        sections={
            "method": SectionMix(allow=("paper", "rnd_project"), min_scholarly=2),
            "title": SectionMix(allow=("paper",)),
        },
        overlap_exclude=("internal_report",),
    )
    g = gen(FakeLLM(), r, section_search=True, section_k=3, mix=mix, k=4)
    snap = await g.retrieve(REQ)
    assert set(snap.doc_types) == {c.doc_id for c in snap.chunks}  # 스냅샷 문서마다 doc_type
    snap = await g.retrieve_sections(REQ, snap)
    method_ids = snap.section_chunks["method"]
    types = [snap.doc_types[i.split("#")[0]] for i in method_ids]
    assert (
        types.count("paper") >= 2 and "internal_report" not in types
    )  # 논문 최소 2 + 허용 밖 제외
    assert [snap.doc_types[c.doc_id] for c in g.chunks_for("title", snap)] == ["paper"] * 3
    # 유사과제 판정 후보에서 제외 doc_type 은 빠진다
    r.similar = [(docs[-1], 0.95), (docs[0], 0.9)]
    g2 = gen(FakeLLM(), r, check_overlap=True, mix=mix, k=4)
    snap2 = await g2.retrieve(REQ)
    assert [a.doc_id for a in snap2.overlap] == ["own:0"]


async def test_precheck_excludes_overlap_exclude_types():
    from rra.domain.rules.retrieval_mix import RetrievalMix

    r = InMemoryRepository()
    pol = Document(doc_id="alio:p", source="alio", doc_type="internal_report", title="정책")
    own = Document(doc_id="own:1", source="own", doc_type="rnd_project", title="과제")
    r.similar = [(pol, 0.95), (own, 0.9)]
    mix = RetrievalMix(overlap_exclude=("internal_report",))
    assert [a.doc_id for a in await PrecheckOverlap(r, mix=mix)(REQ)] == ["own:1"]
    rr = FakeReranker()
    assert [a.doc_id for a in await PrecheckOverlap(r, mix=mix, reranker=rr)(REQ)] == ["own:1"]
