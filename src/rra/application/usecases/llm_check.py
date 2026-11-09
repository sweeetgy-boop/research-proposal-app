"""`rra llm-check` 왕복 1회 — 시간 제한·무응답 처리 (계약 healthz-status.md §3, ADR 0062).

2026-11-03 로컬 서버(mlx)가 긴 생성 1건에 16분 넘게 붙들려 있는 동안 `rra llm-check` 는 읽기 제한
10분 × 재시도 3회를 조용히 기다렸다. 그래서 점검은 (1) 읽기 제한을 짧게(로컬 기본 120초, Argon 은
llm.yaml timeout.read) 재시도 없이 한 번만 보내고, (2) 무응답(시간 초과·연결 실패·서버 오류)이면
로컬 모델 상태를 `unavailable` 로 적고 사유 한 줄과 함께 끝낸다(멈춤 금지). 성공이면 `ok`.
클라이언트 자체(읽기 제한·재시도 1회)는 조립(`build_llm_check_client`)이 만들어 넘긴다.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable
from dataclasses import dataclass

from rra.application.ports.llm import LLMPort
from rra.application.ports.ops_status import OpsStatusWriterPort
from rra.domain.rules import ops_status

LOCAL_PROVIDERS = frozenset({"mlx", "local", "llama.cpp"})
LOCAL_DEFAULT_TIMEOUT_SEC = 120.0
# 어댑터 예외 `code` 중 "서버가 답하지 않았다" 로 보는 것 — 로컬이면 unavailable 로 적는다
UNRESPONSIVE_CODES = frozenset({"timeout", "connection", "server"})


def is_local_provider(provider: str) -> bool:
    return provider.lower() in LOCAL_PROVIDERS


def default_timeout(provider: str) -> float | None:
    """--timeout 이 없을 때 — 로컬 120초, 원격은 None(클라이언트 기본 = llm.yaml timeout.read)."""
    return LOCAL_DEFAULT_TIMEOUT_SEC if is_local_provider(provider) else None


@dataclass(frozen=True)
class LlmCheckResult:
    output: str | None  # 성공 응답(본문)
    seconds: float
    warning: str | None = None  # served_model 경고
    failure: RuntimeError | None = None  # 분류된 실패(어댑터 예외) — 호출 쪽이 분류만 표시한다
    local_state: str | None = None  # 로컬이면 ok|unavailable, 원격이면 None

    @property
    def unresponsive(self) -> bool:
        return self.local_state == ops_status.UNAVAILABLE


class LlmCheck:
    def __init__(
        self,
        llm: LLMPort,
        *,
        provider: str,
        status: OpsStatusWriterPort | None = None,
        served_check: Awaitable[str | None] | None = None,
    ):
        self.llm = llm
        self.local = is_local_provider(provider)
        self.status = status
        self.served_check = served_check

    def _record(self, state: str) -> None:
        if self.local and self.status is not None:
            self.status.record(ops_status.LLM_LOCAL, state)

    async def __call__(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> LlmCheckResult:
        started = time.monotonic()
        warning: str | None = None
        try:
            if self.served_check is not None:
                warning = await self.served_check
            output = await self.llm.complete(prompt, system=system, json_mode=json_mode)
        except RuntimeError as exc:  # 어댑터가 분류한 실패(code) — 본문은 싣지 않는다
            code = getattr(exc, "code", None)
            state = None
            if self.local and code in UNRESPONSIVE_CODES:
                state = ops_status.UNAVAILABLE
                self._record(state)
            return LlmCheckResult(
                output=None,
                seconds=time.monotonic() - started,
                warning=warning,
                failure=exc,
                local_state=state,
            )
        finally:
            close = getattr(self.llm, "aclose", None)  # 클라이언트를 반드시 닫는다
            if close is not None:
                await close()
        self._record(ops_status.OK)
        return LlmCheckResult(
            output=output,
            seconds=time.monotonic() - started,
            warning=warning,
            local_state=ops_status.OK if self.local else None,
        )
