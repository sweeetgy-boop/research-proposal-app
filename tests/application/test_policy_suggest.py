"""PolicySuggest — korail_web 자료원만 검색, policy 문서만, LLM 없음, 자동 삽입 없음."""

from datetime import date

from rra.application.usecases.policy_suggest import PolicySuggest
from rra.domain.models import Chunk, Document, ProposalRequest
from tests.fakes import InMemoryRepository

REQ = ProposalRequest(
    current_state="궤도 틀림 점검이 수작업",
    root_cause="센서 부재",
    limitation="주기 점검",
    goal="상태기반 유지보수 자동 감지",
)
POLICY = Document(
    doc_id="korail_web:p1",
    source="korail_web",
    doc_type="policy",
    title="중장기 경영목표",
    body="x",
    pub_date=date(2026, 3, 1),
    url="https://info.korail.com/info/contents.do?key=1900",
    raw={
        "menu_path": "ESG경영 > 경영공시 > 일반항목 > 중장기 경영목표",
        "crawl_snapshot": "2026-10-27",
    },
)
NEWS = POLICY.model_copy(
    update={"doc_id": "korail_web:n1", "doc_type": "korail_news", "title": "보도자료"}
)
PAPER = Document(doc_id="openalex:W1", source="openalex", doc_type="paper", title="paper")
CHUNKS = [
    Chunk(
        chunk_id="korail_web:p1#0",
        doc_id="korail_web:p1",
        ordinal=0,
        heading="표 전략과제",
        text="데이터기반 유지보수 첨단화. 차량·철도시설 상태기반의 유지보수체계 확립.",
        similarity=0.8,
    ),
    Chunk(
        chunk_id="korail_web:p1#1",
        doc_id="korail_web:p1",
        ordinal=1,
        text="국민공감 소통·홍보 강화.",
        similarity=0.6,
    ),
    Chunk(
        chunk_id="korail_web:n1#0",
        doc_id="korail_web:n1",
        ordinal=0,
        text="궤도 틀림 자동 감지 센서 도입 보도.",
        similarity=0.9,
    ),
    Chunk(
        chunk_id="openalex:W1#0",
        doc_id="openalex:W1",
        ordinal=0,
        text="track geometry",
        similarity=0.95,
    ),
]


async def test_suggests_only_policy_documents_from_korail_web():
    repo = InMemoryRepository()
    repo.seed([POLICY, NEWS, PAPER], CHUNKS)
    out = await PolicySuggest(repo)(REQ)
    assert [s.doc_id for s in out] == ["korail_web:p1"]
    s = out[0]
    assert s.year == 2026 and s.page == "표 전략과제" and s.url.endswith("key=1900")
    assert s.quote == "차량·철도시설 상태기반의 유지보수체계 확립." and "유지보수" in s.keywords
    assert s.menu_path.startswith("ESG경영")
    call = next(c for c in repo.calls if c[0] == "hybrid_search")
    assert call[1]["sources"] == ["korail_web", "molit", "rnd_notice"] and call[1]["k"] == 30


async def test_empty_when_nothing_ingested():
    assert await PolicySuggest(InMemoryRepository())(REQ) == []


async def test_policy_importance_rule_still_uses_only_proposer_input():
    """정책 근거 추천이 있어도 2-가-(1) 은 policy_basis 입력만 근거로 쓴다 (grounding 규칙 불변)."""
    from rra.config_loader import lint_rules
    from rra.settings import Settings

    rules = lint_rules(Settings())
    assert "policy_importance" in rules.evidence_forbidden
    assert rules.requires_input["policy_importance"] == ["policy_basis"]
    assert rules.input_grounded["policy_importance"] == ["policy_basis"]
