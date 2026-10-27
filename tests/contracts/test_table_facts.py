"""TableFactRepository·CorpusAccessPort 계약 (P2-8·P2-9) — SQLite 와 InMemory fake 가 같은 테스트를
통과.

계약:
- replace_facts 는 문서 단위 통째 교체(멱등), 빈 목록이면 삭제
- search_facts: 항목에 질의 토큰이 전부 포함된 사실만, 빈 질의 → [], k 상한, LIKE 와일드카드는
  리터럴
- facts_for: 있는 문서만 키, 순서 유지, 값·단위·연도 왕복
- fact_counts: doc_id 접두어(자료원)별 건수
- sample_chunks: ≤ limit, 자료원별로 섞임 / documents_of: 그 자료원만 doc_id 순
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rra.application.ports import CorpusAccessPort, TableFactRepository
from rra.domain.models import Chunk, Document, TableFact
from tests.fakes import DeterministicEmbedding, InMemoryRepository


def fact(doc_id: str, item: str, value: str, **kw) -> TableFact:
    return TableFact(doc_id=doc_id, item=item, value=Decimal(value), value_text=value, **kw)


FACTS_A = [
    fact("korail_web:a", "합계 엘리베이터", "1512", unit="대", year=2026, page=None, sheet="현황"),
    fact("korail_web:a", "경부선 서울역사 엘리베이터", "18", row_label="경부선 서울역사"),
    fact("korail_web:a", "100%_구간", "3.5", unit="%"),
]
FACTS_B = [fact("molit:b", "철도 투자 예산", "5100", unit="억원", year=2023, basis="text")]


def docs():
    return [
        Document(
            doc_id="korail_web:a",
            source="korail_web",
            doc_type="policy",
            title="승강설비",
            body="표",
        ),
        Document(
            doc_id="molit:b", source="molit", doc_type="policy", title="투자계획", body="예산 표"
        ),
        Document(
            doc_id="alio:c", source="alio", doc_type="internal_report", title="보고서", body="본문"
        ),
    ]


def chunks():
    return [
        Chunk(
            chunk_id="korail_web:a#0", doc_id="korail_web:a", ordinal=0, text="역별 승강설비 현황"
        ),
        Chunk(chunk_id="korail_web:a#1", doc_id="korail_web:a", ordinal=1, text="엘리베이터 수"),
        Chunk(chunk_id="molit:b#0", doc_id="molit:b", ordinal=0, text="철도 투자 계획"),
        Chunk(chunk_id="alio:c#0", doc_id="alio:c", ordinal=0, text="궤도 틀림 분석"),
    ]


@pytest.fixture(params=["memory", "sqlite"])
async def repo(request, tmp_path):
    if request.param == "memory":
        r = InMemoryRepository()
        r.seed(docs(), chunks())
        yield r
        return
    from rra.adapters.persistence import SQLiteDocumentRepository

    r = SQLiteDocumentRepository(
        tmp_path / "rra.sqlite", DeterministicEmbedding(), prefer_extension=False
    )
    await r.upsert(docs(), chunks())
    yield r
    r.close()


async def test_ports_and_replace_is_idempotent(repo):
    assert isinstance(repo, TableFactRepository) and isinstance(repo, CorpusAccessPort)
    assert await repo.replace_facts("korail_web:a", FACTS_A) == 3
    assert await repo.replace_facts("korail_web:a", FACTS_A) == 3  # 두 번 넣어도 3건
    assert await repo.replace_facts("molit:b", FACTS_B) == 1
    found = await repo.facts_for(["korail_web:a", "molit:b", "없는:문서"])
    assert set(found) == {"korail_web:a", "molit:b"}
    assert [f.item for f in found["korail_web:a"]] == [f.item for f in FACTS_A]
    first = found["korail_web:a"][0]
    assert first.value == 1512 and first.unit == "대" and first.year == 2026
    assert first.sheet == "현황" and first.basis == "text" and first.trust == "untrusted"
    assert found["korail_web:a"][2].value == Decimal("3.5")
    assert await repo.fact_counts() == {"korail_web": 3, "molit": 1}
    assert await repo.replace_facts("korail_web:a", []) == 0
    assert await repo.facts_for(["korail_web:a"]) == {} and await repo.facts_for([]) == {}


async def test_search_facts_by_item_tokens(repo):
    await repo.replace_facts("korail_web:a", FACTS_A)
    await repo.replace_facts("molit:b", FACTS_B)
    hits = await repo.search_facts("엘리베이터")
    assert {h.item for h in hits} == {"합계 엘리베이터", "경부선 서울역사 엘리베이터"}
    assert [h.item for h in await repo.search_facts("서울역사 엘리베이터")] == [
        "경부선 서울역사 엘리베이터"
    ]
    assert [h.item for h in await repo.search_facts("예산")] == ["철도 투자 예산"]
    assert await repo.search_facts("") == [] and await repo.search_facts("   ") == []
    assert await repo.search_facts("없는항목") == []
    assert len(await repo.search_facts("엘리베이터", k=1)) == 1
    # 와일드카드·구두점은 검색 연산자가 아니다 — "%" 는 토큰에서 사라지고 "100" 만 남는다
    assert [h.item for h in await repo.search_facts("100%")] == ["100%_구간"]
    assert await repo.search_facts("_") == []


async def test_corpus_access(repo):
    sample = await repo.sample_chunks(3)
    assert 1 <= len(sample) <= 3 and all(isinstance(c, Chunk) for c in sample)
    assert await repo.sample_chunks(0) == []
    ids = [d.doc_id for d in await repo.documents_of("korail_web")]
    assert ids == ["korail_web:a"]
    assert [d.doc_id for d in await repo.documents_of("molit", limit=0)] == []
    assert await repo.documents_of("없는자료원") == []
