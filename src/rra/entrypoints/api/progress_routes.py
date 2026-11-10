"""③ 생성 진행 — 작성 중 섹션 먼저 보기 (2026-10-29 레인 C, ADR 0045) + ② 과제안 단계 SSE
(2026-11-09 레인 A). create_app 이 register()·register_recommend_stream() 으로 붙인다. 로직 없음.

- GET  /v1/runs/{id}/sections-progress          끝난 섹션 글(읽기 전용, 버전 아님)·남은 섹션 키
- POST /v1/precheck/recommendations/stream      과제안 SSE — 단계 이벤트 먼저, 과제안은 이어서

과제안 SSE 이벤트 (data 는 JSON 한 줄):
  stage            {"stage": "search"|"generate", "status": "started"|"reverted"}
  analogies        {"mode": "novel", "coverage": {...}, "analogies": [...]}  — novel 갈래만, 확인
                   범위와 다른 분야 사례가 준비되는 즉시(과제안 작성 전). 칸 모양은 최종 응답의 같은
                   칸과 같다
  recommendations  POST /v1/precheck/recommendations 응답 본문과 같은 객체
  error            {"status": 409|500, "detail": "..."}  (일일 상한 409, 그 밖 500 — 화면 표시 문구)
  end              {"status": "done"|"error"}
  주석 줄 ": keep-alive" 를 `heartbeat_sec` 마다 보낸다(프록시 유휴 끊김 방지).
연결이 끊기면 작업(코루틴)을 취소한다(ADR 0038 과 같은 뜻). 글 칸은 LLM 출력·수집 자료(비신뢰) →
recommend_full 이 clean 을 거친 응답을 만든다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from rra.application.ports import RunNotFound
from rra.application.ports.auth import BudgetExhausted
from rra.domain.models import ProposalRequest
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.views import novel_progress_payload

logger = logging.getLogger("rra.api.progress")

# 유스케이스(recommend_projects.PROGRESS_*)가 부르는 이름 — 그 밖은 보내지 않는다
EVENT_STAGE = "stage"
EVENT_ANALOGIES = "analogies"
EVENT_RECOMMENDATIONS = "recommendations"
EVENT_ERROR = "error"
EVENT_END = "end"
STAGES = frozenset({"search", "generate"})
STAGE_STATUSES = frozenset({"started", "reverted"})
BUDGET_DETAIL = "오늘 외부 AI 호출 한도에 이르렀습니다."
FAILED_DETAIL = "과제안을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요."
_DONE = object()

Progress = Callable[[str, dict[str, Any]], None]
RecommendFull = Callable[[Request, ProposalRequest, Progress], Awaitable[dict[str, Any]]]


def register(
    app: FastAPI,
    *,
    api_version: str,
    manager: Any,
    own: Callable[[Request, str], Awaitable[tuple[str, str]]],
    clean: Callable[[str], str],
) -> None:
    V = api_version

    @app.get(f"/{V}/runs/{{run_id}}/sections-progress")
    async def sections_progress_route(request: Request, run_id: str) -> dict[str, Any]:
        user, rid = await own(request, run_id)
        try:
            view = await manager.sections_progress(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "제안서를 찾을 수 없습니다.") from exc
        return {
            "run_id": rid,
            "notice": UNTRUSTED_NOTICE,
            "status": view["status"],
            "sections": [
                {"key": s["key"], "sentences": [clean(t) for t in s["sentences"]]}
                for s in view["sections"]
            ],
            "pending": list(view["pending"]),
        }


def sse(name: str, data: Any) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def shape_event(name: str, data: dict[str, Any], *, clean: Callable[[str], str]) -> bytes | None:
    """유스케이스 진행 자료 → SSE 바이트. 모르는 이름·값은 보내지 않는다(None)."""
    if name == EVENT_STAGE:
        stage, status = str(data.get("stage", "")), str(data.get("status", ""))
        if stage not in STAGES or status not in STAGE_STATUSES:
            return None
        return sse(EVENT_STAGE, {"stage": stage, "status": status})
    if name == EVENT_ANALOGIES:
        return sse(
            EVENT_ANALOGIES,
            novel_progress_payload(
                data.get("coverage"),
                data.get("analogies") or [],
                clean=clean,
                analogy_report=data.get("analogy_report"),
            ),
        )
    return None


def register_recommend_stream(
    app: FastAPI,
    *,
    api_version: str,
    recommend_full: RecommendFull | None,
    clean: Callable[[str], str],
    heartbeat_sec: float = 5.0,
) -> None:
    """POST /{V}/precheck/recommendations/stream — recommend_full(request, req, progress) 는
    app.py 의 과제안 경로(지금 AI 판정 → 추천 → 되돌림 행 합치기 → 응답 본문)에 progress 콜백만
    더한 것. None 이면(LLM 없음) 503."""
    V = api_version

    @app.post(f"/{V}/precheck/recommendations/stream")
    async def recommend_stream_route(request: Request, req: ProposalRequest) -> StreamingResponse:
        if recommend_full is None:
            raise HTTPException(503, "과제 추천을 쓸 수 없습니다 (LLM 없음).")
        return StreamingResponse(
            _stream(request, req, recommend_full, clean=clean, heartbeat=heartbeat_sec),
            media_type="text/event-stream",
            headers={"cache-control": "no-store", "x-accel-buffering": "no"},
        )


async def _stream(
    request: Request,
    req: ProposalRequest,
    recommend_full: RecommendFull,
    *,
    clean: Callable[[str], str],
    heartbeat: float,
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def progress(name: str, data: dict[str, Any]) -> None:
        queue.put_nowait((name, dict(data)))

    task = asyncio.ensure_future(recommend_full(request, req, progress))
    task.add_done_callback(lambda _t: queue.put_nowait(_DONE))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), heartbeat)
            except TimeoutError:
                yield b": keep-alive\n\n"
                continue
            if item is _DONE:
                break
            body = shape_event(item[0], item[1], clean=clean)
            if body is not None:
                yield body
        try:
            result = task.result()
        except BudgetExhausted:
            yield sse(EVENT_ERROR, {"status": 409, "detail": BUDGET_DETAIL})
            yield sse(EVENT_END, {"status": "error"})
            return
        except HTTPException as exc:
            yield sse(EVENT_ERROR, {"status": exc.status_code, "detail": str(exc.detail)})
            yield sse(EVENT_END, {"status": "error"})
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 열거값(예외 클래스)만 — 메시지에 본문·키가 섞일 수 있다
            logger.warning("api.recommend_stream_failed kind=%s", type(exc).__name__)
            yield sse(EVENT_ERROR, {"status": 500, "detail": FAILED_DETAIL})
            yield sse(EVENT_END, {"status": "error"})
            return
        yield sse(EVENT_RECOMMENDATIONS, result)
        yield sse(EVENT_END, {"status": "done"})
    finally:
        if not task.done():  # 브라우저가 끊었다 — 작업도 멈춘다
            task.cancel()
            logger.info("api.recommend_stream_cancelled")
