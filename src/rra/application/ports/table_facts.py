"""표 사실(P2-8)·코퍼스 표본(P2-9) 포트. 구현은 adapters/persistence(SQLite)·adapters/tables,
테스트는 tests/fakes.InMemoryRepository."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rra.domain.models import Chunk, Document, ParsedTable, TableFact


@runtime_checkable
class TableFactRepository(Protocol):
    """표 사실 저장소. DocumentRepository 와 같은 객체가 구현한다(같은 DB)."""

    async def replace_facts(self, doc_id: str, facts: list[TableFact]) -> int:
        """그 문서의 사실을 통째로 바꾼다 (빈 목록 = 삭제). 넣은 건수."""
        ...

    async def search_facts(self, query: str, *, k: int = 20) -> list[TableFact]:
        """항목(item)에 질의 토큰이 전부 들어 있는 사실. 빈 질의 → []."""
        ...

    async def facts_for(self, doc_ids: list[str]) -> dict[str, list[TableFact]]:
        """문서별 사실 (없는 문서는 키 없음)."""
        ...

    async def fact_counts(self) -> dict[str, int]:
        """자료원(doc_id 접두어)별 사실 수."""
        ...


@runtime_checkable
class TableSourcePort(Protocol):
    """표를 내는 쪽 — 스냅샷 첨부(xlsx·xls·pdf), 판독 캐시(표 이미지), DB 문서 본문."""

    name: str

    async def tables(self, *, limit: int | None = None) -> list[ParsedTable]:
        """표 격자 목록. 문서 하나가 여러 표(시트·쪽)를 낼 수 있다."""
        ...


@runtime_checkable
class CorpusAccessPort(Protocol):
    """용어 후보·본문 표 추출용 읽기 — 검색이 아니라 순차 접근."""

    async def sample_chunks(self, limit: int) -> list[Chunk]:
        """자료원별로 고르게 뽑은 청크 표본 (결정적 순서)."""
        ...

    async def documents_of(self, source: str, *, limit: int | None = None) -> list[Document]:
        """그 자료원의 문서 (doc_id 순)."""
        ...
