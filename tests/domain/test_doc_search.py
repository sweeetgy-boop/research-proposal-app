"""문서 단위 검색 규칙 (domain/rules/doc_search, 2026-10-29 [UI] 레인 3)."""

from rra.domain.rules.doc_search import excerpt, first_per_doc, looks_like_doc_id, year_in_range


def test_first_per_doc_keeps_order_and_first_chunk():
    hits = [("a", 1), ("b", 1), ("a", 2), ("c", 1), ("b", 2)]
    assert first_per_doc(hits, lambda h: h[0]) == [("a", 1), ("b", 1), ("c", 1)]


def test_year_in_range():
    assert year_in_range(None, None, None)
    assert not year_in_range(None, 2020, None)  # 거르기를 켜면 연도 모르는 문서는 빠진다
    assert year_in_range(2020, 2020, 2020)
    assert not year_in_range(2019, 2020, None)
    assert not year_in_range(2027, None, 2026)


def test_excerpt_flattens_and_truncates():
    assert excerpt(" 가  나\n다 ") == "가 나 다"
    long = excerpt("가" * 400)
    assert len(long) == 300 and long.endswith("…")
    assert excerpt(None) == ""


def test_looks_like_doc_id():
    assert looks_like_doc_id("openalex:fake-1")
    assert looks_like_doc_id("alio:sum-0f3a#2")
    assert not looks_like_doc_id("궤도 틀림")
    assert not looks_like_doc_id("ratio: 3")
