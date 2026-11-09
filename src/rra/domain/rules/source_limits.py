"""자료원 호출 제한(HTTP 429 등) 판정 — 순수 함수 (레인 A, 2026-11-09).

OpenAlex 는 2026-11 부터 익명(API 키 없음) 검색 요청을 혼잡할 때 429 + `Retry-After: 30` 으로 막고,
키 없는 요청은 같은 공인 IP 가 하루 예산을 나눠 쓴다(실호출 확인 2026-11-09). 실시간 검색은 자료원
하나의 제한 시간(10~15초)이 Retry-After 보다 짧으므로 기다리지 않고 그 자료원만 건너뛴다 —
어댑터는 `SourceRateLimited` 를 올리고, 유스케이스는 결과를 `error` + 안내 문구로 남긴다(coverage
열거값은 계약 그대로 `error`).

여기에는 네트워크·설정 읽기가 없다. 안내 문구는 CLI·로그·웹 자료원 상태가 같은 것을 쓴다.
"""

from __future__ import annotations

NOTICE_RATE_LIMITED = "{source} 가 요청 빈도를 제한함 — 잠시 뒤 다시 시도"
NOTICE_ANONYMOUS_LIMITED = "{source} 가 익명(API 키 없음) 검색을 제한함 — API 키({env}) 등록 필요"
OPENALEX_KEY_ENV = "RRA_OPENALEX_API_KEY"


class SourceRateLimited(RuntimeError):
    """자료원 API 가 호출 빈도·예산을 이유로 요청을 거부했다(429 Retry-After 가 기다릴 수 있는
    시간보다 길거나 재시도를 다 씀). 유스케이스는 그 자료원만 건너뛴다. 메시지는 사람에게 보일 짧은
    안내만(키·URL 없음)."""


def rate_limit_notice(source: str, *, anonymous: bool = False, key_env: str = "") -> str:
    """사람에게 보일 안내. anonymous(키 없이 호출했다)면 키 등록을 권한다."""
    if anonymous:
        return NOTICE_ANONYMOUS_LIMITED.format(source=source, env=key_env or "API 키")
    return NOTICE_RATE_LIMITED.format(source=source)
