"""문제 정의 카드 경로 (ADR 0065, 계약 problem-card.md 3절) — create_app 이 register() 로 붙인다.
로직 없음.

- POST /v1/ideas/diagnose        제안 입력 → 카드(AI 1회 + 규칙 검증). 꺼짐·실패면 card: null
                                 (오류 응답으로 만들지 않는다 — 화면은 카드 없이 진행)
- POST /v1/ideas/diagnose/edit   사용자 수정 → 그 항목에 기대는 것만 다시 계산 + 기록

카드는 ① 화면의 상태다 — 서버는 세션에 저장하지 않는다. 요청 몸통은 모르는 칸을 거부한다.
네 칸 중 빈 칸이 있으면 422(기존 필수 슬롯 문구). 브라우저가 끊으면 작업을 취소한다(ADR 0038).
카드의 글은 AI 출력(비신뢰) — UNTRUSTED_NOTICE 와 함께 clean 을 거쳐 나간다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rra.application.usecases.edit_problem_card import CardDisabled
from rra.application.usecases.problem_card_contract import CardEdit, CardEditor, ProblemDiagnosis
from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import CARD_FIELDS, CardField, ProblemCard
from rra.domain.models.request import validation_message
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.api.cancellable import cancel_on_disconnect
from rra.entrypoints.views_card import DISABLED_DETAIL, diagnose_payload, edit_payload, off_payload

_TEXT = 2000  # 길이 상한은 ProposalRequest 가 다시 강제한다 — 여기는 몸통 크기만 막는다


class IdeaIn(BaseModel):
    """네 칸 + 가제. 필수 칸 검사는 ProposalRequest 한 곳(문구도 그곳)."""

    model_config = ConfigDict(extra="forbid")

    title_hint: str | None = Field(default=None, max_length=_TEXT)
    current_state: str = Field(default="", max_length=_TEXT)
    root_cause: str = Field(default="", max_length=_TEXT)
    limitation: str = Field(default="", max_length=_TEXT)
    goal: str = Field(default="", max_length=_TEXT)

    def request(self) -> ProposalRequest:
        try:
            return ProposalRequest(
                title_hint=self.title_hint,
                current_state=self.current_state,
                root_cause=self.root_cause,
                limitation=self.limitation,
                goal=self.goal,
            )
        except ValidationError as exc:
            raise HTTPException(422, validation_message(exc)) from exc


class DiagnoseIn(IdeaIn):
    """POST /v1/ideas/diagnose — previous: 화면이 갖고 있던 카드(사용자 항목은 그대로 둔다)."""

    previous: ProblemCard | None = None


class DiagnoseEditIn(BaseModel):
    """POST /v1/ideas/diagnose/edit — fields: 사용자가 고친 항목 이름."""

    model_config = ConfigDict(extra="forbid")

    request: IdeaIn
    before: ProblemCard
    after: ProblemCard
    fields: list[CardField] = Field(min_length=1, max_length=len(CARD_FIELDS))


def register(
    app: FastAPI,
    *,
    api_version: str,
    diagnosis: ProblemDiagnosis | None,
    editor: CardEditor | None,
    who: Callable[[Request], Principal],
    clean: Callable[[str], str],
) -> None:
    """diagnosis·editor 가 None 이면(조립이 만들지 않음) 진단은 꺼짐 응답, 수정은 409."""
    V = api_version

    @app.post(f"/{V}/ideas/diagnose")
    async def diagnose_route(request: Request, body: DiagnoseIn) -> dict[str, Any]:
        req = body.request()
        if diagnosis is None:
            return {"notice": UNTRUSTED_NOTICE, **off_payload()}
        outcome = await cancel_on_disconnect(  # 끊기면 진단만 멈춘다 (ADR 0038)
            request, diagnosis(req, previous=body.previous, principal=who(request))
        )
        return {"notice": UNTRUSTED_NOTICE, **diagnose_payload(outcome, clean=clean)}

    @app.post(f"/{V}/ideas/diagnose/edit")
    async def diagnose_edit_route(request: Request, body: DiagnoseEditIn) -> dict[str, Any]:
        req = body.request.request()
        if editor is None:
            raise HTTPException(409, DISABLED_DETAIL)
        try:
            outcome = await cancel_on_disconnect(
                request,
                editor(
                    req,
                    body.before,
                    body.after,
                    [CardEdit(field=f) for f in dict.fromkeys(body.fields)],
                    principal=who(request),
                ),
            )
        except CardDisabled as exc:
            raise HTTPException(409, DISABLED_DETAIL) from exc
        return {"notice": UNTRUSTED_NOTICE, **edit_payload(outcome, clean=clean)}
