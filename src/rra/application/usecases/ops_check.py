"""`rra ops check` — 터널·로컬 모델 점검 1회 → 상태 파일 갱신 (계약 healthz-status.md §3).

launchd(com.rra.opscheck, 5분)가 띄운다. 포트에서 받는 값은 정해진 값·참/거짓뿐이고, 판정은
domain/rules/ops_status 의 순수 함수다. 결과는 열거값 한 줄(`summary_line`)로만 보고한다.
터널 점검기(tailscale 명령)가 없는 환경(개발 맥)은 tunnel 을 적지 않는다 → `/healthz` 는 unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

from rra.application.ports.ops_status import (
    LocalLlmProbePort,
    OpsStatusWriterPort,
    TunnelProbePort,
)
from rra.domain.rules import ops_status


@dataclass(frozen=True)
class OpsCheckResult:
    tunnel: str  # ok|down|unknown
    llm_local: str  # ok|unavailable|unknown

    def line(self) -> str:
        return ops_status.summary_line(
            {ops_status.TUNNEL: self.tunnel, ops_status.LLM_LOCAL: self.llm_local}
        )


class OpsCheck:
    def __init__(
        self,
        *,
        status: OpsStatusWriterPort,
        local: LocalLlmProbePort,
        tunnel: TunnelProbePort | None = None,
    ):
        self.status = status
        self.local = local
        self.tunnel = tunnel

    def __call__(self) -> OpsCheckResult:
        tunnel_state = ops_status.UNKNOWN
        if self.tunnel is not None:
            probe = self.tunnel.probe()
            tunnel_state = ops_status.tunnel_state(probe.backend_state, probe.funnel_on)
        local_state = ops_status.local_state(self.local.probe())
        # unknown(점검 못 함)은 적지 않는다 — 이전 기록이 남았다가 15분이 지나면 저절로 unknown
        if tunnel_state != ops_status.UNKNOWN:
            self.status.record(ops_status.TUNNEL, tunnel_state)
        if local_state != ops_status.UNKNOWN:
            self.status.record(ops_status.LLM_LOCAL, local_state)
        return OpsCheckResult(tunnel=tunnel_state, llm_local=local_state)
