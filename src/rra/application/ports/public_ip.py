"""공인 IP 조회·자료원 가용 상태 포트 (레인 I). 어댑터: adapters/sources/public_ip.py,

adapters/persistence/source_availability.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PublicIpPort(Protocol):
    """호출 기기의 현재 공인 IP. 실패는 예외 (호출자가 진단으로만 남긴다)."""

    async def current_ip(self) -> str: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class SourceAvailabilityPort(Protocol):
    """자료원별 마지막 차단 안내 (IP 거부 등). 비밀 없음.

    웹 자료원 상태·로그가 같은 문구를 보인다."""

    def record(self, source: str, notice: str | None) -> None:
        """notice=None 이면 해제."""
        ...

    def notice(self, source: str) -> str | None: ...

    def notices(self) -> dict[str, str]: ...
