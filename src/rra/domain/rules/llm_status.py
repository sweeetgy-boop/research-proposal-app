"""원격 LLM(Argon = Gemini) 연결 상태 규칙 — 순수 함수 (ADR 0055).

2026-10-30 ~ 11-03 Gemini 키가 무효였던 나흘 동안 모든 Argon 호출이 400 으로 실패했는데, 로그에는
`err=LLMError` 만 남고 화면은 로컬 모델로 조용히 대체돼 아무도 몰랐다. 그래서 마지막 호출 결과를
거친 열거값 하나로 남기고 `/healthz`·화면 위 알림 띠·`rra llm-check` 가 같은 표를 쓴다.

- 상태: ok | key_invalid | quota | unavailable. 기록이 없으면 unknown.
- `since` 는 지금 상태가 시작된 시각(같은 상태가 이어지면 그대로), `checked_at` 은 마지막 갱신 시각.
- 실패 종류(code)는 어댑터 예외의 `code`(adapters/llm/errors). 보내지 않은 호출(not_sent)·응답 형식
  오류(invalid)는 연결 상태와 무관해 상태를 바꾸지 않는다(None).
- 공개 표시(`public_view`)는 열거값과 시각만 — 공급자 주소·모델 이름·오류 문구·건수는 넣지 않는다
  (/healthz 는 인증 없이 인터넷에서 보인다).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

OK = "ok"
KEY_INVALID = "key_invalid"
QUOTA = "quota"
UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"
STATES = (OK, KEY_INVALID, QUOTA, UNAVAILABLE)

# 어댑터 실패 종류 → 상태. 표에 없는 종류는 UNAVAILABLE (재시도 뒤에도 실패한 그 밖의 오류).
_CODE_STATES: dict[str, str | None] = {
    "auth": KEY_INVALID,
    "quota": QUOTA,
    "rate_limit": QUOTA,
    "timeout": UNAVAILABLE,
    "connection": UNAVAILABLE,
    "server": UNAVAILABLE,
    "http": UNAVAILABLE,
    "format": UNAVAILABLE,
    "error": UNAVAILABLE,
    "invalid": None,  # 응답은 왔다 — 연결 상태는 그대로
    "not_sent": None,  # 보내지 않았다
}

# `rra llm-check` 표시 — 실패 종류별 한 줄 (본문 대신)
FAILURE_LABELS: dict[str, str] = {
    "auth": "인증 실패(API 키 무효)",
    "quota": "사용 한도 초과(할당량 소진)",
    "rate_limit": "호출 한도 초과(잠시 뒤 다시)",
    "timeout": "응답 없음(시간 초과)",
    "connection": "응답 없음(연결 실패)",
    "server": "응답 없음(서버 오류)",
}


# 그림 생성(Nano Banana, adapters/llm/image_gen) 상태 — 텍스트와 같은 키, 다른 대체
# (ADR 0055 덧붙임). 그림 결과는 늘 IMAGE_PROVIDER 로 따로 적는다(/healthz 에 내지 않는다).
# 텍스트 상태(TEXT_PROVIDER)에는 키 무효만 올리고, 그림 성공은 텍스트 상태가 key_invalid 일 때만
# ok 로 되돌린다. 그림의 할당량·응답 없음은 텍스트 상태를 바꾸지 않는다 — 그림 대체는 기본
# 그림이지 로컬 모델이 아니다(띠 문구 "로컬 모델로 대체 중" 과 맞지 않는다).
TEXT_PROVIDER = "gemini"
IMAGE_PROVIDER = "gemini_image"


def text_status_from_image(image_status: str | None, current_text: str | None) -> str | None:
    """그림 호출 결과 → 텍스트(gemini) 상태에 적을 값. 바꾸지 않으면 None (순수 함수).

    - key_invalid → key_invalid (같은 키 — 띠가 떠야 한다)
    - ok → 지금 텍스트 상태가 key_invalid 일 때만 ok (같은 키가 다시 된다)
    - quota·unavailable·None → None
    """
    if image_status == KEY_INVALID:
        return KEY_INVALID
    if image_status == OK and current_text == KEY_INVALID:
        return OK
    return None


def status_for_code(code: str | None) -> str | None:
    """실패 종류 → 상태. 상태를 바꾸지 않을 실패면 None."""
    if not code:
        return UNAVAILABLE
    return _CODE_STATES.get(code, UNAVAILABLE)


def failure_label(code: str | None) -> str | None:
    """분류된 실패면 한국어 한 줄, 아니면 None(호출 쪽이 기존 메시지를 쓴다)."""
    return FAILURE_LABELS.get(code or "")


def advance(previous: Mapping[str, Any] | None, status: str, now: str) -> dict[str, str]:
    """새 결과를 반영한 기록 {status, since, checked_at}. 같은 상태가 이어지면 since 는 그대로."""
    if status not in STATES:
        raise ValueError(f"알 수 없는 LLM 상태: {status!r}")
    prev = dict(previous or {})
    same = prev.get("status") == status and isinstance(prev.get("since"), str)
    return {"status": status, "since": prev["since"] if same else now, "checked_at": now}


def _iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def public_view(record: Mapping[str, Any] | None) -> dict[str, str | None]:
    """/healthz `llm` — {"gemini": 상태|unknown, "since": ISO|None}. 모르는 값은 unknown."""
    status = (record or {}).get("status")
    if status not in STATES:
        return {"gemini": UNKNOWN, "since": None}
    return {"gemini": str(status), "since": _iso((record or {}).get("since"))}
