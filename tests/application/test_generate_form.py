"""별지 제2호서식 규칙(config/templates/proposal_korail.rules.yaml)으로 도는 생성 — FakeLLM 만.

선택형 섹션, 입력 전용 섹션(정책적 중요도), 전략 목록, 유사과제 판정 경로를 검증한다.
"""

import json
from pathlib import Path

import pytest
import yaml

from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Budget, StrategyCatalog
from rra.domain.rules.lint import LintRules, has_errors
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

RULES_PATH = Path(__file__).parents[2] / "config/templates/proposal_korail.rules.yaml"
RULES = LintRules.model_validate(yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")))
CATALOG = StrategyCatalog.model_validate(
    {
        "source": "테스트",
        "directions": [
            {
                "id": "D1",
                "name": "안전 최우선",
                "tasks": [{"id": "D1-1", "name": "예방적 유지보수 고도화"}],
            }
        ],
    }
)


def _items(sentences):
    return [{"text": t, "evidence": list(ev)} for t, ev in sentences]


def arr(*sentences):
    return json.dumps(_items(sentences), ensure_ascii=False)


def obj(choices, *sentences):
    return json.dumps({"choices": choices, "sentences": _items(sentences)}, ensure_ascii=False)


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    r.upsert(docs, chunks)
    return r


def make(llm, repo, *, strategy=None, check_overlap=True):
    return GenerateProposal(
        llm,
        repo,
        FakePromptLibrary(),
        RULES,
        RULES.order,
        strategy=strategy or StrategyCatalog(),
        check_overlap=check_overlap,
    )


def by_key(llm):
    """프롬프트의 [섹션: key] 로 응답을 고르는 FakeLLM (순서에 묶이지 않게)."""

    class _ByKey(FakeLLM):
        def __init__(self, answers):
            super().__init__()
            self.answers = answers

        async def complete(self, prompt, **kw):
            self.calls.append(prompt)
            key = prompt.split("]", 1)[0].removeprefix("[섹션: ")
            return self.answers.get(key, "[]")

    return _ByKey(llm)


FULL = {
    "title": arr(("궤도 틀림 상시 감지 기술 개발", [])),
    "task_type": obj(["development"], ("장치 개발이 목적임", [])),
    "policy_importance": arr(("제4차 국가철도망 구축계획의 디지털 전환 방향과 부합함", [])),
    "tech_importance": arr(("사내 선행 연구는 수동 점검을 다룸", ["alio:1#0"])),
    "strategy_alignment": obj(["D1-1"], ("예방적 유지보수 고도화와 연계됨", [])),
    "objective": arr(("상시 자동 감지 체계를 확보함", [])),
    "method": arr(("1차년도에 센서를 시험함", [])),
    "expected_management": arr(("점검 인력을 줄임", [])),
    "expected_technology": arr(("자체 감지 기술을 확보함", [])),
    "expected_standing": arr(("대국민 안전 신뢰를 높임", [])),
    "utilization": obj(["software", "commercialization"], ("시설처가 운영함", [])),
}


async def test_full_form_is_done_with_only_expected_warnings(req, repo):
    req = req.model_copy(update={"policy_basis": "제4차 국가철도망 구축계획 — 철도 디지털 전환"})
    llm = by_key(FULL)
    draft = await make(llm, repo, strategy=CATALOG)(req)
    assert [s.key for s in draft.sections] == RULES.order
    assert draft.template == "korail_rnd_proposal_v2024"
    assert draft.section("task_type").choices == ["development"]
    assert draft.section("utilization").choices == ["software", "commercialization"]
    assert draft.section("strategy_alignment").choices == ["D1-1"]
    overlap = [s.text for s in draft.section("overlap_review").sentences]
    assert all(s.origin == "app" for s in draft.section("overlap_review").sentences)
    # 실제 본 범위: 검색 청크 문서 (alio:1, openalex:W1). scienceon:9 는 적재됐지만 검색에 안 걸림
    assert overlap[0] == (
        "유사과제 검토 범위는 수집 자료 중 본 제안과 관련도가 높은 "
        "알리오 공시 연구보고서 1건, OpenAlex 해외 논문 1건임."
    )
    assert overlap[1] == (
        "미수집 자료원(NTIS 국가R&D 과제, KIPRIS 국내 특허, KIPRIS 해외 특허)은 "
        "검토 범위에서 제외됨."
    )
    assert "ScienceON" not in overlap[1]  # 적재된 자료원은 미수집으로 쓰지 않는다
    assert "확인되지 않음" in overlap[2]
    assert not any("[섹션: overlap_review]" in c for c in llm.calls)  # 유사과제 없음 → LLM 미사용


async def test_policy_section_is_skipped_without_basis(req, repo):
    llm = by_key(FULL)
    uc = make(llm, repo)
    snap = uc.retrieve(req)
    composed = await uc.compose_section("policy_importance", req, snap)
    assert composed.mode == "skipped" and composed.section.sentences == []
    assert composed.parse is None and composed.prompt_hash is None and llm.calls == []
    _, problems = uc.finalize("r", req, snap, [composed.section])
    assert ("policy_importance", "input_missing", "warning") in {
        (p.section, p.code, p.severity) for p in problems
    }


async def test_policy_section_drops_invented_names_and_citations(req, repo):
    req = req.model_copy(update={"policy_basis": "제4차 국가철도망 구축계획"})
    llm = by_key(
        {
            "policy_importance": arr(
                ("제4차 국가철도망 구축계획의 방향과 부합함", []),
                ("철도산업발전 기본계획에도 부합함", []),  # 입력에 없는 계획명
                ("제5차 국가철도망 구축계획에 반영될 것임", []),  # 입력에 없는 차수
                ("자료에 따르면 정책이 중요함", ["alio:1#0"]),  # 자료 인용 금지
            )
        }
    )
    uc = make(llm, repo)
    composed = await uc.compose_section("policy_importance", req, uc.retrieve(req))
    assert [s.text for s in composed.section.sentences] == [
        "제4차 국가철도망 구축계획의 방향과 부합함"
    ]
    assert len(composed.dropped) == 3


async def test_strategy_is_skipped_when_catalog_is_empty(req, repo):
    llm = by_key(FULL)
    uc = make(llm, repo)
    composed = await uc.compose_section("strategy_alignment", req, uc.retrieve(req))
    assert composed.mode == "skipped" and llm.calls == []


async def test_strategy_prompt_lists_only_catalog_and_rejects_others(req, repo):
    llm = by_key({"strategy_alignment": obj(["D9-9"], ("없는 전략", []))})
    uc = make(llm, repo, strategy=CATALOG)
    composed = await uc.compose_section("strategy_alignment", req, uc.retrieve(req))
    assert composed.section.choices == []  # 목록에 없는 id 는 버린다
    assert "- D1-1: 안전 최우선 > 예방적 유지보수 고도화" in llm.calls[0]


async def test_prompt_carries_no_budget_or_department(req, repo):
    req = req.model_copy(
        update={
            "department": "기술연구처",
            "budget": Budget(account="연구개발비", amount_thousand_krw=123456),
        }
    )
    llm = by_key({"title": arr(("제목", []))})
    uc = make(llm, repo)
    await uc.compose_section("title", req, uc.retrieve(req))
    assert "123456" not in llm.calls[0] and "기술연구처" not in llm.calls[0]
    assert "연구개발비" not in llm.calls[0]


async def test_overlap_review_uses_llm_when_blocking_alert_exists(req, repo, docs):
    repo.similar = [(docs[0], 0.93), (docs[1], 0.40)]  # alio:1 은 domestic_rail 0.85 초과
    llm = by_key(
        {
            "overlap_review": arr(
                ("사내 과제와 대상이 겹침", ["alio:1"]),
                ("근거 없는 주장", []),
            )
        }
    )
    uc = make(llm, repo)
    snap = uc.retrieve(req)
    assert snap.overlap_checked and snap.overlap[0].blocking
    composed = await uc.compose_section("overlap_review", req, snap)
    assert [s.text for s in composed.section.sentences] == ["사내 과제와 대상이 겹침"]
    assert "id=alio:1" in llm.calls[0] and "중복기준초과=예" in llm.calls[0]
    assert "궤도 상태 자동 감지 연구" not in llm.calls[0].split("[자료]")[0]  # 제목은 표에 없음


async def test_blocking_doc_outside_search_gets_a_chunk(req, repo, docs):
    repo.chunks = [c for c in repo.chunks if c.doc_id != "alio:1"]
    repo.similar = [(docs[0], 0.95)]
    snap = make(FakeLLM(), repo).retrieve(req)
    assert "alio:1#overlap" in {c.chunk_id for c in snap.chunks}
    assert "alio:1" in snap.retrieved_ids


async def test_without_overlap_check_the_section_falls_back_to_llm(req, repo):
    llm = by_key({"overlap_review": arr(("겹침 없음", ["alio:1#0"]))})
    uc = make(llm, repo, check_overlap=False)
    snap = uc.retrieve(req)
    assert not snap.overlap_checked
    composed = await uc.compose_section("overlap_review", req, snap)
    assert composed.mode == "llm" and composed.section.sentences[0].origin == "llm"


async def test_missing_required_section_is_still_an_error(req, repo):
    llm = by_key({})  # 전부 빈 배열
    uc = make(llm, repo)
    snap = uc.retrieve(req)
    sections = [(await uc.compose_section(k, req, snap)).section for k in RULES.order]
    _, problems = uc.finalize("r", req, snap, sections)
    assert has_errors(problems)
    assert ("title", "missing") in {(p.section, p.code) for p in problems}
