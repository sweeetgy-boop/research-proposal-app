"""참고 논문 열의 관련 순위("관련 순위 n/총수") — 순수 규칙·비교표 유스케이스·REST 직렬화.

2026-11-04 소유자 결정: 고정 경계값 "검색 관련도 높음·중간·낮음" 대신 ② 관련 연구 목록 안의 자리.
목록 출처: 같은 입력의 precheck 메모(제안자가 본 관련 연구) → 메모가 없으면 같은 관련 연구 검색을
다시.
"""

from __future__ import annotations

from pathlib import Path

from rra.application.usecases.compare_projects import CompareProjects
from rra.domain.models import Document, PrecheckResult, ProposalRequest
from rra.domain.models.gap import RelatedResearch
from rra.domain.rules.reference_rank import research_ranks
from rra.entrypoints.views import comparison_payload
from tests.fakes import InMemoryRepository

REQ = ProposalRequest(
    current_state="궤도 틀림이 반복 발생함",
    root_cause="다짐 효과가 오래 가지 않음",
    limitation="주기적 보수로는 진행 속도를 반영하지 못함",
    goal="검측 이력 기반 보수 우선순위 산정",
)
PAPERS = [
    Document(
        doc_id=f"scienceon:p{i}",
        source="scienceon",
        doc_type="paper",
        title=f"논문 {i}",
        abstract="궤도 틀림 진행 속도 추정",
        orgs=["external"],
    )
    for i in range(1, 5)
]


def _related(doc_id, score):
    return RelatedResearch(
        doc_id=doc_id, title="t", source="scienceon", doc_type="paper", similarity=score
    )


# ── 순수 규칙 ────────────────────────────────────────────
def test_ranks_follow_score_desc_and_total_is_list_length():
    got = research_ranks([("a", 0.86), ("b", 0.91), ("c", 0.88)])
    assert got == {"b": (1, 3), "c": (2, 3), "a": (3, 3)}


def test_ties_keep_list_order():
    got = research_ranks([("x", 0.9), ("y", 0.95), ("z", 0.9), ("w", 0.9)])
    assert got == {"y": (1, 4), "x": (2, 4), "z": (3, 4), "w": (4, 4)}


def test_missing_doc_has_no_rank_and_empty_list_is_empty():
    assert research_ranks([("a", 0.9)]).get("other") is None
    assert research_ranks([]) == {}


def test_duplicate_doc_counts_once():
    assert research_ranks([("a", 0.9), ("b", 0.8), ("a", 0.99)]) == {"a": (1, 2), "b": (2, 2)}


# ── 비교표 유스케이스 ────────────────────────────────────
class MemoPrecheck:
    """메모만 있는 precheck 대역 — 다시 검색하면 실패."""

    def __init__(self, related):
        self.result = PrecheckResult(alerts=[], related_research=related)
        self.searched = 0

    async def __call__(self, req):
        return []

    def memo(self, req):
        return self.result

    async def search_research(self, req):
        self.searched += 1
        raise AssertionError("메모가 있으면 다시 검색하지 않는다")


class NoMemoPrecheck:
    def __init__(self, related):
        self.related = related
        self.searched = 0

    async def __call__(self, req):
        return []

    def memo(self, req):
        return None

    async def search_research(self, req):
        self.searched += 1
        return self.related


def _repo():
    repo = InMemoryRepository()
    repo.seed(PAPERS, [])
    return repo


async def test_reference_rank_comes_from_the_precheck_memo():
    # 메모의 관련 연구 목록(화면 순서: 점수 내림차순) — 참고 논문은 그 안의 자리 n/총수
    pre = MemoPrecheck(
        [
            _related("scienceon:p9", 0.93),
            _related("scienceon:p1", 0.91),
            _related("scienceon:p2", 0.889),
            _related("scienceon:p3", 0.87),
            _related("scienceon:p8", 0.86),
        ]
    )
    uc = CompareProjects(_repo(), precheck=pre)
    req = REQ.model_copy(
        update={"reference_ids": ["scienceon:p3", "scienceon:p1", "scienceon:p4", "scienceon:p2"]}
    )
    table = await uc(req, [], similar_only=True)
    got = {c.doc_id: (c.relevance_rank, c.relevance_total, c.similarity) for c in table.projects}
    assert got == {
        "scienceon:p3": (4, 5, 0.87),
        "scienceon:p1": (2, 5, 0.91),
        "scienceon:p4": (None, None, None),  # 관련 연구 목록 밖 — 순위 없음
        "scienceon:p2": (3, 5, 0.889),
    }
    # 열 순서는 그대로 reference_ids 순서 (순위로 다시 줄 세우지 않는다)
    assert [c.doc_id for c in table.projects] == req.reference_ids
    assert pre.searched == 0
    payload = comparison_payload(table)
    projects = payload["projects"]
    assert [(p["relevance_rank"], p["relevance_total"]) for p in projects] == [
        (4, 5),
        (2, 5),
        (None, None),
        (3, 5),
    ]
    assert all("relevance" not in p for p in [payload["proposal"], *projects])
    assert payload["proposal"]["relevance_rank"] is None
    assert payload["proposal"]["relevance_total"] is None


async def test_reference_rank_recomputes_the_research_search_without_memo():
    pre = NoMemoPrecheck([_related("scienceon:p1", 0.95), _related("scienceon:p2", 0.9)])
    uc = CompareProjects(_repo(), precheck=pre)
    req = REQ.model_copy(update={"reference_ids": ["scienceon:p2"]})
    table = await uc(req, [], similar_only=True)
    (col,) = table.projects
    assert col.kind == "reference" and (col.relevance_rank, col.relevance_total) == (2, 2)
    assert col.similarity == 0.9 and pre.searched == 1


async def test_no_precheck_list_means_no_rank():
    pre = NoMemoPrecheck([])
    uc = CompareProjects(_repo(), precheck=pre)
    req = REQ.model_copy(update={"reference_ids": ["scienceon:p1"]})
    (col,) = (await uc(req, [], similar_only=True)).projects
    assert col.relevance_rank is None and col.relevance_total is None and col.similarity is None


async def test_no_references_no_research_search():
    pre = NoMemoPrecheck([_related("scienceon:p2", 0.9)])
    table = await CompareProjects(_repo(), precheck=pre)(REQ, [], similar_only=True)
    assert table.projects == [] and pre.searched == 0


# ── 설정·PrecheckOverlap ─────────────────────────────────
def test_repo_config_has_no_relevance_thresholds():
    """경계값(옛 candidates.research.relevance)은 없앴다 — 재측정은 시범 사례가 쌓인 뒤."""
    import yaml

    root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "config" / "overlap.yaml").read_text(encoding="utf-8"))
    assert "relevance" not in cfg["candidates"]["research"]


async def test_precheck_search_research_repeats_the_related_research_search(docs, own):
    from rra.application.usecases.precheck_overlap import PrecheckOverlap
    from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember

    repo = InMemoryRepository()
    repo.seed([*docs, *PAPERS], [])
    repo.similar = [(PAPERS[0], 0.91), (docs[0], 0.95), (PAPERS[1], 0.87)]
    rule = OverlapCandidateRule(research=(SourceMember(source="scienceon"),), research_k=5)
    pre = PrecheckOverlap(repo, own=own, candidates=rule)
    assert pre.memo(REQ) is None
    found = await pre.search_research(REQ)
    assert [(r.doc_id, r.similarity) for r in found] == [
        ("scienceon:p1", 0.91),
        ("scienceon:p2", 0.87),
    ]
    rule_result = await pre.rule_stage(REQ, keywords=False, remember=True)
    assert [r.doc_id for r in pre.memo(REQ).related_research] == [
        r.doc_id for r in rule_result.related_research
    ]
