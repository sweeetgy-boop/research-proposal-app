from rra.application.usecases.precheck_overlap import PrecheckOverlap
from tests.fakes import InMemoryRepository


async def test_precheck_orders_blocking_first(req, docs, own):
    repo = InMemoryRepository()
    repo.similar = [(docs[1], 0.95), (docs[0], 0.81)]
    alerts = await PrecheckOverlap(repo, own=own)(req)
    assert [a.blocking for a in alerts] == [True, True]
    assert [a.tier for a in alerts] == ["external", "own"]


async def test_precheck_without_own_unit_has_no_own_tier(req, docs):
    repo = InMemoryRepository()
    repo.similar = [(docs[0], 0.81)]
    (alert,) = await PrecheckOverlap(repo)(req)
    assert alert.tier == "domestic_rail" and not alert.blocking


async def test_precheck_passes_query_and_keyword_rule_to_judge(req, docs, own):
    from rra.domain.rules.keywords import KeywordRule

    repo = InMemoryRepository()
    tracked = docs[0].model_copy(update={"body": "궤도 틀림 상시 감지 센서 연구"})
    repo.similar = [(tracked, 0.9), (docs[1], 0.95)]
    alerts = await PrecheckOverlap(repo, own=own, keywords=KeywordRule(min_hits=2))(req)
    by_id = {a.doc_id: a for a in alerts}
    assert by_id["alio:1"].blocking and {"궤도", "틀림", "감지"} <= set(by_id["alio:1"].keywords)
    assert not by_id["openalex:W1"].blocking  # 유사도 0.95 지만 공유 키워드 없음


# ── 판정 후보 = 과제형 자료원만 (ADR 0028) ─────────────────────────────
def _rule(k: int = 5):
    from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember

    return OverlapCandidateRule(
        project=(
            SourceMember(source="own"),
            SourceMember(source="alio"),
            SourceMember(source="ntis", doc_types=("rnd_project",)),
        ),
        research=(
            SourceMember(source="openalex"),
            SourceMember(source="ntis", doc_types=("report",)),
        ),
        research_k=k,
    )


def _doc(doc_id, source, doc_type, title="궤도 틀림 상시 감지"):
    from rra.domain.models import Document

    return Document(doc_id=doc_id, source=source, doc_type=doc_type, title=title)


async def test_precheck_searches_project_sources_only_and_reports_related_research(req, own):
    repo = InMemoryRepository()
    repo.similar = [
        (_doc("openalex:W1", "openalex", "paper"), 0.97),
        (_doc("ntis:rep", "ntis", "report"), 0.95),
        (_doc("alio:1", "alio", "internal_report"), 0.90),
        (_doc("own:1", "own", "rnd_project", "궤도 틀림 보수 기록"), 0.86),
        (_doc("ntis:prj", "ntis", "rnd_project", "궤도 틀림 진행 예측"), 0.85),
    ]
    uc = PrecheckOverlap(repo, own=own, candidates=_rule())
    result = await uc.run(req)
    assert [a.doc_id for a in result.alerts] == ["alio:1", "own:1", "ntis:prj"]  # 논문·보고서 없음
    assert [r.doc_id for r in result.related_research] == ["openalex:W1", "ntis:rep"]
    assert result.related_research[0].similarity == 0.97
    project_call, research_call = [c for c in repo.calls if c[0] == "find_similar"]
    assert project_call[1]["sources"] == ["own", "alio", "ntis"]
    assert research_call[1]["sources"] == ["openalex", "ntis"] and research_call[1]["k"] == 10
    # __call__ 은 종전처럼 알림 목록만 (MCP·Streamlit·추천·측정 호환)
    assert [a.doc_id for a in await uc(req)] == ["alio:1", "own:1", "ntis:prj"]


async def test_precheck_without_candidate_rule_keeps_old_behaviour(req, own):
    repo = InMemoryRepository()
    repo.similar = [(_doc("openalex:W1", "openalex", "paper"), 0.97)]
    result = await PrecheckOverlap(repo, own=own).run(req)
    assert [a.doc_id for a in result.alerts] == ["openalex:W1"] and result.related_research == []
    assert repo.calls[-1][1]["sources"] is None


async def test_precheck_reranker_gets_only_project_candidates(req, own):
    class Rerank:
        seen = None

        async def rerank_documents(self, query, docs, *, k=None):
            self.seen = [d.doc_id for d, _ in docs]
            return docs[:k]

    repo = InMemoryRepository()
    repo.similar = [
        (_doc("ntis:rep", "ntis", "report"), 0.95),
        (_doc("own:1", "own", "rnd_project"), 0.86),
    ]
    rr = Rerank()
    await PrecheckOverlap(repo, own=own, reranker=rr, candidates=_rule(k=0))(req)
    assert rr.seen == ["own:1"]
    assert len([c for c in repo.calls if c[0] == "find_similar"]) == 1  # research_k=0 → 검색 없음
