"""유사과제 판정 후보 = 과제형 자료원만 (ADR 0028) — domain/rules/overlap_candidates."""

from __future__ import annotations

from datetime import date

from rra.domain.models import Document
from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember
from rra.domain.rules.retrieval_mix import RetrievalMix

RULE = OverlapCandidateRule(
    project=(
        SourceMember(source="own"),
        SourceMember(source="alio"),
        SourceMember(source="ntis", doc_types=("rnd_project",)),
        SourceMember(source="g2b"),
    ),
    research=(
        SourceMember(source="scienceon"),
        SourceMember(source="openalex"),
        SourceMember(source="ntis", doc_types=("report",)),
    ),
    research_k=2,
)


def doc(doc_id, source, doc_type, **kw):
    return Document(doc_id=doc_id, source=source, doc_type=doc_type, title=f"제목 {doc_id}", **kw)


HITS = [
    (doc("scienceon:a1", "scienceon", "paper", pub_date=date(2024, 3, 1), url="https://s/1"), 0.90),
    (doc("ntis:rep", "ntis", "report"), 0.89),
    (doc("alio:1", "alio", "internal_report"), 0.88),
    (doc("scienceon:r1", "scienceon", "internal_report"), 0.87),  # ScienceON 보고서도 연구
    (doc("own:1", "own", "rnd_project"), 0.86),
    (doc("ntis:prj", "ntis", "rnd_project"), 0.85),
    (doc("openalex:W1", "openalex", "paper"), 0.84),
    (doc("g2b:1", "g2b", "procurement"), 0.83),
    (doc("korail_web:p", "korail_web", "policy"), 0.82),
]


def test_project_hits_keep_only_project_sources_and_ntis_projects():
    kept = [d.doc_id for d, _ in RULE.project_hits(HITS)]
    assert kept == ["alio:1", "own:1", "ntis:prj", "g2b:1"]
    assert RULE.project_sources() == ["own", "alio", "ntis", "g2b"]
    assert RULE.research_sources() == ["scienceon", "openalex", "ntis"]


def test_related_research_is_top_k_by_similarity_with_year_and_url():
    rows = RULE.related_research(HITS)
    assert [r.doc_id for r in rows] == ["scienceon:a1", "ntis:rep"]  # research_k=2
    first = rows[0]
    assert first.source == "scienceon" and first.doc_type == "paper"
    assert first.year == 2024 and first.url == "https://s/1" and first.similarity == 0.90
    assert rows[1].year is None


def test_empty_rule_restricts_nothing():
    rule = OverlapCandidateRule()
    assert not rule.restricts and rule.project_hits(HITS) == HITS
    assert rule.related_research(HITS) == [] and rule.project_sources() == []


def test_retrieval_mix_applies_candidate_rule_after_doc_type_exclusion():
    mix = RetrievalMix(overlap_exclude=("policy",), candidates=RULE)
    kept = [d.doc_id for d, _ in mix.overlap_candidates(HITS, lambda d: d.doc_type)]
    assert kept == ["alio:1", "own:1", "ntis:prj", "g2b:1"]
    plain = RetrievalMix(overlap_exclude=("policy",))
    assert len(plain.overlap_candidates(HITS, lambda d: d.doc_type)) == len(HITS) - 1
