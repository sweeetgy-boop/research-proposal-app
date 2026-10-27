"""섹션 프롬프트 [자료] 상한 (ADR 0027) — 청크 글자·기본 집합 개수."""

from rra.domain.models import Chunk
from rra.domain.rules.section_search import clip_chunks


def ch(i, text, suffix="#0"):
    return Chunk(chunk_id=f"d:{i}{suffix}", doc_id=f"d:{i}", ordinal=0, text=text)


def test_clip_cuts_long_text_and_limits_count_but_keeps_overlap_chunks():
    chunks = [ch(1, "a" * 700), ch(2, "b" * 100), ch(3, "c" * 50), ch(4, "o" * 900, "#overlap")]
    out = clip_chunks(chunks, max_chars=500, limit=2)
    assert [c.chunk_id for c in out] == ["d:1#0", "d:2#0", "d:4#overlap"]
    assert out[0].text == "a" * 500 + "…" and out[1].text == "b" * 100
    assert out[2].text == "o" * 500 + "…"
    assert chunks[0].text == "a" * 700  # 원본 불변 (스냅샷·근거 대조 집합은 그대로)


def test_zero_means_no_limit():
    chunks = [ch(1, "a" * 700), ch(2, "b")]
    assert clip_chunks(chunks) == chunks
    assert clip_chunks(chunks, max_chars=0, limit=0) == chunks
