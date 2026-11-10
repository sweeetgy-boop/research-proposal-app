from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CodeCountPort(Protocol):
    """저장 자료에 실제로 붙어 있는 분류 코드 건수 — 문서 저장소의 선택 기능(ADR 0065).

    분류 코드 후보(AI 가 낸 것)가 실제로 쓰이는 코드인지 확인하는 데만 쓴다. 저장소가 이 메서드를
    갖지 않으면 호출자는 그 확인을 건너뛴다.
    """

    async def count_by_code(self, prefix: str) -> int:
        """코드(IPC)가 prefix 로 시작하는 문서 수. prefix 는 `problem_card.ipc_group_prefix`
        꼴("A01M 29/" 또는 "A01M") — 저장 표기("A01M-029/00")는 구현이 맞춘다."""
        ...

    async def count_by_science_class(self, name: str) -> int:
        """국가과학기술표준분류 이름(예: 철도교통기술)이 붙은 문서 수."""
        ...
