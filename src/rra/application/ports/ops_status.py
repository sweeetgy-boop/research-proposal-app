"""운영 상태(터널·로컬 모델) 포트 (계약 docs/contracts/healthz-status.md, 레인 C).

- OpsStatusPort: `/healthz` 가 쓰는 **읽기 전용** 포트 — 상태 파일 스냅샷만(명령 실행 없음).
- OpsStatusWriterPort: `rra ops check`·`rra llm-check` 가 점검 결과를 적는다(열거값·시각만).
- TunnelProbePort / LocalLlmProbePort: 점검 1회. 어댑터는 subprocess(tailscale)·HTTP(GET /v1/models)
  를 쓰지만 포트로는 **정해진 값·참/거짓**만 돌려준다 — 출력 원문(IP·이름)은 어댑터 안에서 버린다.
모두 동기(점검은 launchd 가 5분마다 띄우는 짧은 CLI 다).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TunnelProbe:
    """`tailscale status --json` 의 BackendState 값과 `funnel status` 의 "(Funnel on)" 유무.
    None = 얻지 못함(명령 없음·실패·시간 초과)."""

    backend_state: str | None
    funnel_on: bool | None


@runtime_checkable
class OpsStatusPort(Protocol):
    def snapshot(self) -> Mapping[str, Any] | None:
        """상태 파일 전체 {"tunnel": {state, since, checked_at}, "llm_local": {...}} 또는 None."""
        ...


@runtime_checkable
class OpsStatusWriterPort(Protocol):
    def record(self, kind: str, state: str) -> None:
        """kind 는 domain/rules/ops_status.KINDS 의 키, state 는 그 종류의 열거값. 실패는 삼킨다."""
        ...


@runtime_checkable
class TunnelProbePort(Protocol):
    def probe(self) -> TunnelProbe: ...


@runtime_checkable
class LocalLlmProbePort(Protocol):
    def probe(self) -> bool | None:
        """로컬 모델 서버가 GET /v1/models 에 2xx 로 답했는가. None = 점검 못 함."""
        ...
