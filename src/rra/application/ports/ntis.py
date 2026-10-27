"""NTIS 부가 조회 포트 — 성과검색·연관콘텐츠 추천 + 과제번호 캐시. 어댑터:

adapters/sources/ntis/insights.py, adapters/persistence/file_cache.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProjectOutcomePort(Protocol):
    """과제번호 → 성과(논문·특허) 원시 dict 목록
    ({kind,title,year,venue,result_id,registration_no}). 비신뢰."""

    async def outcomes(self, project_no: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class RelatedProjectPort(Protocol):
    """과제번호 → 연관 과제 원시 dict 목록 ({project_no,title,score,rank}). 비신뢰."""

    async def related(self, project_no: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class CachePort(Protocol):
    """키 → JSON 값. 만료는 어댑터가 ttl 로. 값에 비밀을 넣지 않는다."""

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any) -> None: ...
