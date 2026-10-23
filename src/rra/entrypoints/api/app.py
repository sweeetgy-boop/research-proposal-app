"""REST API — 보안 G.

- 127.0.0.1:8000 기본 바인딩. 설정으로 바꿀 수 있으나 외부 공개는 HTTPS 역프록시 뒤에서만
  (deploy/README.md).
- 모든 /v1/* 는 토큰 필수 (X-RRA-Token 또는 Authorization: Bearer). /healthz 만 열려 있고
  내부 정보가 없다.
- 본문 상한·필드 길이(도메인 모델)·보안 헤더·CORS 없음·업로드 없음. 미들웨어는 adapters/security.
- 사용자는 단일 토큰 소유자(LOCAL_USER). 다중 사용자는 후속.
- 모든 호출은 RunManager·PrecheckOverlap·DocumentRepository 로만 — CLI·MCP·UI 와 같은 application.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from rra.application.ports import RunBusy, RunNotFound
from rra.application.ports.renderer import RenderRejected
from rra.application.services import (
    ConfirmRejected,
    QueueFull,
    RenderUnavailable,
    RunNotResumable,
)
from rra.domain.models import ProposalRequest, ProposerInfo
from rra.domain.models.proposer import Person
from rra.domain.models.request import validation_message
from rra.domain.models.run import is_valid_run_id
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.api.schemas import ConfirmIn, ProposerIn
from rra.entrypoints.views import alerts_payload, chunks_payload, draft_payload, run_state_payload

API_VERSION = "v1"
DEFAULT_K = 5
MAX_K = 20
MAX_ORGS = 10
HWPX_MEDIA_TYPE = "application/hwp+zip"


def _clean(text: str) -> str:
    """제어문자 제거 — JSON 소비자가 터미널·로그에 그대로 찍어도 안전하게."""
    return "".join(ch for ch in text if ch >= " " or ch in "\n\t")


def create_app(
    *,
    manager: Any,
    precheck: Any,
    repo: Any,
    user: str,
    middlewares: list[tuple[type, dict[str, Any]]],
    query_max_chars: int = 500,
    on_shutdown: Callable[[], Any] | None = None,
) -> FastAPI:
    """조립된 서비스로 앱을 만든다. 기본 조립은 composition.build_api()."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if on_shutdown is not None:
            result = on_shutdown()
            if hasattr(result, "__await__"):
                await result

    app = FastAPI(
        title="rra",
        version=API_VERSION,
        docs_url=None,  # 문서 UI 없음 (CSP default-src 'none' 과도 맞지 않는다)
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    for cls, kwargs in middlewares:  # 바깥쪽부터: 헤더 → 본문 상한 → 인증 순서가 되도록 역순 등록
        app.add_middleware(cls, **kwargs)

    @app.exception_handler(ValidationError)
    async def _validation(_req: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse({"detail": validation_message(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # 도메인 모델(ProposalRequest 등)의 검증 메시지를 CLI·UI·MCP 와 같은 문구로 돌려준다
        return JSONResponse({"detail": validation_message(exc.errors())}, status_code=422)

    def _run_id(value: str) -> str:
        if not is_valid_run_id(value):
            raise HTTPException(404, "run 을 찾을 수 없습니다.")
        return value

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(f"/{API_VERSION}/precheck")
    async def precheck_route(req: ProposalRequest) -> dict[str, Any]:
        alerts = await precheck(req)
        return {"notice": UNTRUSTED_NOTICE, **alerts_payload(alerts, clean=_clean)}

    @app.get(f"/{API_VERSION}/search")
    async def search_route(
        q: str = Query(min_length=1),
        k: int = Query(default=DEFAULT_K, ge=1, le=MAX_K),
        orgs: str | None = Query(default=None, max_length=400),
    ) -> dict[str, Any]:
        query = q.strip()
        if not query:
            raise HTTPException(422, "q 가 비어 있습니다.")
        if len(query) > query_max_chars:
            raise HTTPException(422, f"q 길이 {len(query)} > 상한 {query_max_chars}")
        org_list = [o.strip() for o in (orgs or "").split(",") if o.strip()][:MAX_ORGS] or None
        chunks = await repo.hybrid_search([query], k=k, orgs=org_list)
        return {"notice": UNTRUSTED_NOTICE, "chunks": chunks_payload(list(chunks), clean=_clean)}

    @app.post(f"/{API_VERSION}/runs", status_code=202)
    async def submit_route(req: ProposalRequest) -> dict[str, Any]:
        try:
            state = await manager.submit(user, req)
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        except RunBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        return run_state_payload(state)

    @app.get(f"/{API_VERSION}/runs/{{run_id}}")
    async def status_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.status(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return run_state_payload(state, legacy=manager.is_legacy(state))

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/resume", status_code=202)
    async def resume_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.resume(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except (RunNotResumable, RunBusy) as exc:
            raise HTTPException(409, str(exc)) from exc
        return run_state_payload(state)

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/draft")
    async def draft_route(run_id: str) -> dict[str, Any]:
        try:
            view = await manager.get_draft(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"notice": UNTRUSTED_NOTICE, **draft_payload(view, clean=_clean)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/confirm")
    async def confirm_route(run_id: str, body: ConfirmIn) -> dict[str, Any]:
        try:
            confirmation = await manager.confirm(user, _run_id(run_id), body.choices())
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except ConfirmRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": run_id, "confirmed": confirmation.choices}

    async def _render(run_id: str, proposer: ProposerInfo | None) -> Response:
        try:
            data = await manager.render(user, _run_id(run_id), proposer=proposer)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except RenderRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        except RenderUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(
            content=data,
            media_type=HWPX_MEDIA_TYPE,
            headers={"content-disposition": f'attachment; filename="proposal-{run_id}.hwpx"'},
        )

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/file")
    async def file_route(run_id: str) -> Response:
        """양식 파일 (하단 제안자 칸 빈칸). 제안자 정보는 POST 본문으로 — URL·로그에 남지 않게."""
        return await _render(run_id, None)

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/file")
    async def file_with_proposer_route(run_id: str, body: ProposerIn) -> Response:
        proposer = ProposerInfo(
            proposed_on=body.proposed_on,
            proposer=Person(**body.proposer.model_dump()),
            head=Person(**body.head.model_dump()),
        )
        return await _render(run_id, proposer)

    return app
