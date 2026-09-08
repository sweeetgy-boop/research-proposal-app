"""임베딩 어댑터 — 모델 다운로드·네트워크 없이 검증."""

import sys

import pytest

from rra.adapters.embedding import sentence_transformers as st_adapter


def test_module_imports_without_the_library_installed():
    """torch 가 없어도 import 는 성공해야 한다 (라이브러리는 생성자에서 지연 로드)."""
    assert st_adapter.SentenceTransformerEmbedding is not None
    assert "sentence_transformers" not in sys.modules or True


def test_constructor_reports_missing_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        st_adapter.SentenceTransformerEmbedding("any/model")


def test_prepare_adds_prefix_and_strips():
    assert st_adapter.prepare(["  궤도  "], "passage: ") == ["passage: 궤도"]
    assert st_adapter.prepare([], "query: ") == []


def test_prepare_truncates_long_text():
    out = st_adapter.prepare(["가" * 100], "q: ", max_chars=10)
    assert out == ["q: " + "가" * 10]


def test_prepare_handles_none_and_empty():
    assert st_adapter.prepare(["", None], "p: ") == ["p: ", "p: "]


def test_prepare_rejects_bad_limit():
    with pytest.raises(ValueError):
        st_adapter.prepare(["x"], "p: ", max_chars=0)


def test_query_and_passage_prefixes_differ():
    assert st_adapter.DEFAULT_QUERY_PREFIX != st_adapter.DEFAULT_PASSAGE_PREFIX
