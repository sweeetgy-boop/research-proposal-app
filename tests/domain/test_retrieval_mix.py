"""근거 구성 규칙(retrieval_mix) — 섹션별 허용 doc_type, 논문·보고서·특허 최소 보장, 유사과제 판정
제외."""

from rra.domain.models import Chunk, Document
from rra.domain.rules.retrieval_mix import RetrievalMix, SectionMix

MIX = RetrievalMix(
    section_min_per_source=2,
    sections={
        "tech_importance": SectionMix(
            allow=("paper", "report", "patent", "internal_report", "rnd_project"), min_scholarly=2
        ),
        "policy_importance": SectionMix(allow=("policy",)),
    },
    overlap_exclude=("policy", "korail_news"),
)
TYPES = {
    "openalex:W1": "paper",
    "openalex:W2": "paper",
    "own:1": "rnd_project",
    "alio:1": "internal_report",
    "korail_web:p1": "policy",
}


def chunk(doc_id, n=0):
    return Chunk(chunk_id=f"{doc_id}#{n}", doc_id=doc_id, ordinal=n, text="t")


def test_filter_keeps_allowed_types_unknown_types_and_overlap_chunks():
    chunks = [chunk("korail_web:p1"), chunk("own:1"), chunk("zzz:new"), chunk("openalex:W1")]
    overlap = Chunk(chunk_id="alio:9#overlap", doc_id="alio:9", ordinal=0, text="x")
    kept = MIX.filter("tech_importance", [*chunks, overlap], TYPES)
    assert [c.doc_id for c in kept] == ["own:1", "zzz:new", "openalex:W1", "alio:9"]
    assert MIX.filter("objective", chunks, TYPES) == chunks  # 규칙 없는 섹션은 전부
    assert MIX.filter("policy_importance", [chunk("own:1")], TYPES) == [
        chunk("own:1")
    ]  # 0건 → 전부
    assert MIX.filter("tech_importance", chunks, {}) == chunks  # doc_type 모르면 거르지 않는다


def test_top_up_scholarly_adds_papers_from_pool_until_minimum():
    picked = [chunk("own:1"), chunk("alio:1")]
    pool = [
        chunk("own:1"),
        chunk("alio:1"),
        chunk("openalex:W1"),
        chunk("korail_web:p1"),
        chunk("openalex:W2"),
    ]
    assert MIX.scholarly_shortfall("tech_importance", picked, TYPES) == 2
    out = MIX.top_up_scholarly("tech_importance", picked, pool, TYPES)
    assert [c.doc_id for c in out] == ["own:1", "alio:1", "openalex:W1", "openalex:W2"]
    assert MIX.scholarly_shortfall("tech_importance", out, TYPES) == 0
    assert MIX.top_up_scholarly("objective", picked, pool, TYPES) == picked  # 보장 없는 섹션


def test_overlap_candidates_drop_policy_and_news_documents():
    def doc(doc_id, doc_type, source="alio"):
        return Document(doc_id=doc_id, source=source, doc_type=doc_type, title="t")

    hits = [(doc("own:1", "rnd_project", "own"), 0.9), (doc("alio:p", "internal_report"), 0.95)]
    mix = RetrievalMix(overlap_exclude=("internal_report",))
    kept = mix.overlap_candidates(hits, lambda d: d.doc_type)
    assert [d.doc_id for d, _ in kept] == ["own:1"]
    assert RetrievalMix().overlap_candidates(hits, lambda d: d.doc_type) == hits
