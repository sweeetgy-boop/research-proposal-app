"""차별화 과제안 측정 줄 (2026-11-04, ADR 0055 덧붙임) — 추천 호출 한 번 = 한 줄.

건수·시간·열거값만 담는다. 가제·본문·doc_id·사용자/소유자 id·아이디어 해시는 넣지 않는다(보안 D).
`ts` 는 기록하는 어댑터가 붙인다(이 모듈은 시계를 모른다). 문자열 칸은 `ENUM_FIELDS` 셋뿐이고,
짧은 영문 식별자가 아니면 None 으로 바꾼다 — 열거값 밖의 글이 파일에 들어가지 않는다.
"""

from __future__ import annotations

from rra.domain.models import RecommendationResult

MODE_INITIAL = "initial"  # 처음 받기 (자동 1회·[다시 받기]·CLI·MCP·Streamlit)
MODE_MORE = "more"  # [차별화 과제안 더 만들기] (/recommendations/more, 이미 보인 카드 `shown`)
MODES = (MODE_INITIAL, MODE_MORE)

# 줄의 칸 순서 (ts 포함). 값 형식: bool 3칸, int 5칸, float 1칸, 열거 문자열(또는 null) 3칸
ROW_FIELDS = (
    "provider",
    "fallback_local",
    "calls",
    "cards",
    "discarded",
    "retry_used",
    "regenerated",
    "skipped_reason",
    "references",
    "similar",
    "mode",
    "seconds",
)
FIELDS = ("ts", *ROW_FIELDS)
# 있을 때만 쓰는 칸 — 시험 계정 세션(배포 확인용 임시 사번)의 줄만 `test: true`, 그 밖에는 키 없음
# (ADR 0056 2026-11-04 덧붙임). 줄 끝에 붙는다
TEST_FIELD = "test"
OPTIONAL_FIELDS = (TEST_FIELD,)
ENUM_FIELDS = frozenset({"provider", "skipped_reason", "mode"})


def enum_value(value: object) -> str | None:
    """열거 칸 — 64자 이하 영문·숫자·밑줄만, 그 밖은 None."""
    if not isinstance(value, str) or not value or len(value) > 64 or not value.isascii():
        return None
    return value if value.replace("_", "").isalnum() else None


def metrics_row(
    result: RecommendationResult,
    *,
    mode: str,
    similar: int,
    seconds: float,
    test: bool = False,
) -> dict[str, object]:
    """추천 결과 → 측정 줄(ts 제외). similar = 비교에 쓴 [유사함] 행 수, seconds = 호출 전체
    벽시계 시간(다시 받기·카드 겹침 재판정 포함). test 면(시험 계정 세션) `test: true` 를 붙인다."""
    row: dict[str, object] = {
        "provider": enum_value(result.provider),
        "fallback_local": bool(result.fallback_local),
        "calls": int(result.calls),
        "cards": len(result.recommendations),
        "discarded": len(result.discarded),
        "retry_used": bool(result.retry_used),
        "regenerated": bool(result.regenerated),
        "skipped_reason": enum_value(result.skipped_reason),
        "references": len(result.reference_doc_ids),
        "similar": max(0, int(similar)),
        "mode": mode if mode in MODES else MODE_INITIAL,
        "seconds": round(max(0.0, float(seconds)), 2),
    }
    if test:
        row[TEST_FIELD] = True
    return row
