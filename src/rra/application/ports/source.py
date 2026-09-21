from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rra.domain.models import Document


class SourcePort(Protocol):
    source: str

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """원본 응답 반환. query=None 이면 증분 수집."""
        ...

    def normalize(self, raw: dict[str, Any]) -> Document:
        """순수 함수. 네트워크 접근 금지."""
        ...


@runtime_checkable
class AcknowledgingSource(Protocol):
    """저장이 끝난 raw 를 통보받는 소스 (선택). filedrop 처럼 처리 완료 표시가 필요한 경우."""

    def acknowledge(self, raws: list[dict[str, Any]]) -> None: ...


@runtime_checkable
class WarningSource(Protocol):
    """저장될 문서마다 경고를 돌려주는 소스 (선택). 반환: [(코드, 짧은 설명)]. 순수 함수.

    예: 공개 요약 inbox 가 카탈로그 매칭 없이 기본 기관 태그를 붙임 → ("assumed_org", "korail").
    """

    def ingest_warnings(self, doc: Document) -> list[tuple[str, str]]: ...
