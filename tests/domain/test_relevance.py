"""생성 근거 검색의 관련도 하한 (이슈 #2) — 순수 규칙 + 골든셋 측정값으로 임계치 고정."""

from __future__ import annotations

import json
from pathlib import Path

from rra.domain.models import Chunk
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.relevance import RelevanceFloor, drop_reason, filter_chunks, has_hangul

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "relevance_golden.json"
KW = KeywordRule()
QUERY = "궤도 틀림 상시 감지 센서"


def chunk(text: str, sim: float | None, cid: str = "x:1#0") -> Chunk:
    return Chunk(chunk_id=cid, doc_id=cid.split("#")[0], ordinal=0, text=text, similarity=sim)


def test_defaults_match_overlap_yaml_measurement():
    floor = RelevanceFloor()
    assert floor.min_similarity == 0.79 and floor.min_keyword_hits == 1


def test_similarity_below_floor_is_dropped_regardless_of_language():
    floor = RelevanceFloor()
    assert drop_reason(chunk("track geometry", 0.78), QUERY, floor, KW) == "similarity"
    assert drop_reason(chunk("궤도 틀림 감지", 0.70), QUERY, floor, KW) == "similarity"
    assert drop_reason(chunk("track geometry", 0.79), QUERY, floor, KW) is None  # 경계는 포함


def test_hangul_chunk_needs_a_shared_query_keyword_but_english_does_not():
    floor = RelevanceFloor()
    assert drop_reason(chunk("자산개발 사례 조사", 0.85), QUERY, floor, KW) == "keywords"
    assert drop_reason(chunk("궤도의 틀림을 센서로 본다", 0.85), QUERY, floor, KW) is None
    # 영어 논문: 한국어 질의와 토큰이 겹칠 수 없으므로 유사도만 본다
    assert drop_reason(chunk("Track geometry monitoring with IMU", 0.85), QUERY, floor, KW) is None
    assert has_hangul("abc") is False and has_hangul("abc 가") is True


def test_missing_similarity_means_no_vector_index_so_only_keywords_apply():
    floor = RelevanceFloor()
    assert drop_reason(chunk("english only", None), QUERY, floor, KW) is None
    assert drop_reason(chunk("무관한 한글", None), QUERY, floor, KW) == "keywords"
    assert drop_reason(chunk("궤도 틀림", None), QUERY, floor, KW) is None


def test_zero_keyword_hits_disables_the_keyword_condition():
    floor = RelevanceFloor(min_keyword_hits=0)
    assert drop_reason(chunk("무관한 한글", 0.9), QUERY, floor, KW) is None


def test_filter_keeps_order_and_reports_reasons():
    chunks = [
        chunk("Track geometry", 0.83, "openalex:W1#0"),
        chunk("자산개발 현황", 0.81, "alio:1#0"),
        chunk("Rail noise", 0.75, "openalex:W2#0"),
        chunk("궤도 틀림 감지", 0.88, "alio:2#0"),
    ]
    kept, dropped = filter_chunks(chunks, QUERY, RelevanceFloor(), KW)
    assert [c.chunk_id for c in kept] == ["openalex:W1#0", "alio:2#0"]
    assert [(c.chunk_id, r) for c, r in dropped] == [
        ("alio:1#0", "keywords"),
        ("openalex:W2#0", "similarity"),
    ]


# ── 골든셋 측정값으로 임계치 고정 (2026-10-26, multilingual-e5-base, DB 21건) ──────────
def _golden_chunks(idea: dict) -> tuple[str, list[Chunk], set[str]]:
    """측정값 재현: 한글 청크는 질의 키워드를 측정된 개수만큼 담고, 영어 청크는 안 담는다."""
    keywords = idea["query_keywords"]
    query = " ".join(keywords)
    chunks, relevant = [], set()
    for row in idea["chunks"]:
        if row["hangul"]:
            text = " ".join(keywords[: row["keyword_hits"]]) + " 한글 본문임"
        else:
            text = "english abstract text"
        chunks.append(chunk(text, row["similarity"], row["chunk_id"]))
        if row["relevant"]:
            relevant.add(row["chunk_id"])
    return query, chunks, relevant


def test_fixture_reproduces_measured_keyword_hits():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    from rra.domain.rules.keywords import keyword_overlap

    for idea in data["ideas"].values():
        query, chunks, _ = _golden_chunks(idea)
        for row, c in zip(idea["chunks"], chunks, strict=True):
            assert len(keyword_overlap(query, c.text, KW)) == row["keyword_hits"], row["chunk_id"]


def test_golden_03_unrelated_idea_keeps_no_evidence():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    query, chunks, _ = _golden_chunks(data["ideas"]["03_unrelated_library"])
    kept, dropped = filter_chunks(chunks, query, RelevanceFloor(), KW)
    assert kept == [] and len(dropped) == 20
    # 무관한 한글 요약 3건은 유사도가 하한을 넘지만(0.79~0.80) 키워드 0건이라 빠진다
    over = [(c, r) for c, r in dropped if c.similarity >= 0.79]
    assert len(over) == 3 and all(
        r == "keywords" and c.chunk_id.startswith("alio:") for c, r in over
    )


def test_golden_01_related_idea_keeps_every_relevant_paper_and_drops_the_unrelated_summary():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    query, chunks, relevant = _golden_chunks(data["ideas"]["01_track_irregularity"])
    kept, dropped = filter_chunks(chunks, query, RelevanceFloor(), KW)
    assert {c.chunk_id for c in kept} == relevant and len(kept) == 16
    assert all(c.chunk_id.startswith("alio:") for c, _ in dropped) and len(dropped) == 4
    assert all(r == "keywords" for c, r in dropped if c.similarity >= 0.79)  # 0.80·0.796·0.795


def test_golden_02_own_summary_passes_with_shared_keywords():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    query, chunks, relevant = _golden_chunks(data["ideas"]["02_asset_development"])
    kept, _ = filter_chunks(chunks, query, RelevanceFloor(), KW)
    assert relevant <= {c.chunk_id for c in kept}
    # 알려진 한계: 자산개발 질의에도 궤도 논문 2건이 0.79 를 간신히 넘는다 (영어는 키워드 조건 X)
    assert sum(1 for c in kept if c.chunk_id.startswith("openalex:")) == 2


def test_balance_sources_guarantees_each_source_then_fills_by_rank():
    from rra.domain.rules.relevance import balance_sources

    ranked = [chunk("k", 0.9, f"own:{i}#0") for i in range(10)] + [
        chunk("e", 0.9, f"openalex:W{i}#0") for i in range(10)
    ]
    out = balance_sources(ranked, 8, 3)
    ids = [c.chunk_id for c in out]
    assert len(ids) == 8 and sum(i.startswith("openalex") for i in ids) == 3
    assert ids[:5] == [f"own:{i}#0" for i in range(5)]  # 순위 순서 유지(보장분 뒤 채움)
    assert balance_sources(ranked, 8, 0) == ranked[:8]  # 끔
    assert balance_sources(ranked[:5], 8, 3) == ranked[:5]  # k 보다 적으면 그대로
    assert balance_sources(ranked, 0, 3) == []
    assert RelevanceFloor().min_per_source == 4 and RelevanceFloor().search_multiplier == 4
