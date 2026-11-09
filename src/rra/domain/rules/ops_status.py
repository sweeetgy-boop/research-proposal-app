"""운영 상태(터널·로컬 모델) 열거값·판정 규칙 — 순수 함수 (계약 docs/contracts/healthz-status.md).

`/healthz` 는 인증 없이 인터넷에서 보인다. 그래서 상태 파일과 응답에는 **열거값과 시각만** 둔다 —
명령 출력 원문(IP·호스트명·DNS 이름·계정)·오류 문구·건수는 어디에도 남기지 않는다.

- tunnel: ok | down | unknown. ok = Tailscale BackendState 가 "Running" 이고 funnel status 에
  "(Funnel on)" 표식이 있을 때. 하나라도 아니면 down. 표식을 못 얻었으면(명령 없음·실패) unknown.
- llm_local: ok | unavailable | unknown. 로컬 모델 서버(mlx, 127.0.0.1) GET /v1/models 가 2xx 면 ok,
  연결 실패·시간 초과·4xx·5xx 면 unavailable. 점검 기록이 없으면 unknown.
- 오래된 기록: 마지막 점검(checked_at)이 `MAX_AGE_SEC`(15분, 5분 주기의 3배)보다 오래되면 unknown —
  점검 자체가 멈춘 것(launchd 미기동)을 "ok" 로 보이지 않게.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

OK = "ok"
DOWN = "down"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"

TUNNEL_STATES = (OK, DOWN)
LOCAL_STATES = (OK, UNAVAILABLE)

TUNNEL = "tunnel"
LLM_LOCAL = "llm_local"
KINDS = {TUNNEL: TUNNEL_STATES, LLM_LOCAL: LOCAL_STATES}

RUNNING = "Running"  # tailscale status --json 의 BackendState — 이 값만 비교한다
FUNNEL_ON_MARK = "(Funnel on)"  # tailscale funnel status 본문의 표식 — 이것만 찾는다

MAX_AGE_SEC = 15 * 60  # 점검 주기 5분 × 3


def tunnel_state(backend_state: str | None, funnel_on: bool | None) -> str:
    """두 값 → ok|down|unknown. 하나라도 없으면(None) unknown."""
    if backend_state is None or funnel_on is None:
        return UNKNOWN
    return OK if backend_state == RUNNING and funnel_on else DOWN


def local_state(responded: bool | None) -> str:
    """로컬 모델 응답 여부 → ok|unavailable|unknown(점검 못 함)."""
    if responded is None:
        return UNKNOWN
    return OK if responded else UNAVAILABLE


def advance(previous: Mapping[str, Any] | None, state: str, now: str) -> dict[str, str]:
    """새 점검 결과를 반영한 기록 {state, since, checked_at}. 같은 상태가 이어지면 since 그대로."""
    if state not in (OK, DOWN, UNAVAILABLE):
        raise ValueError(f"알 수 없는 운영 상태: {state!r}")
    prev = dict(previous or {})
    same = prev.get("state") == state and isinstance(prev.get("since"), str)
    return {"state": state, "since": prev["since"] if same else now, "checked_at": now}


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_stale(
    record: Mapping[str, Any] | None, now: datetime, max_age_sec: int = MAX_AGE_SEC
) -> bool:
    """마지막 점검이 max_age_sec 보다 오래됐거나 시각을 읽을 수 없으면 True."""
    checked = _parse((record or {}).get("checked_at"))
    if checked is None:
        return True
    if (checked.tzinfo is None) != (now.tzinfo is None):
        return True  # 시간대 유무가 다르면 비교하지 않는다 — 모르는 것으로
    age = (now - checked).total_seconds()
    return age < 0 or age > max_age_sec


def view_state(kind: str, record: Mapping[str, Any] | None, now: datetime) -> str:
    """기록 한 칸 → 공개 열거값. 없음·모르는 값·오래됨 → unknown."""
    allowed = KINDS[kind]
    state = (record or {}).get("state")
    if state not in allowed or is_stale(record, now):
        return UNKNOWN
    return str(state)


def public_view(data: Mapping[str, Any] | None, now: datetime) -> dict[str, str]:
    """상태 파일 전체 → {"tunnel": …, "llm_local": …}. 열거값만."""
    table = data if isinstance(data, Mapping) else {}
    return {
        TUNNEL: view_state(TUNNEL, _record(table.get(TUNNEL)), now),
        LLM_LOCAL: view_state(LLM_LOCAL, _record(table.get(LLM_LOCAL)), now),
    }


def _record(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


# `rra ops check`·`rra llm-check` 출력 한 줄 — 열거값만
def summary_line(view: Mapping[str, str]) -> str:
    return f"tunnel={view.get(TUNNEL, UNKNOWN)} llm_local={view.get(LLM_LOCAL, UNKNOWN)}"
