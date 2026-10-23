"""어댑터가 포트 Protocol 의 시그니처를 그대로 따르는지 정적 검사."""

import inspect

import pytest

from rra.adapters.embedding import SentenceTransformerEmbedding
from rra.adapters.llm import FilePromptLibrary, OpenAICompatLLM
from rra.adapters.persistence import SQLiteDocumentRepository
from rra.adapters.sources import OpenAlexSource
from rra.adapters.sources.alio import AlioSource, FileCatalog
from rra.application.ports.catalog import CatalogPort
from rra.application.ports.embedding import EmbeddingPort
from rra.application.ports.llm import LLMPort
from rra.application.ports.prompt_library import PromptLibraryPort
from rra.application.ports.repository import DocumentRepository
from rra.application.ports.source import AcknowledgingSource, SourcePort

CASES = [
    (DocumentRepository, SQLiteDocumentRepository),
    (EmbeddingPort, SentenceTransformerEmbedding),
    (LLMPort, OpenAICompatLLM),
    (PromptLibraryPort, FilePromptLibrary),
    (SourcePort, OpenAlexSource),
    (SourcePort, AlioSource),
    (AcknowledgingSource, AlioSource),
    (CatalogPort, FileCatalog),
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


def test_fakes_still_satisfy_the_prompt_library_port():
    from tests.fakes import FakePromptLibrary

    fake = FakePromptLibrary()
    for name in port_methods(PromptLibraryPort):
        assert inspect.signature(getattr(FakePromptLibrary, name)) == inspect.signature(
            getattr(PromptLibraryPort, name)
        )
    assert fake.system() and fake.section("background")


async def test_fakes_still_satisfy_the_embedding_port():
    from tests.fakes import DeterministicEmbedding, FakeEmbedding

    for fake in (FakeEmbedding(), DeterministicEmbedding()):
        assert isinstance(fake.dim, int)
        assert len((await fake.embed(["a"]))[0]) == fake.dim or fake.dim == 4
        assert await fake.embed_query(["a"])


def test_openalex_declares_source_name():
    assert OpenAlexSource.source == "openalex"


# ── isinstance — 모든 포트는 runtime_checkable. 어댑터·fake 가 구조적으로 포트를 만족한다 ──
def _adapters(tmp_path, monkeypatch):
    """실물 어댑터 인스턴스. 모델·네트워크·LLM 서버 없이 만들 수 있어야 한다 (지연 로딩)."""
    import sys
    import types

    from rra.adapters.runs import FileRunLog, FileRunStore, FlockSlot
    from rra.adapters.sources.alio import AlioSummarySource, CatalogFetcher
    from rra.composition import (
        build_alio_catalog,
        build_alio_catalog_fetcher,
        build_embedding,
        build_llm,
        build_ntis_source,
        build_openalex_source,
        build_prompt_library,
        build_repository,
        build_scienceon_source,
        build_sources,
    )
    from rra.settings import Settings

    # sentence-transformers 가 실제로 로드되면 테스트가 느려진다 — 생성만 하고 모델은 올리지 않는다
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=pytest.fail)
    )
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "db.sqlite",
        runs_dir=tmp_path / "runs",
        scienceon_client_id="c",
        scienceon_key="k" * 32,
        scienceon_mac="AA-BB",
        ntis_key="n",
    )
    emb = build_embedding(settings)
    alio, alio_summary = build_sources(["alio", "alio_summary"], settings)
    assert isinstance(alio_summary, AlioSummarySource)
    (tmp_path / "sources.yaml").write_text(
        "alio: {catalog: {fetch_url: https://www.data.go.kr/x.csv}}\n", encoding="utf-8"
    )
    fetcher = build_alio_catalog_fetcher(
        Settings(_env_file=None, config_dir=tmp_path), resolver=lambda h: False
    )
    assert isinstance(fetcher, CatalogFetcher)
    return {
        "embedding": emb,
        "repo": build_repository(emb, settings),
        "llm": build_llm(settings),
        "prompts": build_prompt_library(settings),
        "openalex": build_openalex_source(settings),
        "alio": alio,
        "alio_summary": alio_summary,
        "catalog": build_alio_catalog(settings),
        "scienceon": build_scienceon_source(settings, resolver=lambda h: False),
        "ntis": build_ntis_source(settings, resolver=lambda h: False),
        "run_store": FileRunStore(tmp_path / "runs"),
        "run_log": FileRunLog(tmp_path / "runs"),
        "slot": FlockSlot(tmp_path / "runs" / ".lock"),
    }


ADAPTER_PORTS = {
    "embedding": ["EmbeddingPort"],
    "repo": ["DocumentRepository"],
    "llm": ["LLMPort", "ModelListingPort"],
    "prompts": ["PromptLibraryPort"],
    "openalex": ["SourcePort"],
    "alio": ["SourcePort", "AcknowledgingSource", "InboxSource"],
    "alio_summary": ["SourcePort", "AcknowledgingSource", "WarningSource", "InboxSource"],
    "catalog": ["CatalogPort"],
    "scienceon": ["SourcePort", "ProbingSource"],
    "ntis": ["SourcePort", "ProbingSource"],
    "run_store": ["RunStorePort"],
    "run_log": ["RunLogPort"],
    "slot": ["GenerationSlot"],
}


def test_every_adapter_is_an_instance_of_its_ports(tmp_path, monkeypatch):
    import rra.application.ports as ports

    objs = _adapters(tmp_path, monkeypatch)
    for key, names in ADAPTER_PORTS.items():
        for name in names:
            port = getattr(ports, name)
            assert isinstance(objs[key], port), f"{type(objs[key]).__name__} is not {name}"
    assert not objs["embedding"].loaded  # 생성·isinstance 만으로 모델을 올리지 않았다


def test_every_fake_is_an_instance_of_its_port(tmp_path):
    import rra.application.ports as ports
    from rra.domain.models import Draft
    from tests import fakes

    cases = [
        (fakes.FakeLLM(), ["LLMPort"]),
        (fakes.ListingLLM(), ["LLMPort", "ModelListingPort"]),
        (fakes.FakePromptLibrary(), ["PromptLibraryPort"]),
        (fakes.FakeEmbedding(), ["EmbeddingPort"]),
        (fakes.DeterministicEmbedding(), ["EmbeddingPort"]),
        (fakes.InMemoryRepository(), ["DocumentRepository"]),
        (fakes.FakeRenderer(), ["RendererPort"]),
        (fakes.FakeRunLog(), ["RunLogPort"]),
        (fakes.FakeSource("s", []), ["SourcePort"]),
        (fakes.FakeAckSource("s", []), ["SourcePort", "AcknowledgingSource"]),
        (fakes.FakeProbingSource("s"), ["ProbingSource"]),
        (fakes.FakeCatalog([]), ["CatalogPort"]),
        (fakes.InMemoryRunStore(), ["RunStorePort"]),
        (fakes.FakeSlot(), ["GenerationSlot"]),
    ]
    assert Draft  # RendererPort 가 참조하는 도메인 타입
    for obj, names in cases:
        for name in names:
            assert isinstance(obj, getattr(ports, name)), f"{type(obj).__name__} is not {name}"


def test_isinstance_rejects_objects_that_miss_a_method():
    from rra.application.ports import DocumentRepository, LLMPort

    class Half:
        def upsert(self, docs, chunks): ...

    assert not isinstance(Half(), DocumentRepository)
    assert not isinstance(object(), LLMPort)
