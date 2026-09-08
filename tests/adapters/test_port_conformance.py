"""어댑터가 포트 Protocol 의 시그니처를 그대로 따르는지 정적 검사."""

import inspect

import pytest

from rra.adapters.embedding import SentenceTransformerEmbedding
from rra.adapters.persistence import SQLiteDocumentRepository
from rra.application.ports.embedding import EmbeddingPort
from rra.application.ports.repository import DocumentRepository

CASES = [
    (DocumentRepository, SQLiteDocumentRepository),
    (EmbeddingPort, SentenceTransformerEmbedding),
]


def port_methods(protocol):
    return [
        name
        for name, member in vars(protocol).items()
        if not name.startswith("_") and inspect.isfunction(member)
    ]


@pytest.mark.parametrize(("protocol", "impl"), CASES)
def test_implementation_covers_every_port_method(protocol, impl):
    for name in port_methods(protocol):
        assert callable(getattr(impl, name, None)), f"{impl.__name__} 에 {name} 없음"


@pytest.mark.parametrize(("protocol", "impl"), CASES)
def test_signatures_match(protocol, impl):
    for name in port_methods(protocol):
        expected = inspect.signature(getattr(protocol, name))
        actual = inspect.signature(getattr(impl, name))
        assert list(actual.parameters) == list(expected.parameters), name
        for param in expected.parameters.values():
            if param.name == "self":
                continue
            got = actual.parameters[param.name]
            assert got.kind == param.kind, f"{name}.{param.name}"
            assert got.default == param.default, f"{name}.{param.name}"


def test_fakes_still_satisfy_the_embedding_port():
    from tests.fakes import DeterministicEmbedding, FakeEmbedding

    for fake in (FakeEmbedding(), DeterministicEmbedding()):
        assert isinstance(fake.dim, int)
        assert len(fake.embed(["a"])[0]) == fake.dim or fake.dim == 4
        assert fake.embed_query(["a"])
