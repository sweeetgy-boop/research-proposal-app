import pytest

from rra.domain.rules.fusion import reciprocal_rank_fusion


def test_rrf_scores_match_formula():
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], k=60)
    assert [i for i, _ in fused] == ["a", "b"]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1][1] == pytest.approx(1 / 62 + 1 / 61)


def test_document_in_both_rankings_beats_single_list_leader():
    fused = reciprocal_rank_fusion([["x", "shared"], ["y", "shared"]], k=1)
    assert fused[0][0] == "shared"


def test_ties_break_on_first_appearance_then_id():
    fused = reciprocal_rank_fusion([["b", "a"]], k=60)
    assert [i for i, _ in fused] == ["b", "a"]


def test_empty_input():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_invalid_k():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=0)
