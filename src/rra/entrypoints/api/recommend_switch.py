"""② 과제안 갈래 전환 판정 — novel ↔ 차별화 (레인 B, 2026-11-09, ADR 0061).

과제안 세션(`RecommendationSessions`)은 만들 때의 갈래(`RecommendationResult.mode`)를 들고 있다.
그 뒤 제안자가 행의 [유사함]/[관련 없음] 을 바꾸면 `similar_rows.recommend_mode`(한 곳)가 고르는
갈래가 달라질 수 있다 — 이때 [더 만들기](`/recommendations/more`)·카드 적용 미리보기
(`/{id}/apply`)는 옛 갈래의 세션을 잇는 일이라 맞지 않는다. 409 "새 과제안은 …" 대신 **갈래 전환**을
알린다: problem+json `code=mode_changed`, 한국어 detail. 화면(`features/precheck/model` 의
`modeMismatch`)은 같은 규칙으로 먼저 알아채고 [과제안 다시 만들기] 와 같은 요청을 보내므로, 서버
판정은 화면이 놓친 경우의 안전망이다.

app.py 는 공용 파일이라 여기서 고치지 않는다 — 더/적용 핸들러에 넣을 줄은 PR 설명 "통합 때 메인이
반영할 조립 변경" 절에 있다(`check_mode_unchanged` 호출 + `ModeChanged` 예외 처리기
`mode_changed_response`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi.responses import JSONResponse

from rra.application.usecases.similar_rows import recommend_mode
from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.models.novel import MODE_DIFFERENTIATE, RecommendMode
from rra.domain.rules.problem_labels import problem_label

MODE_CHANGED_CODE = "mode_changed"
# 화면 문구 = problem_labels 두 표(파이썬·web/src/lib/labels.ts)의 설명과 같은 뜻
MODE_CHANGED = (
    problem_label(MODE_CHANGED_CODE) + " — [과제안 다시 만들기] 와 같은 요청을 보내십시오."
)
_PROBLEM_JSON = "application/problem+json"


class ModeChanged(Exception):
    """세션의 갈래와 지금 선택으로 계산한 갈래가 다르다 (409, code=mode_changed)."""

    status_code = 409

    def __init__(self, session_mode: RecommendMode, current_mode: RecommendMode):
        super().__init__(MODE_CHANGED)
        self.session_mode = session_mode
        self.current_mode = current_mode
        self.code = MODE_CHANGED_CODE
        self.detail = MODE_CHANGED


def session_mode(result: Any) -> RecommendMode:
    """세션 결과의 갈래 — 칸이 없거나 비면(옛 결과) differentiate."""
    mode = getattr(result, "mode", None) or MODE_DIFFERENTIATE
    return "novel" if mode == "novel" else MODE_DIFFERENTIATE


def _changed(
    result: Any, alerts: Sequence[OverlapAlert], req: ProposalRequest
) -> tuple[RecommendMode, RecommendMode, bool]:
    """(세션 갈래, 지금 갈래, 바뀌었는가). 새로움 확인에서 새 행이 걸려 서버가 novel 을 차별화로
    되돌린 세션(`novelty_reverted`, ADR 0057)은 novel 입력에 대한 서버의 답이므로 지금 갈래가 novel
    이어도 전환이 아니다 — 아니면 [더 만들기]마다 다시 받고 다시 되돌리는 되풀이가 된다."""
    before = session_mode(result)
    current = recommend_mode(alerts, req.choice_map())
    if (
        before == MODE_DIFFERENTIATE
        and current == "novel"
        and getattr(result, "novelty_reverted", False)
    ):
        return before, current, False
    return before, current, current != before


def mode_changed(result: Any, alerts: Sequence[OverlapAlert], req: ProposalRequest) -> bool:
    """세션을 만들 때의 갈래와 지금 선택(`req.choice_map()`)으로 계산한 갈래가 다른가 — 갈래 판정은
    `similar_rows.recommend_mode` 한 곳(ADR 0057)."""
    return _changed(result, alerts, req)[2]


def check_mode_unchanged(result: Any, alerts: Sequence[OverlapAlert], req: ProposalRequest) -> None:
    """갈래가 바뀌었으면 ModeChanged — 더/적용 핸들러가 novel 409 보다 먼저 부른다."""
    before, current, changed = _changed(result, alerts, req)
    if changed:
        raise ModeChanged(before, current)


def mode_changed_response(exc: ModeChanged) -> JSONResponse:
    """problem+json(409) + `code` 칸 — 화면은 code 로 동작을 가르고 문구는 detail 을 보인다."""
    return JSONResponse(
        {
            "type": "about:blank",
            "title": "상태 충돌",
            "status": exc.status_code,
            "detail": exc.detail,
            "code": exc.code,
        },
        status_code=exc.status_code,
        media_type=_PROBLEM_JSON,
    )
