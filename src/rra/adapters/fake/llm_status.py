"""가짜 모드(RRA_FAKE_LLM=1) Argon 연결 상태 — e2e·화면 확인용 (ADR 0055). 파일을 읽지 않는다.

`RRA_FAKE_GEMINI_STATUS`(ok | key_invalid | quota | unavailable)를 주면 그 상태를 보고하고, 없으면
기록 없음(→ /healthz `unknown`). 기본은 꺼짐 — 다른 e2e 는 영향을 받지 않는다. 시각은 고정값.
"""

from __future__ import annotations

import os
from typing import Any

from rra.domain.rules import llm_status

FAKE_SINCE = "2026-11-03T16:14:49+09:00"


class FakeLLMStatus:
    def __init__(self, status: str | None = None) -> None:
        raw = (
            status if status is not None else os.environ.get("RRA_FAKE_GEMINI_STATUS", "")
        ).strip()
        self.status = raw if raw in llm_status.STATES else None

    def record(self, provider: str, status: str) -> None:
        return None  # 가짜 모드는 고정 상태

    def snapshot(self, provider: str) -> dict[str, Any] | None:
        if provider != "gemini" or self.status is None:
            return None
        return {"status": self.status, "since": FAKE_SINCE, "checked_at": FAKE_SINCE}
