"""LLMStatusPort 구현 — 원격 LLM 연결 상태 파일 (ADR 0055).

`<data_dir>/cache/llm_status.json` = {"<provider>": {"status", "since", "checked_at"}}. 어댑터
(OpenAICompatLLM._request)가 호출이 끝날 때마다 기록하고 `/healthz` 가 읽는다. API·CLI·MCP
프로세스가 같은 파일을 본다 — 쓰기는 스레드 락 + 원자적 교체(runs/_fs.write_json, 600).

추가 API 호출 없음(이미 하는 호출의 결과만). 같은 상태가 이어지면 `min_write_interval` 초 안의
기록은 건너뛴다(성공 호출마다 디스크를 쓰지 않게). 기록 실패는 삼킨다 — 상태 표시가 호출을 막지
않는다. 열거값·시각만 담는다(키·주소·응답 본문 없음, 보안 D).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import ensure_dir, read_json, write_json
from rra.domain.rules import llm_status

logger = logging.getLogger("rra.llm")


def _now() -> datetime:
    return datetime.now(UTC).astimezone()


class FileLLMStatus:
    def __init__(
        self,
        path: Path,
        *,
        now: Callable[[], datetime] = _now,
        min_write_interval: float = 60.0,
    ):
        self.path = Path(path)
        self._now = now
        self.min_write_interval = max(0.0, float(min_write_interval))
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"FileLLMStatus({self.path})"

    def _read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = read_json(self.path)
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def snapshot(self, provider: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._read_all().get(provider)
        return dict(found) if isinstance(found, dict) else None

    def _fresh(self, prev: dict[str, Any], status: str, now: datetime) -> bool:
        """같은 상태를 최근에 이미 적었는지 — 그러면 쓰지 않는다."""
        if prev.get("status") != status or not self.min_write_interval:
            return False
        try:
            checked = datetime.fromisoformat(str(prev.get("checked_at")))
        except ValueError:
            return False
        return 0 <= (now - checked).total_seconds() < self.min_write_interval

    def record(self, provider: str, status: str) -> None:
        if status not in llm_status.STATES:
            return
        now = self._now()
        try:
            with self._lock:
                data = self._read_all()
                prev = data.get(provider) if isinstance(data.get(provider), dict) else {}
                if self._fresh(prev, status, now):
                    return
                data[provider] = llm_status.advance(prev, status, now.isoformat(timespec="seconds"))
                ensure_dir(self.path.parent)
                write_json(self.path, data)
        except OSError as exc:  # 기록 실패가 호출을 막지 않는다
            logger.debug("llm.status_write_failed err=%s", type(exc).__name__)
