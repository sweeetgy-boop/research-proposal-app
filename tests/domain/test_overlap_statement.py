"""5. 특이사항 — 유사과제 없음 확정 문장은 실제 검토 범위와 미수집 자료원을 밝힌다."""

from rra.domain.models import Chunk, OverlapAlert, RetrievalSnapshot
from rra.domain.rules.overlap import no_overlap_statement, uncollected_sources


def test_statement_lists_scope_and_uncollected_sources():
    texts = no_overlap_statement({"openalex": 16, "alio": 1}, ["scienceon", "ntis"])
    assert texts[0] == (
        "유사과제 검토 범위는 수집 자료 중 본 제안과 관련도가 높은 "
        "알리오 공시 연구보고서 1건, OpenAlex 해외 논문 16건임."
    )
    assert texts[1] == (
        "NTIS 국가R&D 과제·ScienceON 국내 논문·보고서은(는) 아직 수집되지 않아 "
        "검토 범위에 포함되지 않음."
    )
    assert "사내 0.80" in texts[2] and texts[2].endswith("확인되지 않음.")


def test_no_uncollected_line_when_everything_is_loaded_or_unknown():
    assert len(no_overlap_statement({"alio": 2}, [])) == 2
    assert len(no_overlap_statement({"alio": 2}, None)) == 2  # 이전 스냅샷: 확인 안 함


def test_empty_scope_does_not_claim_no_overlap():
    (text,) = no_overlap_statement({}, ["alio", "ntis"])
    assert "수행하지 못함" in text and "확인되지 않음" not in text


def test_uncollected_follows_source_types():
    assert uncollected_sources({"openalex": 3, "alio": 1}) == [
        "scienceon",
        "kipris_kr",
        "kipris_intl",
        "ntis",
    ]


def test_snapshot_scope_counts_documents_not_chunks():
    snap = RetrievalSnapshot.of(
        "q",
        [
            Chunk(chunk_id="openalex:W1#0", doc_id="openalex:W1", ordinal=0, text="a"),
            Chunk(chunk_id="openalex:W1#1", doc_id="openalex:W1", ordinal=1, text="b"),
            Chunk(chunk_id="alio:7#0", doc_id="alio:7", ordinal=0, text="c"),
        ],
        [OverlapAlert(doc_id="ntis:9", title="t", tier="external", similarity=0.3, blocking=False)],
    )
    assert snap.scope == {"openalex": 1, "alio": 1, "ntis": 1}
