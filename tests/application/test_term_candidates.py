"""용어 후보 유스케이스 (P2-9) — InMemoryRepository 표본 → 후보 두 벌 payload. 파일은 어댑터가
적는다."""

from __future__ import annotations

from datetime import date

from rra.application.usecases.term_candidates import (
    GENERIC_FILE,
    RAIL_FILE,
    ExtractTermCandidates,
)
from rra.domain.models import Chunk, Document
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.term_candidates import CandidateConfig
from tests.fakes import InMemoryRepository

BASE = "본 연구는 철도 안전을 위해 수행한다. "


def make_repo():
    texts = {
        "alio:1": BASE + "궤도 틀림을 검측차로 측정한다.",
        "alio:2": BASE + "궤도 침목 교체 주기를 분석한다. 분기기 마모.",
        "own:3": BASE + "전차선 마모 예측. 분기기 상태 진단.",
        "korail_web:4": BASE + "경영목표와 ESG 경영. 분기기 교체 계획.",
    }
    repo = InMemoryRepository()
    docs = [
        Document(doc_id=d, source=d.split(":")[0], doc_type="policy", title=d, body=t)
        for d, t in texts.items()
    ]
    chunks = [Chunk(chunk_id=f"{d}#0", doc_id=d, ordinal=0, text=t) for d, t in texts.items()]
    repo.seed(docs, chunks)
    return repo


async def test_candidates_from_repository_sample_and_payload_shape():
    usecase = ExtractTermCandidates(
        make_repo(),
        KeywordRule().with_extra_generic(["안전"]),
        config=CandidateConfig(min_doc_freq=2, generic_doc_ratio=0.6),
        today=lambda: date(2026, 10, 27),
    )
    report = await usecase(sample=100)
    assert report.documents == 4 and report.chunks == 4
    rail = {s.term for s in report.rail}
    generic = {s.term for s in report.generic}
    assert "궤도" in rail and "안전" not in rail | generic  # 이미 일반어
    assert "분기기" in generic  # 3/4 문서·자료원 3 → 흔한 말 후보 (사람이 되돌릴 수 있다)
    payloads = usecase.payloads(report)
    assert set(payloads) == {RAIL_FILE, GENERIC_FILE}
    rail_payload = payloads[RAIL_FILE]
    assert rail_payload["kind"] == "rail_terms" and rail_payload["generated"] == "2026-10-27"
    assert "자동 반영되지 않습니다" in rail_payload["notice"]
    assert rail_payload["sample"] == {
        "chunks": 4,
        "documents": 4,
        "sources": {"alio": 2, "korail_web": 1, "own": 1},
    }
    row = next(r for r in rail_payload["candidates"] if r["term"] == "궤도")
    assert row == {
        "term": "궤도",
        "doc_freq": 2,
        "chunk_freq": 2,
        "doc_ratio": 0.5,
        "sources": {"alio": 2},
        "examples": ["alio:1", "alio:2"],
        "hint": "rail_seed",
    }
    assert rail_payload["config"]["min_doc_freq"] == 2
    generic_row = next(r for r in payloads[GENERIC_FILE]["candidates"] if r["term"] == "분기기")
    assert generic_row["doc_freq"] == 3 and generic_row["hint"] == "rail_seed"


async def test_limit_overrides_config_limit():
    usecase = ExtractTermCandidates(
        make_repo(), KeywordRule(), config=CandidateConfig(min_doc_freq=1, limit=50)
    )
    report = await usecase(sample=100, limit=1)
    assert len(report.rail) == 1 and len(report.generic) <= 1
