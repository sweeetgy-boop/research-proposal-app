"""L2 로컬 2차 검토 경로 (2026-10-28 레인 B, ADR 0040) — create_app 이 register() 로 붙인다. 로직
없음.

- GET  /v1/runs/{id}/local-review                       문장별 판정(지지·부분·불일치)·Argon
제안·미결정 수
- POST /v1/runs/{id}/local-review/{suggestion}/apply    [반영] — 보통 편집 경로로 새 버전
- POST /v1/runs/{id}/local-review/{suggestion}/dismiss  [무시] — 결정 기록만(새 버전 없음)
- POST /v1/runs/{id}/local-review/{suggestion}/retry    제안 다시 받기(Argon) — [취소] 는 연결 끊기

제안 문장은 LLM 출력(비신뢰, UNTRUSTED_NOTICE).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from rra.application.ports import RunNotFound
from rra.application.services.run_manager import EditRejected, VersionConflict
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.api.cancellable import cancel_on_disconnect
from rra.entrypoints.views import version_payload

_SUGGESTION_ID = re.compile(r"\Alc-[0-9a-f]{6,16}\Z")


class LocalApplyIn(BaseModel):
    base_version: int | None = Field(default=None, ge=1)


def _sid(value: str) -> str:
    if not _SUGGESTION_ID.match(value):
        raise HTTPException(404, "그런 로컬 검토 제안이 없습니다.")
    return value


def register(
    app: FastAPI,
    *,
    api_version: str,
    manager: Any,
    own: Callable[[Request, str], Awaitable[tuple[str, str]]],
) -> None:
    V = api_version

    @app.get(f"/{V}/runs/{{run_id}}/local-review")
    async def local_review_route(request: Request, run_id: str) -> dict[str, Any]:
        user, rid = await own(request, run_id)
        try:
            view = await manager.local_review(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"run_id": rid, "notice": UNTRUSTED_NOTICE, "local_check": view}

    @app.post(f"/{V}/runs/{{run_id}}/local-review/{{suggestion_id}}/apply")
    async def local_apply_route(
        request: Request, run_id: str, suggestion_id: str, body: LocalApplyIn
    ) -> dict[str, Any]:
        """[반영] — 다시 쓰기는 직접 수정(원래 근거 유지), 빼기는 삭제. 새 버전."""
        user, rid = await own(request, run_id)
        try:
            version = await manager.apply_local_suggestion(
                user, rid, _sid(suggestion_id), base_version=body.base_version
            )
            state = await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except (EditRejected, VersionConflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": rid, "status": state.status, **version_payload(version, run_id=rid)}

    @app.post(f"/{V}/runs/{{run_id}}/local-review/{{suggestion_id}}/dismiss")
    async def local_dismiss_route(
        request: Request, run_id: str, suggestion_id: str
    ) -> dict[str, Any]:
        """[무시] — 결정만 기록한다. 버전은 그대로."""
        user, rid = await own(request, run_id)
        try:
            view = await manager.dismiss_local_suggestion(user, rid, _sid(suggestion_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": rid, "notice": UNTRUSTED_NOTICE, "local_check": view}

    @app.post(f"/{V}/runs/{{run_id}}/local-review/{{suggestion_id}}/retry")
    async def local_retry_route(
        request: Request, run_id: str, suggestion_id: str
    ) -> dict[str, Any]:
        """제안 다시 받기 — Argon 먼저(오류 응답일 때만 로컬). 시간 제한 없음, [취소] 는 연결
        끊기."""
        user, rid = await own(request, run_id)
        try:
            view = await cancel_on_disconnect(
                request, manager.retry_local_suggestion(user, rid, _sid(suggestion_id))
            )
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": rid, "notice": UNTRUSTED_NOTICE, "local_check": view}
