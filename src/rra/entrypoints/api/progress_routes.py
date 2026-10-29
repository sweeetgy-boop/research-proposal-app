"""③ 생성 진행 — 작성 중 섹션 먼저 보기 (2026-10-29 레인 C, ADR 0045). create_app 이 register() 로
붙인다. 로직 없음.

- GET /v1/runs/{id}/sections-progress   끝난 섹션 글(읽기 전용, 버전 아님)·남은 섹션 키

섹션 글은 LLM 출력(비신뢰, UNTRUSTED_NOTICE).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from rra.application.ports import RunNotFound
from rra.domain.rules.trust import UNTRUSTED_NOTICE


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
