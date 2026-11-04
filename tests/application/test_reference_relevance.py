"""참고 논문 열의 검색 관련도(높음·중간·낮음) — 순수 규칙·비교표 유스케이스·가짜 모드.

점수 출처: 같은 입력의 precheck 메모(제안자가 본 관련 연구) → 메모가 없으면 같은 관련 연구 검색을
다시.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rra.application.usecases.compare_projects import CompareProjects
from rra.domain.models import Document, PrecheckResult, ProposalRequest
from rra.domain.models.gap import RelatedResearch
from rra.domain.rules.research_relevance import ResearchRelevanceRule
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
@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0.93, "high"),
        (0.895, "high"),
        (0.8949, "mid"),
        (0.885, "mid"),
        (0.8849, "low"),
        (0.60, "low"),
        (None, None),
    ],
)
def test_default_thresholds_from_measurement(score, level):
    assert ResearchRelevanceRule().level(score) == level


def test_thresholds_are_configurable_and_ordered():
    rule = ResearchRelevanceRule(high=0.5, mid=0.2)
    assert [rule.level(x) for x in (0.6, 0.3, 0.1)] == ["high", "mid", "low"]
    with pytest.raises(ValueError):
        ResearchRelevanceRule(high=0.8, mid=0.9)


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


async def test_reference_relevance_comes_from_the_precheck_memo():
    pre = MemoPrecheck(
        [
            _related("scienceon:p1", 0.91),
            _related("scienceon:p2", 0.889),
            _related("scienceon:p3", 0.87),
        ]
    )
    uc = CompareProjects(_repo(), precheck=pre)
    req = REQ.model_copy(
        update={"reference_ids": ["scienceon:p1", "scienceon:p2", "scienceon:p3", "scienceon:p4"]}
    )
    table = await uc(req, [], similar_only=True)
    got = {c.doc_id: (c.relevance, c.similarity) for c in table.projects}
    assert got == {
        "scienceon:p1": ("high", 0.91),
        "scienceon:p2": ("mid", 0.889),
        "scienceon:p3": ("low", 0.87),
        "scienceon:p4": (None, None),  # 관련 연구 목록 밖 — 관련도 없음
    }
    assert pre.searched == 0
    payload = comparison_payload(table)
    assert [p["relevance"] for p in payload["projects"]] == ["high", "mid", "low", None]


async def test_reference_relevance_recomputes_the_research_search_without_memo():
    pre = NoMemoPrecheck([_related("scienceon:p2", 0.9)])
    uc = CompareProjects(
        _repo(), precheck=pre, relevance=ResearchRelevanceRule(high=0.95, mid=0.85)
    )
    req = REQ.model_copy(update={"reference_ids": ["scienceon:p2"]})
    table = await uc(req, [], similar_only=True)
    (col,) = table.projects
    assert col.kind == "reference" and col.relevance == "mid" and pre.searched == 1


async def test_no_references_no_research_search():
    pre = NoMemoPrecheck([_related("scienceon:p2", 0.9)])
    table = await CompareProjects(_repo(), precheck=pre)(REQ, [], similar_only=True)
    assert table.projects == [] and pre.searched == 0


# ── 설정·PrecheckOverlap ─────────────────────────────────
def test_repo_config_holds_the_measured_thresholds(tmp_path):
    from rra.config_loader import research_relevance
    from rra.settings import Settings

    root = Path(__file__).resolve().parents[2]
    s = Settings(_env_file=None, config_dir=root / "config", data_dir=tmp_path / "data")
    assert research_relevance(s) == ResearchRelevanceRule(high=0.895, mid=0.885)
    assert research_relevance(s) == ResearchRelevanceRule()  # 도메인 기본값과 같다


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
