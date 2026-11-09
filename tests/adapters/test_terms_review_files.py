"""레인 E 어댑터 — IDF JSON 캐시, 용어 후보 읽기, 검토표·overlap.yaml 후보 구역 쓰기 (ADR 0059)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from rra.adapters.terms import JsonIdfCache, TermsReviewFiles, YamlTermCandidatesReader
from rra.application.usecases.build_idf import BuildIdf, load_idf
from rra.application.usecases.terms_review import TermsReview
from rra.domain.models import Chunk, Document
from rra.domain.rules.idf import IdfWeights
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.synonyms import SynonymReview
from tests.fakes import InMemoryRepository

OVERLAP_YAML = """keywords:
  min_hits: 2
facets:
  enabled: false        # 4축
idf_weighting:
  enabled: false
synonyms:
  enabled: false        # 사람 검토 전에는 켜지 않는다
"""


def test_idf_cache_roundtrip_and_corruption(tmp_path: Path):
    cache = JsonIdfCache(tmp_path / "cache" / "idf.json")
    assert cache.load() is None
    cache.save(IdfWeights(values={"궤도": 1.5, "철도": 0.0}, documents=3, max_idf=1.5))
    loaded = cache.load()
    assert loaded is not None and loaded.values == {"궤도": 1.5, "철도": 0.0}
    assert loaded.documents == 3 and loaded.max_idf == 1.5
    assert oct((tmp_path / "cache" / "idf.json").stat().st_mode & 0o777) == "0o600"
    (tmp_path / "cache" / "idf.json").write_text('{"values": {"a": "x"}}', encoding="utf-8")
    assert cache.load() is None and load_idf(cache) is None


async def test_build_idf_scans_repo_chunks_per_document(tmp_path: Path):
    repo = InMemoryRepository()
    docs = [
        Document(doc_id=f"own:{i}", source="own", doc_type="rnd_project", title="t")
        for i in range(3)
    ]
    chunks = [
        Chunk(chunk_id="own:0#0", doc_id="own:0", ordinal=0, text="궤도 틀림 감지"),
        Chunk(chunk_id="own:0#1", doc_id="own:0", ordinal=1, text="궤도 보수"),
        Chunk(chunk_id="own:1#0", doc_id="own:1", ordinal=0, text="궤도 전차선"),
        Chunk(chunk_id="own:2#0", doc_id="own:2", ordinal=0, text="비둘기 퇴치"),
    ]
    repo.seed(docs, chunks)
    cache = JsonIdfCache(tmp_path / "idf.json")
    report = await BuildIdf(repo, cache)()
    assert (report.documents, report.chunks) == (3, 4)
    idf = cache.load()
    assert idf is not None and idf.values["궤도"] == round(__import__("math").log(3 / 2), 2)
    assert idf.values["비둘기"] == idf.max_idf


def test_terms_review_writes_markdown_and_replaces_only_candidates_block(tmp_path: Path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "overlap.yaml").write_text(OVERLAP_YAML, encoding="utf-8")
    rows = [
        {"term": "유지보수", "doc_freq": 155, "sources": {"own": 100}, "examples": ["d1", "d2"]},
        {"term": "유지관리", "doc_freq": 52, "sources": {"own": 50}, "examples": ["d2"]},
        {"term": "전차선", "doc_freq": 28, "sources": {}, "examples": []},
    ]
    (cfg / "rail_terms.candidates.yaml").write_text(
        yaml.safe_dump({"candidates": rows}, allow_unicode=True), encoding="utf-8"
    )
    review_path = tmp_path / "docs" / "review" / "terms-review.md"
    usecase = TermsReview(
        YamlTermCandidatesReader(cfg),
        TermsReviewFiles(review_path, cfg / "overlap.yaml"),
        KeywordRule(),
        today=lambda: date(2026, 11, 9),
    )
    report = usecase()
    assert (report.rows, report.high) == (3, 1) and report.reviews >= 2
    md = review_path.read_text(encoding="utf-8")
    assert (
        "| - [ ] | 유지보수 | 유지보수, 유지관리 | 207 | 1 |" in md
        and "검토 전 — 운영 반영 안 함" in md
    )
    text = (cfg / "overlap.yaml").read_text(encoding="utf-8")
    assert "enabled: false        # 사람 검토 전에는 켜지 않는다" in text  # 다른 줄은 그대로
    data = yaml.safe_load(text)
    assert data["synonyms"]["enabled"] is False
    assert data["synonyms"]["candidates"][0]["canonical"] == "유지보수"
    assert data["synonyms"]["candidates"][0]["terms"] == ["유지보수", "유지관리"]
    assert data["keywords"] == {"min_hits": 2} and data["facets"]["enabled"] is False
    # 두 번째 실행은 구역만 바꾼다 (표식이 하나)
    TermsReviewFiles(review_path, cfg / "overlap.yaml").write_candidates(
        [
            SynonymReview(
                canonical="전차선",
                variants=("전차선", "가선"),
                doc_freq=30,
                cooccur=0,
                confidence="high",
                basis="seed",
            )
        ]
    )
    text2 = (cfg / "overlap.yaml").read_text(encoding="utf-8")
    assert text2.count(">>> synonyms.candidates") == 1
    assert yaml.safe_load(text2)["synonyms"]["candidates"][0]["canonical"] == "전차선"


def test_candidates_reader_skips_missing_files(tmp_path: Path):
    assert YamlTermCandidatesReader(tmp_path).read() == []
