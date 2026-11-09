"""TunnelProbePort 구현 — Tailscale Funnel 공개 경로 점검 (계약 healthz-status.md, ADR 0047).

`tailscale status --json` 과 `tailscale funnel status` 를 subprocess 로 1회씩 부른다(고정 인자,
shell 없음, 시간 초과 10초). 출력 원문에는 IP·호스트명·DNS 이름·계정이 들어 있으므로 **여기서
버린다** — 포트로는 BackendState 값과 "(Funnel on)" 유무만 나간다(`normalize_*` 순수 함수).
원문은 로그에도 쓰지 않는다. 명령 파일이 없으면(개발 맥) None·None → unknown.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from rra.application.ports.ops_status import TunnelProbe
from rra.domain.rules import ops_status

logger = logging.getLogger("rra.ops")

DEFAULT_TAILSCALE_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
PROBE_TIMEOUT_SEC = 10.0
MAX_OUTPUT_BYTES = 1_000_000  # 이보다 큰 출력은 해석하지 않는다(상태 JSON 은 수십 KB)
_BACKEND_STATES = frozenset(
    {"Running", "Stopped", "NeedsLogin", "NeedsMachineAuth", "Starting", "NoState"}
)


def normalize_status_json(text: str) -> str | None:
    """`tailscale status --json` 본문 → BackendState(정해진 값만). 그 밖은 None."""
    if not text or len(text) > MAX_OUTPUT_BYTES:
        return None
    try:
        data: Any = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    state = data.get("BackendState")
    return state if isinstance(state, str) and state in _BACKEND_STATES else None


def normalize_funnel_text(text: str) -> bool:
    """`tailscale funnel status` 본문에 "(Funnel on)" 표식이 있는가. 본문은 돌려주지 않는다."""
    if not text or len(text) > MAX_OUTPUT_BYTES:
        return False
    return ops_status.FUNNEL_ON_MARK in text


class TailscaleProbe:
    def __init__(
        self, bin_path: str | Path = DEFAULT_TAILSCALE_BIN, *, timeout: float = PROBE_TIMEOUT_SEC
    ):
        self.bin_path = Path(bin_path)
        self.timeout = max(1.0, float(timeout))

    def __repr__(self) -> str:
        return "TailscaleProbe()"

    @property
    def available(self) -> bool:
        return self.bin_path.is_file()

    def _run(self, *args: str) -> str | None:
        """명령 1회. 실패·시간 초과·0 아닌 종료는 None. 출력 원문은 돌려줄 뿐 기록하지 않는다."""
        try:
            proc = subprocess.run(  # noqa: S603 — 절대 경로 실행 파일, 고정 인자, shell 없음
                [str(self.bin_path), *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("ops.tailscale_failed cmd=%s err=%s", args[0], type(exc).__name__)
            return None
        if proc.returncode != 0:
            logger.debug("ops.tailscale_exit cmd=%s code=%d", args[0], proc.returncode)
            return None
        return proc.stdout

    def probe(self) -> TunnelProbe:
        if not self.available:
            return TunnelProbe(backend_state=None, funnel_on=None)
        status_out = self._run("status", "--json")
        backend = normalize_status_json(status_out) if status_out is not None else None
        if backend is None:
            return TunnelProbe(backend_state=None, funnel_on=None)
        funnel_out = self._run("funnel", "status")
        # funnel status 가 실패하면(데몬 꺼짐 등) Funnel 은 켜져 있지 않다고 본다 → down
        funnel_on = normalize_funnel_text(funnel_out) if funnel_out is not None else False
        return TunnelProbe(backend_state=backend, funnel_on=funnel_on)
