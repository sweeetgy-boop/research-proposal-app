from __future__ import annotations

from typing import Any, Protocol


class RunLogPort(Protocol):
    def record(self, run_id: str, manifest: dict[str, Any]) -> None:
        """I: manifest 에는 해시·doc_id·모델명만. 원문 금지."""
        ...
