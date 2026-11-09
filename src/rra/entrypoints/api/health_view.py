"""`/healthz` 운영 상태 칸 `tunnel`·`llm.local` (계약 docs/contracts/healthz-status.md, 레인 C).

app.py 의 healthz 핸들러가 `with_ops(out, ops_status)` 한 줄로 쓴다(통합 때 메인이 연결).
상태 파일만 읽는 포트(OpsStatusPort.snapshot)에서 열거값을 만들고, 15분 넘은 기록은 unknown.
명령 실행·경로·IP·호스트명 없음 — 인증 없이 인터넷에서 보이는 경로다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from rra.application.ports.ops_status import OpsStatusPort
from rra.domain.rules import ops_status

_UNKNOWN_LLM: dict[str, Any] = {"gemini": ops_status.UNKNOWN, "since": None}


def _now() -> datetime:
    return datetime.now(UTC).astimezone()


def ops_fields(status: OpsStatusPort, *, now: Callable[[], datetime] = _now) -> dict[str, str]:
    """{"tunnel": ok|down|unknown, "local": ok|unavailable|unknown} — 열거값만."""
    view = ops_status.public_view(status.snapshot(), now())
    return {"tunnel": view[ops_status.TUNNEL], "local": view[ops_status.LLM_LOCAL]}


def with_ops(
    out: dict[str, Any], status: OpsStatusPort | None, *, now: Callable[[], datetime] = _now
) -> dict[str, Any]:
    """healthz 응답 딕셔너리에 `tunnel` 과 `llm.local` 을 더한다. status 가 None 이면 그대로.
    `llm` 이 없으면(Argon 상태 함수가 없는 조립) gemini unknown 으로 만들어 local 만 채운다."""
    if status is None:
        return out
    fields = ops_fields(status, now=now)
    out["tunnel"] = fields["tunnel"]
    llm = out.get("llm")
    if not isinstance(llm, dict):
        llm = dict(_UNKNOWN_LLM)
        out["llm"] = llm
    llm["local"] = fields["local"]
    return out
