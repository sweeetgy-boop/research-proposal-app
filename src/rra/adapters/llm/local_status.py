"""LocalLlmProbePort 구현 — 로컬 모델 서버(mlx, 127.0.0.1) 응답 점검 (계약 healthz-status.md).

GET /v1/models 한 번, 시간 초과 5초, 재시도 없음. 2xx 면 True, 연결 실패·시간 초과·4xx·5xx 면 False.
보안 H: base_url 은 루프백만(`_endpoint.guard_base_url`). 응답 본문은 읽지 않고 상태 코드만 본다.
2026-11-03 `rra llm-check` 가 멈춘 일(ADR 0062): 서버는 살아 있었지만 긴 생성 1건이 16분 넘게
서버를 붙들고 있었고, 클라이언트는 10분 읽기 제한 × 3회 재시도로 기다렸다. 이 점검은 짧게 끝난다.
"""

from __future__ import annotations

import logging

import httpx

from rra.adapters.llm import _endpoint

logger = logging.getLogger("rra.ops")

PROBE_TIMEOUT_SEC = 5.0


class LocalLlmProbe:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = PROBE_TIMEOUT_SEC,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = _endpoint.guard_base_url("mlx", base_url)
        self.timeout = max(0.5, float(timeout))
        self._transport = transport

    def __repr__(self) -> str:
        return f"LocalLlmProbe({self.base_url!r})"

    def probe(self) -> bool | None:
        url = _endpoint.models_url(self.base_url)
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                resp = client.get(url, headers=_endpoint.auth_headers(None))
        except httpx.HTTPError as exc:  # 연결 실패·시간 초과 — 종류 이름만
            logger.debug("ops.local_llm_failed err=%s", type(exc).__name__)
            return False
        return 200 <= resp.status_code < 300
