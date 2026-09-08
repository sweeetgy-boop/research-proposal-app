from __future__ import annotations

from typing import Protocol


class PromptLibraryPort(Protocol):
    """프롬프트 텍스트 공급자.

    프롬프트는 코드가 아니라 자산이므로 파일로 두고, 유스케이스는 이 포트로만 읽는다.
    (application 이 adapters 를 import 하지 않도록 하는 유일한 통로)
    """

    def system(self) -> str:
        """공통 시스템 프롬프트. A: <doc> 구획 무시 규칙과 JSON 강제를 포함한다."""
        ...

    def section(self, key: str) -> str:
        """섹션별 작성 지시. 미정의 키는 예외."""
        ...
