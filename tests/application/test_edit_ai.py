"""작성·편집 AI (레인 B, 2026-10-28) — Argon 먼저 호출 순서·정책적 중요도 작성안·보강 질문·보완
질문·
변경 세기. LLM 은 FakeLLM (외부 호출 없음)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from rra.application.usecases.argon_first import ArgonFirst
from rra.application.usecases.clarify_input import ClarifyInput, gaps
from rra.application.usecases.policy_cards import PolicyCards
from rra.application.usecases.section_questions import SectionQuestions
from rra.domain.models import (
    Chunk,
    Document,
    DraftVersion,
    EvidenceDecision,
    Figure,
    PolicyChoice,
    PolicySentence,
    PolicySource,
    ProposalRequest,
    Section,
    Sentence,
)
from rra.domain.rules.change_count import base_version, count_changes
from rra.domain.rules.policy_cards import (
    apply_policy_choice,
    basis_text,
    choice_section,
    edited_choice,
    group_passages,
    merge_cards,
    needs_policy_basis,
    validate_sentences,
    verify_sources,
)
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
)


def _src(doc_id: str, source: str, quote: str) -> PolicySource:
    return PolicySource(
        chunk_id=f"{doc_id}#0", doc_id=doc_id, source=source, title=doc_id, quote=quote
    )


PASSAGES = [
    _src("molit:a", "molit", "제4차 국가철도망 구축계획은 노후 궤도 보수를 강화함."),
    _src("molit:b", "molit", "철도 안전 투자를 2030년까지 확대함."),
    _src("molit:c", "molit", "세 번째 정부 구간."),
    _src("korail_web:a", "korail_web", "공사는 데이터 기반 궤도 유지보수를 추진함."),
    _src("bai:a", "bai", "감사원은 궤도 보수가 주기 위주라고 지적함."),
    _src("korail_web:b", "korail_web", "지역 균형발전과 교통약자 접근성을 높임."),
]


# ── 작성안 묶기·검증 (순수) ───────────────────────────────
def test_group_passages_one_doc_per_card_and_regional_from_leftovers():
    groups = group_passages(PASSAGES)
    assert list(groups) == ["government", "company", "audit"]
    assert [p.doc_id for p in groups["government"]] == ["molit:a", "molit:b"]  # 방향당 2구간
    assert [p.doc_id for p in groups["company"]] == ["korail_web:a", "korail_web:b"]
    docs = [p.doc_id for v in groups.values() for p in v]
    assert len(docs) == len(set(docs))  # 근거 겹침 없음
    # 방향당 1구간이면 남은 "지역 균형발전" 구간이 지역·사회 정책 안이 된다
    one = group_passages(PASSAGES, per_card=1)
    assert list(one) == ["government", "company", "audit", "regional"]
    assert [p.doc_id for p in one["regional"]] == ["korail_web:b"]
    # [다른 안 보기] — 본 문서를 빼면 남은 것만
    again = group_passages(PASSAGES, exclude_docs=docs)
    assert [p.doc_id for v in again.values() for p in v] == ["molit:c"]


def test_regional_card_only_when_vocabulary_matches():
    only = [_src("korail_web:x", "korail_web", "지역 소멸 대응과 교통약자 이동권을 높임.")]
    assert list(group_passages(only, per_card=1)) == ["company"]  # 공사 자료는 먼저 공사 전략으로
    left = [
        _src("korail_web:x", "korail_web", "공사 전략 구간."),
        _src("korail_web:y", "korail_web", "지역 균형발전과 접근성을 높임."),
    ]
    groups = group_passages(left, per_card=1)
    assert [p.doc_id for p in groups["regional"]] == ["korail_web:y"]


def test_validate_sentences_quote_bound_and_policy_name_rule():
    sources = PASSAGES[:2]
    raw = [
        {
            "text": "○ 노후 궤도 보수 강화 방향과 이어짐.",
            "evidence": ["molit:a#0"],
        },  # 통과, 기호 뗌
        {"text": "제5차 국가철도망 구축계획에 부합함.", "evidence": ["molit:a#0"]},  # 지어낸 정책명
        {"text": "철도 안전 투자를 2035년까지 확대함.", "evidence": ["molit:b#0"]},  # 지어낸 연도
        {"text": "근거 없는 문장임.", "evidence": ["alio:x#0"]},  # 범위 밖 근거
        {"text": "제4차 국가철도망 구축계획의 궤도 보수 강화와 이어짐.", "evidence": ["molit:a#0"]},
        {"text": "日本語 문장.", "evidence": ["molit:a#0"]},
    ]
    kept, dropped = validate_sentences(raw, sources, REQ)
    assert [k.text for k in kept] == [
        "노후 궤도 보수 강화 방향과 이어짐.",
        "제4차 국가철도망 구축계획의 궤도 보수 강화와 이어짐.",
    ]
    assert dropped == ["ungrounded", "ungrounded", "evidence_out_of_range", "foreign_script"]


def test_choice_helpers_merge_edit_basis_and_section():
    from rra.domain.models import PolicyCard

    a = PolicyCard(
        id="government-1",
        direction="government",
        direction_label="정부 계획",
        sentences=[PolicySentence(text="정부 방향과 이어짐.", evidence=["molit:a#0"])],
        sources=[PASSAGES[0]],
    )
    b = PolicyCard(
        id="audit-1",
        direction="audit",
        direction_label="감사 지적·현안",
        sentences=[
            PolicySentence(text="정부 방향과 이어짐.", evidence=["molit:a#0"]),
            PolicySentence(text="감사 지적을 해소함.", evidence=["bai:a#0"]),
        ],
        sources=[PASSAGES[4]],
    )
    merged = merge_cards(a, b)
    assert merged.mode == "merged" and merged.card_ids == ["government-1", "audit-1"]
    assert [s.text for s in merged.sentences] == ["정부 방향과 이어짐.", "감사 지적을 해소함."]
    assert {s.doc_id for s in merged.sources} == {"molit:a", "bai:a"}
    edited = edited_choice(merged, "○ 정부 방향과 이어짐.\n새로 쓴 문장임.")
    assert edited.mode == "edited"
    assert edited.sentences[0].evidence == ["molit:a#0"]  # 같은 문장은 근거를 이어받는다
    assert edited.sentences[1].evidence == []
    assert edited_choice(None, "직접 쓴 정책 근거임.", manual=True).mode == "manual"
    text = basis_text(merged)
    assert "정부 방향과 이어짐." in text and "(근거: molit:a" in text
    req = apply_policy_choice(REQ, merged)
    assert req.policy_basis == text and req.policy_choice == merged
    assert (
        apply_policy_choice(REQ.model_copy(update={"policy_basis": "입력"}), merged).policy_basis
        == "입력"
    )
    assert "policy_choice" not in req.prompt_view()  # 프롬프트에는 요지(policy_basis)만
    sec = choice_section(merged, {"molit:a#0"})
    assert sec.sentences[0].origin == "proposer_input" and sec.sentences[1].evidence == []
    assert needs_policy_basis(REQ) and not needs_policy_basis(req)
    assert needs_policy_basis(REQ.model_copy(update={"policy_choice": PolicyChoice(mode="none")}))


def test_verify_sources_keeps_only_quotes_found_in_stored_policy_documents():
    doc = Document(
        doc_id="molit:a",
        source="molit",
        doc_type="policy",
        title="계획",
        body="… 제4차 국가철도망 구축계획은 노후 궤도 보수를 강화함. …",
    )
    paper = Document(doc_id="openalex:w", source="openalex", doc_type="paper", title="p", body="x")
    choice = PolicyChoice(
        mode="card",
        sources=[
            PASSAGES[0],
            _src("molit:a", "molit", "본문에 없는 인용"),
            _src("openalex:w", "openalex", "x"),
            _src("molit:zz", "molit", "없는 문서"),
        ],
    )
    out = verify_sources(choice, {"molit:a": doc, "openalex:w": paper, "molit:zz": None})
    assert [c.chunk_id for c in out] == ["molit:a#0"]


# ── 작성안 유스케이스 ───────────────────────────────────
def _repo():
    repo = InMemoryRepository()
    rows = [
        ("molit:p", "molit", "policy", "정부는 노후 궤도의 검측 고도화와 보수 체계 개선을 추진함."),
        ("korail_web:s", "korail_web", "policy", "공사는 데이터 기반 궤도 유지보수로 안전을 높임."),
        ("korail_web:n", "korail_web", "korail_news", "보도자료: 궤도 보수 행사 개최."),
        ("bai:x", "bai", "audit", "감사원은 궤도 틀림 보수가 주기 위주라고 지적함."),
    ]
    repo.seed(
        [
            Document(
                doc_id=d, source=s, doc_type=t, title=f"{d} 제목", body=b, pub_date=date(2025, 1, 1)
            )
            for d, s, t, b in rows
        ],
        [Chunk(chunk_id=f"{d}#0", doc_id=d, ordinal=0, text=b) for d, _, _, b in rows],
    )
    return repo


def _cards_answer(*dirs: str, text: str = "인용 자료의 방향과 본 제안이 이어짐.") -> str:
    ids = {"government": "molit:p#0", "company": "korail_web:s#0", "audit": "bai:x#0"}
    return json.dumps(
        {
            "cards": [
                {"direction": d, "sentences": [{"text": text, "evidence": [ids[d]]}]} for d in dirs
            ]
        },
        ensure_ascii=False,
    )


async def test_policy_cards_argon_first_validated_and_disjoint():
    argon = FakeLLM([_cards_answer("government", "company", "audit")])
    local = FakeLLM()
    uc = PolicyCards(_repo(), ArgonFirst(local, argon))
    result = await uc(REQ)
    assert result.status == "ok" and [c.direction for c in result.cards] == [
        "government",
        "company",
        "audit",
    ]
    assert local.calls == []  # Argon 이 답하면 로컬을 부르지 않는다
    assert all(c.sources[0].doc_id != "korail_web:n" for c in result.cards)  # 보도자료 제외
    assert result.record["model"] == "argon" and result.record["fallback"] is False
    prompt = argon.calls[0]
    assert prompt.startswith("[정책적 중요도 작성안]") and '<doc id="bai:x#0">' in prompt


async def test_policy_cards_fall_back_to_local_then_report_reasons():
    local = FakeLLM([_cards_answer("company")])
    uc = PolicyCards(_repo(), ArgonFirst(local, FakeLLM(fail_at={0})))
    result = await uc(REQ)
    assert [c.direction for c in result.cards] == ["company"]
    assert result.record["fallback"] is True and result.record["model"] == "local"
    # 둘 다 실패 → failed + 사유
    both = PolicyCards(_repo(), ArgonFirst(FakeLLM(fail_at={0}), FakeLLM(fail_at={0})))
    r = await both(REQ)
    assert r.cards == [] and r.status == "failed" and r.reason == "error"
    # 규칙에 걸러짐 (지어낸 정책명) — 로컬도 같은 답이면 filtered
    bad = _cards_answer("government", text="제9차 철도 기본계획에 부합함.")
    r = await PolicyCards(_repo(), ArgonFirst(FakeLLM([bad]), FakeLLM([bad])))(REQ)
    assert r.status == "filtered" and r.reason == "filtered" and r.dropped >= 1
    # 관련 구간 없음 → 해당 없음 (모델을 부르지 않는다)
    empty_llm = FakeLLM()
    r = await PolicyCards(InMemoryRepository(), ArgonFirst(None, empty_llm))(REQ)
    assert r.status == "empty" and empty_llm.calls == []


async def test_policy_polish_keeps_names_from_proposer_text_or_quotes_only():
    uc = PolicyCards(
        _repo(),
        ArgonFirst(
            None,
            FakeLLM(
                [
                    json.dumps(
                        {
                            "sentences": [
                                {"text": "궤도 안전 방향과 이어짐.", "evidence": []},
                                {"text": "제7차 철도안전 종합계획에 부합함.", "evidence": []},
                            ]
                        },
                        ensure_ascii=False,
                    )
                ]
            ),
        ),
    )
    choice = PolicyChoice(
        mode="card", sources=[_src("molit:p", "molit", "정부는 노후 궤도의 검측 고도화를 추진함.")]
    )
    out = await uc.polish(REQ, choice, "궤도 안전 방향과 이어짐")
    assert out.choice is not None and [s.text for s in out.choice.sentences] == [
        "궤도 안전 방향과 이어짐."
    ]
    assert out.dropped == 1 and out.choice.mode == "edited"


# ── 보강 질문 ─────────────────────────────────────────
def _clarify(argon=None, local=None):
    return ClarifyInput(local, FakePromptLibrary(), argon=argon)


Q2 = json.dumps(
    {
        "questions": [
            {"topic": "target", "question": "적용 노선은 어디입니까?"},
            {"topic": "metric", "question": "목표 정확도는?"},
            {"topic": "policy", "question": "정책은?"},  # 정책은 앱이 묻는다 — 버린다
        ]
    },
    ensure_ascii=False,
)


async def test_clarify_argon_questions_with_app_policy_question():
    argon = FakeLLM([Q2])
    res = await _clarify(argon=argon, local=FakeLLM()).inspect(REQ)
    assert res.status == "ok" and res.source == "argon" and res.policy_needed
    assert [q.topic for q in res.questions] == ["policy", "target", "metric"]
    assert "[앱 점검" in argon.calls[0] and "[섹션 체크리스트" in argon.calls[0]


async def test_clarify_reasons_enough_failed_and_rule_fallback():
    filled = REQ.model_copy(
        update={
            "policy_basis": "철도 안전",
            "constraints": "연구기간 12개월",
            "beneficiaries": "시설처",
            "goal": "보수 우선순위 산정 오류 10% 감소",
        }
    )
    assert gaps(filled) == []
    enough = await _clarify(argon=FakeLLM(['{"questions": []}'])).inspect(filled)
    assert enough.status == "enough" and enough.questions == []
    failed = await _clarify(argon=FakeLLM(fail_at={0}), local=FakeLLM(fail_at={0})).inspect(filled)
    assert failed.status == "failed" and failed.reason == "error" and failed.questions == []
    # 모델이 모두 실패해도 앱 점검에서 빠진 것이 있으면 그 질문을 낸다 (사유와 함께)
    rule = await _clarify(argon=FakeLLM(fail_at={0}), local=FakeLLM(fail_at={0})).inspect(REQ)
    assert rule.status == "ok" and rule.source == "rule" and rule.reason == "error"
    assert [q.topic for q in rule.questions][:2] == ["policy", "budget_period"]
    # 로컬 대체
    local = await _clarify(argon=FakeLLM(fail_at={0}), local=FakeLLM([Q2])).inspect(filled)
    assert local.source == "local" and local.record["fallback"] is True


async def test_clarify_answers_reach_section_prompts_as_supplement():
    """보강 질문의 답 → 보충 정보(supplement) → 작성 프롬프트의 [제안 입력] 에 들어간다."""
    from rra.application.usecases.clarify_input import apply_answers
    from rra.application.usecases.generate_proposal import GenerateProposal
    from rra.domain.models import RetrievalSnapshot
    from tests.application.test_review_manager import _rules

    req = apply_answers(REQ, {"적용 노선은 어디입니까?": "경부선 대전~대구"})
    llm = FakeLLM(['[{"text": "경부선 대전~대구 구간에 적용함.", "evidence": []}]'])
    gen = GenerateProposal(llm, _repo(), FakePromptLibrary(), _rules(), ["title", "method"])
    await gen.compose_section("method", req, RetrievalSnapshot.of("q", []))
    assert "경부선 대전~대구" in llm.calls[0] and '"supplement"' in llm.calls[0]


# ── 보완 질문 ─────────────────────────────────────────
CHECK = {"tech_importance": [{"element": "국외 동향", "question": "국외는?", "keywords": ["국외"]}]}


async def test_section_questions_argon_then_checklist_fallback():
    sec = Section(key="tech_importance", sentences=[Sentence(text="국내 연구가 있음.")])
    argon = FakeLLM(
        [
            json.dumps(
                {
                    "questions": [
                        {"element": "국외 동향", "question": "국외 선행연구는 무엇입니까?"},
                        {"element": "한계 수치", "question": "기존 기술의 정확도는?"},
                    ]
                },
                ensure_ascii=False,
            )
        ]
    )
    uc = SectionQuestions(ArgonFirst(FakeLLM(), argon), FakePromptLibrary(), CHECK)
    chunks = [Chunk(chunk_id="a#0", doc_id="a", ordinal=0, text="자료")]
    res = await uc("tech_importance", sec, chunks, REQ, {"이전": "답"})
    assert res.source == "argon" and [q["element"] for q in res.questions] == [
        "국외 동향",
        "한계 수치",
    ]
    prompt = argon.calls[0]
    assert (
        "[양식 작성 지침]" in prompt and "국내 연구가 있음" in prompt and '<doc id="a#0">' in prompt
    )
    # Argon·로컬 실패 → 체크리스트, 사유 남김
    down = SectionQuestions(
        ArgonFirst(FakeLLM(fail_at={0}), FakeLLM(fail_at={0})), FakePromptLibrary(), CHECK
    )
    res = await down("tech_importance", sec, [], REQ)
    assert res.source == "checklist" and res.reason == "error"
    assert res.questions == [{"element": "국외 동향", "question": "국외는?"}]


def test_every_form_section_has_a_checklist():
    from rra.config_loader import lint_rules, section_checklists
    from rra.settings import Settings

    settings = Settings(_env_file=None)
    checklists = section_checklists(settings)
    missing = [k for k in lint_rules(settings).order if not checklists.get(k)]
    assert missing == []


# ── 변경 세기 ─────────────────────────────────────────
def _figure(fid: str, **kw) -> Figure:
    from rra.domain.models.figure import parse_spec

    spec = parse_spec("process", {"stages": [{"name": "a"}, {"name": "b"}, {"name": "c"}]})
    return Figure(id=fid, kind="process", section="method", spec=spec, **kw)


def test_change_count_covers_every_type():
    s = lambda t: Sentence(text=t)  # noqa: E731
    base = DraftVersion(
        version=2,
        origin="argon",
        created_at="2026-10-28T01:00:00+00:00",
        sections=[
            Section(key="method", sentences=[s("가 문장임."), s("나 문장임."), s("다 문장임.")]),
            Section(key="task_type", sentences=[s("유형임.")], choices=["basic"]),
        ],
        figures=[_figure("f:1"), _figure("f:2"), _figure("f:3", included=False), _figure("f:4")],
    )
    current = DraftVersion(
        version=5,
        origin="edit",
        created_at="2026-10-28T02:00:00+00:00",
        sections=[
            Section(
                key="method",
                sentences=[
                    s("가 문장 고침."),
                    s("다 문장임."),
                    s("라 새 문장임."),
                    s("마 새 문장임."),
                ],
            ),
            Section(key="task_type", sentences=[s("유형임.")], choices=["applied"]),
        ],
        figures=[
            _figure("f:1", confirmed=True),
            _figure("f:2", included=False),
            _figure("f:3"),
            _figure("f:4", caption="새 캡션"),
            _figure("f:5"),
        ],
        evidence_decisions=[
            EvidenceDecision(sentence_id="s:method:0", evidence_id="a#0", action="approve"),
            EvidenceDecision(
                sentence_id="s:method:1", evidence_id="b#0", action="replace", replacement="c#0"
            ),
            EvidenceDecision(sentence_id="s:method:2", evidence_id="d#0", action="exclude"),
        ],
    )
    summary = count_changes(
        base, current, confirmed_after_base=True, policy_after_base=True, memo_sections=["method"]
    )
    c = summary.counts
    # 나 → 삭제, 가 → 고침(수정), 라·마 추가 → 짝 1(수정) + 추가 1 … 짝지은 만큼 수정
    assert c["sentence_edit"] == 2 and c["sentence_add"] == 1 and c["sentence_delete"] == 0
    assert c["choice_value"] == 1
    assert (c["figure_confirm"], c["figure_remove"], c["figure_include"]) == (1, 1, 1)
    assert (c["figure_change"], c["figure_add"]) == (1, 1)
    assert (c["evidence_approve"], c["evidence_replace"], c["evidence_exclude"]) == (1, 1, 1)
    assert (c["choice_confirm"], c["policy_choice"], c["memo"]) == (1, 1, 1)
    assert summary.total == sum(c.values()) and summary.dump()["items"][0]["label"] == "문장 수정"
    assert count_changes(base, base).total == 0


def test_base_version_is_last_final_review_or_latest_draft():
    v = [
        DraftVersion(version=1, origin="local", sections=[]),
        DraftVersion(version=2, origin="argon", sections=[]),
        DraftVersion(version=3, origin="edit", sections=[]),
        DraftVersion(version=4, origin="edit", sections=[]),
    ]
    assert base_version(v, None).version == 2
    assert base_version(v, 3).version == 3


@pytest.mark.parametrize("raw", ["not json", '{"x": 1}'])
async def test_argon_first_corrects_once_then_falls_back(raw):
    argon = FakeLLM([raw, raw])
    local = FakeLLM(['{"ok": true}'])

    def check(text):
        try:
            data = json.loads(text)
        except ValueError:
            return None, "invalid"
        return (data, None) if data.get("ok") else (None, "invalid")

    res = await ArgonFirst(local, argon).ask("p", system="s", check=check)
    assert res.value == {"ok": True} and res.fallback and res.calls == 3 and res.remote_calls == 2
    assert len(argon.calls) == 2 and "형식 교정" in argon.calls[1]
