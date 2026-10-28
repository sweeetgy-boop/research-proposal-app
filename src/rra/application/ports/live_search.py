"""[4] 실시간 자료 검색 포트 (ADR 0031). 어댑터: adapters/sources/live.py,

저장소의 동일성 조회는 adapters/persistence/sqlite_repo.py(find_identities).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rra.domain.models import Document


@runtime_checkable
class LiveSourcePort(Protocol):
    """실시간 검색 자료원 하나 (scienceon·ntis·openalex).

    fetch 는 질의를 앞에서부터 보내 limit 건이 차면 멈추고, 정규화한 Document 를 돌려준다(비신뢰,
    A).
    세션 하나의 요청 수는 어댑터가 상한을 둔다. IP 거부는 SourceIpBlocked(domain) 로 올린다.
    lang: 이 자료원에 보낼 키워드 언어 (ko|en)."""

    source: str
    lang: str

    async def fetch(self, queries: list[str], limit: int) -> list[Document]: ...


@runtime_checkable
class IdentityLookupPort(Protocol):
    """저장소에 이미 있는 같은 문서 찾기 (선택) — {새 doc_id: 저장된 doc_id}.

    동일성은 domain/rules/live_search.identity (DOI·과제번호·보고서번호+제목·출원번호·정규화
    제목+연도). doc_id 가 같은 문서는 get_document 로 따로 본다."""

    async def find_identities(self, docs: list[Document]) -> dict[str, str]: ...


@runtime_checkable
class TimedAvailabilityPort(Protocol):
    """자료원 차단 안내가 기록된 시각 (선택, epoch 초). 없으면 None."""

    def recorded_at(self, source: str) -> float | None: ...
