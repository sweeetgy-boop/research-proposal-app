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
    # 정책적 중요도 작성안과 같은 자료원 범위 (ADR 0040)
    assert call[1]["sources"] == ["molit", "rnd_notice", "korail_web", "bai", "mofe"]
    assert call[1]["k"] == 30


async def test_exclude_docs_skips_already_seen_documents():
    """팝업 [다시 받기] — 이미 본 문서는 다시 내지 않는다."""
    repo = InMemoryRepository()
    repo.seed([POLICY, NEWS, PAPER], CHUNKS)
    assert await PolicySuggest(repo)(REQ, exclude_docs=["korail_web:p1"]) == []


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


async def test_research_service_and_admin_records_are_not_policy_basis():
    """사전정보공표 연구용역(사내 발주)·행정 공시는 정책 근거 추천에도, 작성안에도 나오지 않는다
    (ADR 0040 — 두 기능이 같은 규칙 policy_passage 를 쓴다)."""
    from rra.application.usecases.policy_cards import PolicyCards

    research = POLICY.model_copy(
        update={
            "doc_id": "korail_web:r1",
            "title": "레인보우 비경열차 관광수요 예측 연구",
            "raw": {"menu": "preinfo", "native_id": "preinfo:55:1"},
        }
    )
    admin = POLICY.model_copy(
        update={
            "doc_id": "korail_web:a1",
            "title": "신규채용자 친인척 재직관련 현황",
            "raw": {
                "menu": "preinfo",
                "native_id": "preinfo:60:1",
                "page_url": "https://info.korail.com/x?infoRelNo=60&infoRelCategory=IRTYP4",
            },
        }
    )
    text = "상태기반 유지보수 체계 확립을 위한 궤도 틀림 자동 감지 방안을 마련함."
    chunks = [
        Chunk(chunk_id=f"{d}#0", doc_id=d, ordinal=0, text=text, similarity=0.9)
        for d in ("korail_web:p1", "korail_web:r1", "korail_web:a1")
    ]
    repo = InMemoryRepository()
    repo.seed([POLICY, research, admin], chunks)
    out = await PolicySuggest(repo)(REQ)
    assert [s.doc_id for s in out] == ["korail_web:p1"]
    passages = await PolicyCards(repo=repo, ask=None).passages(REQ)  # type: ignore[arg-type]
    assert [p.doc_id for p in passages] == ["korail_web:p1"]


async def test_admin_status_statistics_doc_types_never_offered():
    """ADR 0046 — 이주 뒤 doc_type admin_notice·status_report·statistics 인 행(분류 키가 없어도)은
    정책 근거 추천·작성안 어디에도 나오지 않는다. 유사도가 정책 문서보다 높아도."""
    from rra.application.usecases.policy_cards import PolicyCards

    others = []
    for i, (doc_type, cls) in enumerate(
        (
            ("admin_notice", "admin_record"),
            ("status_report", "status"),
            ("statistics", "statistics"),
            ("admin_notice", None),  # 분류 키 없는 행
            ("status_report", None),
        )
    ):
        raw = {"menu": "biz_maint_track"} | ({"doc_class": cls} if cls else {})
        others.append(
            POLICY.model_copy(
                update={"doc_id": f"korail_web:x{i}", "doc_type": doc_type, "raw": raw}
            )
        )
    text = "상태기반 유지보수 체계 확립을 위한 궤도 틀림 자동 감지 방안을 마련함."
    chunks = [
        Chunk(
            chunk_id="korail_web:p1#0", doc_id="korail_web:p1", ordinal=0, text=text, similarity=0.8
        )
    ] + [
        Chunk(chunk_id=f"{d.doc_id}#0", doc_id=d.doc_id, ordinal=0, text=text, similarity=0.95)
        for d in others
    ]
    repo = InMemoryRepository()
    repo.seed([POLICY, *others], chunks)
    out = await PolicySuggest(repo)(REQ)
    assert [s.doc_id for s in out] == ["korail_web:p1"]
    passages = await PolicyCards(repo=repo, ask=None).passages(REQ)  # type: ignore[arg-type]
    assert [p.doc_id for p in passages] == ["korail_web:p1"]


def test_overlap_candidates_keep_research_service_and_drop_new_types():
    """유사과제 판정 — 연구용역(사내 발주, procurement)은 그대로 후보, 행정 공시·사업 현황은
    아님."""
    from rra.config_loader import overlap_candidates, retrieval_mix
    from rra.domain.rules.retrieval_scope import overlap_candidates as scope_candidates
    from rra.settings import load_settings

    def doc(doc_id, doc_type):
        return Document(doc_id=doc_id, source="korail_web", doc_type=doc_type, title="t")

    research = doc("korail_web:r", "procurement")
    hits = [
        (research, 0.9),
        (doc("korail_web:a", "admin_notice"), 0.95),
        (doc("korail_web:s", "status_report"), 0.93),
        (doc("korail_web:t", "statistics"), 0.92),
    ]
    settings = load_settings()
    rule = overlap_candidates(settings)
    assert [d.doc_id for d, _ in rule.project_hits(hits)] == ["korail_web:r"]
    assert [d.doc_id for d, _ in scope_candidates(hits)] == ["korail_web:r"]
    mix = retrieval_mix(settings)
    assert [d.doc_id for d, _ in mix.overlap_candidates(hits, lambda d: d.doc_type)] == [
        "korail_web:r"
    ]
