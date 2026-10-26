"""REST API — 보안 G. 프론트엔드(web/, React)가 쓰는 유일한 서버 API.

- 127.0.0.1:8000 기본 바인딩. 설정으로 바꿀 수 있으나 외부 공개는 HTTPS 역프록시 뒤에서만
  (deploy/README.md).
- 인증: 헤더 토큰(X-RRA-Token / Bearer) 또는 세션 쿠키(POST /v1/session). 쿠키 인증의 상태 변경
  요청은 X-RRA-CSRF 필수 (adapters/security). /healthz 와 정적 파일만 열려 있다.
- 오류는 전부 application/problem+json 에 한국어 detail. 본문 상한·보안 헤더·CORS 없음·업로드 없음.
- 정적 서빙: settings.static_dir(web/dist) 가 있으면 "/" 에서 SPA(index.html fallback). 같은 출처라
  CORS 가 필요 없고 CSP 는 인라인 스크립트 없이 동작하는 값이다.
- SSE(GET /v1/runs/{id}/events): 상태 조회와 같은 서비스(RunManager.status)를 주기적으로 읽어
  변화만 보낸다. 끊겨도 GET /v1/runs/{id} 로 복구할 수 있다.
- 모든 호출은 RunManager·PrecheckOverlap·DocumentRepository 로만 — CLI·MCP·UI 와 같은 application.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError

from rra.application.ports import RunBusy, RunNotFound
from rra.application.ports.renderer import RenderRejected
from rra.application.services import (
    ConfirmRejected,
    QueueFull,
    RenderUnavailable,
    RunNotResumable,
)
from rra.application.services.run_manager import (
    EditRejected,
    FinalizeRejected,
    WorkingRejected,
)
from rra.domain.models import ProposalRequest, ProposerInfo
from rra.domain.models.proposer import Person
from rra.domain.models.request import validation_message
from rra.domain.models.review import EditRequest
from rra.domain.models.run import ACTIVE, is_valid_run_id
from rra.domain.rules.overlap import ALL_SOURCES, SOURCE_LABELS
from rra.domain.rules.recommendation import apply_recommendation
from rra.domain.rules.review_flow import InvalidTransition
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.api.schemas import (
    ConfirmIn,
    FinalizeIn,
    RecommendationApplyIn,
    RevertIn,
    RunIn,
    SearchIn,
    SessionIn,
    WorkingIn,
)
from rra.entrypoints.views import (
    alerts_payload,
    chunks_payload,
    diff_payload,
    differentiation_payload,
    draft_payload,
    recommendation_preview_payload,
    recommendations_payload,
    render_check_payload,
    review_payload,
    run_state_payload,
    version_payload,
    versions_payload,
)

API_VERSION = "v1"
DEFAULT_K = 5
MAX_K = 20
MAX_ORGS = 10
HWPX_MEDIA_TYPE = "application/hwp+zip"
PROBLEM_JSON = "application/problem+json"
SSE_MAX_SEC = 30 * 60
_TITLES = {
    400: "잘못된 요청",
    401: "인증 필요",
    403: "권한 없음",
    404: "없음",
    409: "상태 충돌",
    413: "본문 너무 큼",
    422: "입력 오류",
    429: "요청 과다",
    503: "사용 불가",
}


def _clean(text: str) -> str:
    """제어문자 제거 — JSON 소비자가 터미널·로그에 그대로 찍어도 안전하게."""
    return "".join(ch for ch in text if ch >= " " or ch in "\n\t")


def problem_response(
    status: int, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {
            "type": "about:blank",
            "title": _TITLES.get(status, "오류"),
            "status": status,
            "detail": detail,
        },
        status_code=status,
        headers=headers,
        media_type=PROBLEM_JSON,
    )


class SessionAuth:
    """POST/DELETE /v1/session 이 쓰는 토큰 검사·세션 저장소. 조립이 넘긴다 (adapters/security)."""

    def __init__(self, token: str, sessions: Any):
        self.token = token
        self.sessions = sessions

    def token_ok(self, presented: str) -> bool:
        import secrets

        return bool(self.token) and secrets.compare_digest(presented.strip(), self.token)


def _named_events(prev: Any, current: Any) -> list[tuple[str, dict[str, Any]]]:
    """SSE 이름 있는 이벤트 — 화면이 팝업·단계 표시를 여는 신호 (state 이벤트와 함께 보낸다).

    pipeline_step(단계 상태 변화), draft_written(v1), draft_ready(③ 끝 — 편집 팝업), version_saved,
    final_review_ready(⑤ 끝 — 최종 검토 팝업).
    """
    out: list[tuple[str, dict[str, Any]]] = []
    done, total = current.progress
    before = {s.name: s.status for s in prev.steps} if prev is not None else {}
    for step in current.steps:
        if before.get(step.name) != step.status and step.status != "pending":
            out.append(
                (
                    "pipeline_step",
                    {
                        "run_id": current.run_id,
                        "step": step.name,
                        "status": step.status,
                        "progress": [done, total],
                    },
                )
            )
    prev_version = prev.draft_version if prev is not None else 0
    if prev_version < 1 <= current.draft_version:
        out.append(("draft_written", {"run_id": current.run_id, "version": 1}))
    if prev is not None and prev.status != current.status:
        if current.status == "drafted":
            out.append(
                ("draft_ready", {"run_id": current.run_id, "version": current.draft_version})
            )
        if current.status == "final_reviewed":
            out.append(
                (
                    "final_review_ready",
                    {"run_id": current.run_id, "final_reviews": current.final_reviews},
                )
            )
    if prev is not None and current.draft_version > max(prev.draft_version, 1):
        generating = prev.status in ("running", "draft_reviewing") and current.draft_version <= 2
        if not generating:
            out.append(
                ("version_saved", {"run_id": current.run_id, "version": current.draft_version})
            )
    return out


class RecommendationSessions:
    """precheck 세션 단위의 추천 결과 보관 — id(무작위) → (입력, 결과). 메모리에만, 최근 MAX 건.

    초안 생성 때 POST /v1/runs 의 recommendation_id 로 run 에 복사한다 (recommendations.json).
    """

    MAX = 200

    def __init__(self) -> None:
        self._items: dict[str, tuple[ProposalRequest, Any]] = {}

    def put(self, req: ProposalRequest, result: Any) -> str:
        rec_id = secrets.token_hex(12)
        self._items[rec_id] = (req, result)
        while len(self._items) > self.MAX:
            self._items.pop(next(iter(self._items)))
        return rec_id

    def get(self, rec_id: str) -> tuple[ProposalRequest, Any] | None:
        return self._items.get(rec_id)


def create_app(
    *,
    manager: Any,
    precheck: Any,
    repo: Any,
    user: str,
    middlewares: list[tuple[type, dict[str, Any]]],
    query_max_chars: int = 500,
    differentiate: Any | None = None,
    recommend: Any | None = None,
    recommend_auto: bool = True,
    clarify: Any | None = None,
    on_shutdown: Callable[[], Any] | None = None,
    session_auth: SessionAuth | None = None,
    static_dir: Path | None = None,
    sse_poll_sec: float = 1.0,
    fake_mode: bool = False,
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
        openapi_url=None,  # 스키마는 `rra api schema` 로 파일로 내보낸다
        lifespan=lifespan,
    )
    app.state.fake_mode = fake_mode
    for cls, kwargs in middlewares:  # 바깥쪽부터: 헤더 → 본문 상한 → 인증 순서가 되도록 역순 등록
        app.add_middleware(cls, **kwargs)

    # ── 오류 = problem+json ─────────────────────────────
    @app.exception_handler(HTTPException)
    async def _http(_req: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "요청을 처리할 수 없습니다."
        return problem_response(exc.status_code, detail, headers=dict(exc.headers or {}))

    @app.exception_handler(ValidationError)
    async def _validation(_req: Request, exc: ValidationError) -> JSONResponse:
        return problem_response(422, validation_message(exc))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # 도메인 모델(ProposalRequest 등)의 검증 메시지를 CLI·UI·MCP 와 같은 문구로 돌려준다
        return problem_response(422, validation_message(exc.errors()))

    def _run_id(value: str) -> str:
        if not is_valid_run_id(value):
            raise HTTPException(404, "run 을 찾을 수 없습니다.")
        return value

    def _titles() -> dict[str, str]:
        return getattr(getattr(manager.generate, "rules", None), "titles", None) or {}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # ── 세션 ────────────────────────────────────────────
    @app.post(f"/{API_VERSION}/session")
    async def session_login(body: SessionIn, request: Request) -> JSONResponse:
        """토큰 → httpOnly·SameSite=Strict 세션 쿠키 + CSRF 토큰. 토큰은 본문으로만."""
        if session_auth is None or not session_auth.token_ok(body.token):
            raise HTTPException(
                401, "인증 토큰이 맞지 않습니다.", headers={"www-authenticate": "Bearer"}
            )
        session = session_auth.sessions.create()
        response = JSONResponse({"csrf": session.csrf, "expires_in": session_auth.sessions.ttl})
        response.set_cookie(
            "rra_session",
            session.id,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
            max_age=session_auth.sessions.ttl,
        )
        return response

    @app.delete(f"/{API_VERSION}/session", status_code=204)
    async def session_logout(request: Request) -> Response:
        if session_auth is not None:
            session_auth.sessions.drop(request.cookies.get("rra_session"))
        response = Response(status_code=204)
        response.delete_cookie("rra_session", path="/")
        return response

    # ── 자료원·검색·사전 점검 ───────────────────────────
    @app.get(f"/{API_VERSION}/sources/status")
    async def sources_status() -> dict[str, Any]:
        status = await repo.source_status()
        return {
            "sources": [
                {
                    "source": s,
                    "label": SOURCE_LABELS.get(s, s),
                    "count": int(status.get(s, {}).get("count", 0)),
                    "last_ingested": status.get(s, {}).get("last_ingested"),
                }
                for s in ALL_SOURCES
            ]
        }

    recommendation_sessions = RecommendationSessions()

    async def _recommend(req: ProposalRequest, alerts: list[Any]) -> dict[str, Any]:
        result = await recommend(req, alerts)
        rec_id = recommendation_sessions.put(req, result)
        return {"id": rec_id, **recommendations_payload(result, clean=_clean)}

    @app.post(f"/{API_VERSION}/precheck")
    async def precheck_route(req: ProposalRequest) -> dict[str, Any]:
        """유사과제 알림. 차단 알림 + 차별화 LLM 이 있으면 차별화 제안(기능 2)을 자동으로 붙이고,
        과제 추천 LLM 이 있고 recommend.auto 면 차별화 과제 추천을 자동 1회 붙인다."""
        alerts = await precheck(req)
        out = {"notice": UNTRUSTED_NOTICE, **alerts_payload(alerts, clean=_clean)}
        if out["blocking"] and differentiate is not None:
            proposal = await differentiate(req, alerts)
            out["differentiation"] = differentiation_payload(proposal, clean=_clean)
        if recommend is not None and recommend_auto:
            out["recommendations"] = await _recommend(req, alerts)
        return out

    @app.post(f"/{API_VERSION}/precheck/clarify")
    async def clarify_route(req: ProposalRequest) -> dict[str, Any]:
        """③ 시작 전 입력 보강 질문(Q1). pipeline.clarify 가 꺼져 있으면 질문 0개."""
        questions = []
        if clarify is not None:
            questions = await clarify(req)
        return {"questions": questions, "skip_allowed": True}

    @app.post(f"/{API_VERSION}/precheck/recommendations")
    async def recommend_route(req: ProposalRequest) -> dict[str, Any]:
        """차별화 과제 추천(ADR 0012) — 다시 받기. 결과는 세션 id 로 보관되어 POST /v1/runs 의
        recommendation_id 로 run 에 복사된다 (외부 LLM 출력, 비신뢰)."""
        if recommend is None:
            raise HTTPException(503, "과제 추천을 쓸 수 없습니다 (LLM 없음).")
        alerts = await precheck(req)
        return {
            "notice": UNTRUSTED_NOTICE,
            **alerts_payload(alerts, clean=_clean),
            "recommendations": await _recommend(req, alerts),
        }

    @app.post(f"/{API_VERSION}/precheck/recommendations/{{rec_id}}/apply")
    async def recommend_apply_route(rec_id: str, body: RecommendationApplyIn) -> dict[str, Any]:
        """고른 추천을 제안자 입력에 채운 '수정 전 미리보기'. 저장하지 않는다 — 사용자가 고쳐 확정한
        입력을 POST /v1/runs 로 보낸다."""
        session = recommendation_sessions.get(rec_id)
        if session is None:
            raise HTTPException(404, "추천 세션을 찾을 수 없습니다 (만료 또는 모르는 id).")
        req, result = session
        if body.index >= len(result.recommendations):
            raise HTTPException(422, "그 번호의 추천이 없습니다.")
        after, preview = apply_recommendation(req, result.recommendations[body.index], body.index)
        return {
            "notice": UNTRUSTED_NOTICE,
            **recommendation_preview_payload(req, after, preview, clean=_clean),
        }

    @app.post(f"/{API_VERSION}/precheck/differentiate")
    async def differentiate_route(req: ProposalRequest) -> dict[str, Any]:
        """기능 2 — precheck 뒤 차단·근접 유사과제별 활용·차별화 방향 (외부 LLM 출력, 비신뢰)."""
        if differentiate is None:
            raise HTTPException(503, "차별화 제안을 쓸 수 없습니다 (LLM 없음).")
        alerts = await precheck(req)
        proposal = await differentiate(req, alerts)
        return {
            "notice": UNTRUSTED_NOTICE,
            **alerts_payload(alerts, clean=_clean),
            "differentiation": differentiation_payload(proposal, clean=_clean),
        }

    async def _search(query: str, k: int, orgs: list[str] | None) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise HTTPException(422, "검색어가 비어 있습니다.")
        if len(query) > query_max_chars:
            raise HTTPException(422, f"검색어 길이 {len(query)} > 상한 {query_max_chars}")
        org_list = [o.strip() for o in (orgs or []) if o and o.strip()][:MAX_ORGS] or None
        chunks = await repo.hybrid_search([query], k=k, orgs=org_list)
        return {"notice": UNTRUSTED_NOTICE, "chunks": chunks_payload(list(chunks), clean=_clean)}

    @app.post(f"/{API_VERSION}/search")
    async def search_post(body: SearchIn) -> dict[str, Any]:
        return await _search(body.query, body.k, body.orgs)

    @app.get(f"/{API_VERSION}/search")
    async def search_get(
        q: str = Query(min_length=1),
        k: int = Query(default=DEFAULT_K, ge=1, le=MAX_K),
        orgs: str | None = Query(default=None, max_length=400),
    ) -> dict[str, Any]:
        return await _search(q, k, (orgs or "").split(",") if orgs else None)

    # ── run ─────────────────────────────────────────────
    @app.post(f"/{API_VERSION}/runs", status_code=202)
    async def submit_route(body: RunIn) -> dict[str, Any]:
        req = body.request()
        recommendations = None
        if body.recommendation_id is not None:
            session = recommendation_sessions.get(body.recommendation_id)
            if session is None:
                raise HTTPException(404, "추천 세션을 찾을 수 없습니다 (만료 또는 모르는 id).")
            recommendations = session[1]
            if body.recommendation_index is not None and body.recommendation_index >= len(
                recommendations.recommendations
            ):
                raise HTTPException(422, "그 번호의 추천이 없습니다.")
        try:
            state = await manager.submit(
                user,
                req,
                differentiation=body.transfer_record(),
                recommendations=recommendations,
                chosen_recommendation=body.recommendation_index,
            )
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        except RunBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        return run_state_payload(state)

    @app.get(f"/{API_VERSION}/runs")
    async def list_route(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        states = manager.list_runs(user, limit)
        return {
            "runs": [run_state_payload(s, legacy=manager.is_legacy(s)) for s in reversed(states)]
        }

    @app.get(f"/{API_VERSION}/runs/{{run_id}}")
    async def status_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.status(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return run_state_payload(state, legacy=manager.is_legacy(state))

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/events")
    async def events_route(run_id: str) -> StreamingResponse:
        """SSE — 상태·진행이 바뀔 때마다 event: state. 끝 상태(ACTIVE 아님)가 되면 event: end."""
        rid = _run_id(run_id)
        try:
            state = await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc

        async def stream() -> AsyncIterator[bytes]:
            last: str | None = None
            waited = 0.0
            current = state
            prev = None
            while True:
                payload = json.dumps(
                    run_state_payload(current, legacy=manager.is_legacy(current)),
                    ensure_ascii=False,
                )
                if payload != last:
                    for name, data in _named_events(prev, current):
                        body = json.dumps(data, ensure_ascii=False)
                        yield f"event: {name}\ndata: {body}\n\n".encode()
                    yield f"event: state\ndata: {payload}\n\n".encode()
                    last = payload
                    prev = current
                if current.status not in ACTIVE or waited >= SSE_MAX_SEC:
                    yield f"event: end\ndata: {json.dumps({'status': current.status})}\n\n".encode()
                    return
                await asyncio.sleep(sse_poll_sec)
                waited += sse_poll_sec
                try:
                    current = await manager.status(user, rid)
                except RunNotFound:
                    yield b'event: end\ndata: {"status": "gone"}\n\n'
                    return

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"cache-control": "no-store", "x-accel-buffering": "no"},
        )

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/resume", status_code=202)
    async def resume_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.resume(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except RunNotResumable as exc:
            raise HTTPException(409, str(exc)) from exc
        except RunBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        return run_state_payload(state)

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/draft")
    async def draft_route(
        run_id: str, version: int | None = Query(default=None, ge=1, le=10_000)
    ) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            if version is not None:
                found = await manager.get_version(user, rid, version)
                return {"notice": UNTRUSTED_NOTICE, **version_payload(found, clean=_clean)}
            view = await manager.get_draft(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"notice": UNTRUSTED_NOTICE, **draft_payload(view, clean=_clean)}

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/versions")
    async def versions_route(run_id: str) -> dict[str, Any]:
        try:
            versions = await manager.versions(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"run_id": run_id, "versions": versions_payload(versions)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/revert")
    async def revert_route(run_id: str, body: RevertIn) -> dict[str, Any]:
        try:
            version = await manager.revert(user, _run_id(run_id), body.to)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": run_id, **version_payload(version, clean=_clean)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/review", status_code=202)
    async def review_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.review(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from exc
        except RunBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        return run_state_payload(state, legacy=manager.is_legacy(state))

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/review")
    async def review_get_route(
        run_id: str, round: int | None = Query(default=None, ge=1, le=10_000)
    ) -> dict[str, Any]:
        try:
            review = await manager.get_review(user, _run_id(run_id), round)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        if review is None:
            raise HTTPException(404, "검토 결과가 없습니다.")
        return {"notice": UNTRUSTED_NOTICE, **review_payload(review, clean=_clean)}

    async def _save(run_id: str, body: EditRequest) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            version = await manager.apply_edits(user, rid, body)
            state = await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:  # VersionConflict 포함
            raise HTTPException(409, str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            "stale_edits": state.stale_edits,
            **version_payload(version, clean=_clean),
        }

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/edits")
    async def edits_route(run_id: str, body: EditRequest) -> dict[str, Any]:
        """(호환) = POST /versions"""
        return await _save(run_id, body)

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/versions")
    async def save_route(run_id: str, body: EditRequest) -> dict[str, Any]:
        """④ 저장 — 편집을 반영한 새 버전 vN(메모 선택). 같은 내용이면 현재 버전을 그대로 돌려준다.
        base_version 이 현재와 다르면 409. 저장하면 임시 사본(working)을 지운다."""
        return await _save(run_id, body)

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/draft/working")
    async def working_get_route(run_id: str) -> dict[str, Any]:
        try:
            working = await manager.load_working(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        if working is None:
            raise HTTPException(404, "임시 저장이 없습니다.")
        return {"run_id": run_id, "notice": UNTRUSTED_NOTICE, "working": working}

    @app.put(f"/{API_VERSION}/runs/{{run_id}}/draft/working")
    async def working_put_route(run_id: str, body: WorkingIn) -> dict[str, Any]:
        """④ 임시 저장(autosave) — 서버 작업 사본. 버전이 아니다. 편집 가능한 상태에서만."""
        try:
            await manager.save_working(user, _run_id(run_id), body.model_dump())
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except WorkingRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": run_id, "saved": True}

    @app.delete(f"/{API_VERSION}/runs/{{run_id}}/draft/working", status_code=204)
    async def working_delete_route(run_id: str) -> Response:
        try:
            await manager.discard_working(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return Response(status_code=204)

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/versions/diff")
    async def diff_route(
        run_id: str,
        from_v: int = Query(alias="from", ge=1, le=10_000),
        to_v: int = Query(alias="to", ge=1, le=10_000),
    ) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            a = await manager.get_version(user, rid, from_v)
            b = await manager.get_version(user, rid, to_v)
            diff = await manager.diff(user, rid, from_v, to_v)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "run_id": rid,
            "notice": UNTRUSTED_NOTICE,
            **diff_payload(a, b, diff, clean=_clean),
        }

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/versions/{{version}}/restore")
    async def restore_route(run_id: str, version: int) -> dict[str, Any]:
        """복원 — 그 버전 내용으로 새 버전을 만든다 (= revert)."""
        rid = _run_id(run_id)
        try:
            new = await manager.revert(user, rid, version)
            state = await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": rid, "status": state.status, **version_payload(new, clean=_clean)}

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/outline")
    async def outline_route(run_id: str) -> dict[str, Any]:
        """③ 섹션 설계도(Q2, pipeline.outline). 없으면 404."""
        rid = _run_id(run_id)
        try:
            await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        loader = getattr(manager, "load_outline", None)
        data = await loader(user, rid) if loader is not None else None
        if not data:
            raise HTTPException(404, "설계도가 없습니다 (pipeline.outline 이 꺼져 있거나 아직 전).")
        return {"run_id": rid, "notice": UNTRUSTED_NOTICE, "outline": data}

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/draft-review")
    async def draft_review_route(run_id: str) -> dict[str, Any]:
        """③ Argon 1차 검토 결과(review_draft.json) — 점수·의견·자동 반영 여부·폐기 사유."""
        try:
            review = await manager.get_review(user, _run_id(run_id), kind="draft")
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        if review is None:
            raise HTTPException(404, "1차 검토 결과가 없습니다.")
        return {"notice": UNTRUSTED_NOTICE, **review_payload(review, clean=_clean)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/final-review", status_code=202)
    async def final_review_route(run_id: str) -> dict[str, Any]:
        """⑤ Argon 최종 검토 — 최신 저장 버전으로 1회(다시 받기도 여기, 횟수 기록).
        임시 편집이 있으면 409."""
        try:
            state = await manager.final_review(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except (InvalidTransition, RunBusy) as exc:
            raise HTTPException(409, str(exc)) from exc
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from exc
        return run_state_payload(state, legacy=manager.is_legacy(state))

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/final-review")
    async def final_review_get_route(
        run_id: str, round: int | None = Query(default=None, ge=1, le=10_000)
    ) -> dict[str, Any]:
        """⑤ 최종 검토 결과(review_final_rN.json). round 는 최종 검토 차수(1..), 없으면 최신."""
        try:
            review = await manager.get_review(user, _run_id(run_id), round, kind="final")
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        if review is None:
            raise HTTPException(404, "최종 검토 결과가 없습니다.")
        return {"notice": UNTRUSTED_NOTICE, **review_payload(review, clean=_clean)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/confirm")
    async def confirm_route(run_id: str, body: ConfirmIn) -> dict[str, Any]:
        try:
            confirmation = await manager.confirm(user, _run_id(run_id), body.choices())
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except ConfirmRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": run_id, "confirmed": confirmation.choices}

    @app.get(f"/{API_VERSION}/runs/{{run_id}}/render-check")
    async def render_check_route(run_id: str) -> dict[str, Any]:
        """렌더 전 점검 — 미해결 lint 알림·칸 길이 초과·전략 빈칸. 렌더를 막지 않는다 (읽기 전용).
        제안자 칸 길이는 여기서 재지 않는다 (GET 에는 개인정보를 싣지 않는다)."""
        try:
            check = await manager.render_check(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"run_id": run_id, **render_check_payload(check, titles=_titles(), clean=_clean)}

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/finalize")
    async def finalize_route(run_id: str, body: FinalizeIn | None = None) -> Response:
        """최종 마무리 → finalized → HWPX. 양식 파일은 이 경로로만. 제안자 정보는 본문으로만 받고
        저장하지 않는다. 렌더 점검 결과는 X-RRA-Check 헤더(JSON, ASCII 이스케이프)로."""
        body = body or FinalizeIn()
        proposer = ProposerInfo(
            proposed_on=body.proposed_on,
            department=body.department,
            proposer=Person(**body.proposer.model_dump()),
            head=Person(**body.head.model_dump()),
        )
        try:
            result = await manager.finalize(
                user,
                _run_id(run_id),
                choices=body.choices() or None,
                proposer=proposer,
                version=body.version,
            )
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except (FinalizeRejected, RenderRejected) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ConfirmRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        except RenderUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        check = render_check_payload(result.check, titles=_titles(), clean=_clean)
        return Response(
            content=result.data,
            media_type=HWPX_MEDIA_TYPE,
            headers={
                "content-disposition": (
                    f'attachment; filename="proposal-{run_id}-v{result.version}.hwpx"'
                ),
                "x-rra-version": str(result.version),
                "x-rra-status": result.state.status,
                "x-rra-check": json.dumps(check, ensure_ascii=True),
            },
        )

    @app.post(f"/{API_VERSION}/runs/{{run_id}}/reopen")
    async def reopen_route(run_id: str) -> dict[str, Any]:
        try:
            state = await manager.reopen(user, _run_id(run_id))
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except EditRejected as exc:
            raise HTTPException(409, str(exc)) from exc
        return run_state_payload(state, legacy=manager.is_legacy(state))

    # ── 정적 SPA (web/dist) ──────────────────────────────
    _mount_static(app, static_dir)
    return app


def _mount_static(app: FastAPI, static_dir: Path | None) -> None:
    """web/dist 가 있으면 "/" 에서 서빙 (SPA fallback: 파일이 없으면 index.html). 없으면 404."""
    root = Path(static_dir).resolve() if static_dir else None
    index = root / "index.html" if root else None
    if root is None or index is None or not index.is_file():

        @app.get("/", include_in_schema=False)
        async def _no_frontend() -> JSONResponse:
            return problem_response(404, "프론트엔드 빌드(web/dist)가 없습니다.")

        return

    @app.get("/{path:path}", include_in_schema=False)
    async def _spa(path: str) -> Response:
        candidate = (root / path).resolve() if path else index
        # 경로 이탈 차단: root 안의 실제 파일만. 그 외는 SPA 라우팅 → index.html
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        if path.startswith(("v1/", "healthz")):
            return problem_response(404, "없는 경로입니다.")
        return FileResponse(index)
