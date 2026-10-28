"""REST 경로 (레인 D, 항목 16·17) — 단계 이동의 run 입력 조회, 입력 변경 미리보기·다시 쓰기,
근거 일괄 승인. 로직 없음 — RunManager 를 부르고 views 로 직렬화한다. create_app 이 등록한다.

- GET  /v1/runs/{id}/request                       저장된 입력(①)·② 우선 근거
- POST /v1/runs/{id}/request/preview                바뀐 칸·관련 섹션 (저장하지 않음)
- POST /v1/runs/{id}/regenerate                     관련 섹션만(sections) / 전체(all) → 새 버전
- POST /v1/runs/{id}/evidence-decisions/bulk-approve 확인 필요 문장을 뺀 근거 일괄 승인 → 새 버전
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from rra.application.ports import RunBusy, RunNotFound
from rra.application.services.run_manager import EditRejected, FeatureDisabled, VersionConflict
from rra.domain.rules.request_change import change_summary
from rra.entrypoints.api.schemas_format import BulkApproveIn, RegenerateIn, RequestChangeIn
from rra.entrypoints.views import regenerate_payload, version_payload

Own = Callable[[Request, str], Awaitable[tuple[str, str]]]


def register_format_routes(
    app: FastAPI,
    *,
    manager: Any,
    own: Own,
    clean: Callable[[str], str],
    titles: Callable[[], dict[str, str]],
    api_version: str = "v1",
) -> None:
    base = f"/{api_version}/runs/{{run_id}}"

    @app.get(f"{base}/request")
    async def run_request_route(request: Request, run_id: str) -> dict[str, Any]:
        """단계 표시 ①·② 를 run 안에서 열 때 — 그 run 의 저장된 입력. 제안자 입력이라 정리만."""
        try:
            owner, rid = await own(request, run_id)
            inputs = await manager.run_inputs(owner, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "제안서를 찾을 수 없습니다.") from exc
        return {"run_id": rid, **inputs}

    @app.post(f"{base}/request/preview")
    async def request_preview_route(
        request: Request, run_id: str, body: RequestChangeIn
    ) -> dict[str, Any]:
        try:
            owner, rid = await own(request, run_id)
            out = await manager.request_change_preview(
                owner, rid, body.request, priority_evidence=body.priority_evidence
            )
        except RunNotFound as exc:
            raise HTTPException(404, "제안서를 찾을 수 없습니다.") from exc
        names = titles()
        return {
            "run_id": rid,
            "fields": change_summary(out["fields"]),
            "sections": [{"key": k, "title": names.get(k, k)} for k in out["sections"]],
            "all_sections": len(out["all_sections"]),
            "can_regenerate": out["can_regenerate"],
            "reason": out["reason"],
            "version": out["version"],
        }

    @app.post(f"{base}/regenerate")
    async def regenerate_route(request: Request, run_id: str, body: RegenerateIn) -> dict[str, Any]:
        """입력 변경 저장 — 관련 섹션만 다시 쓰기 / 초안 전체 다시 생성. 둘 다 새 버전(이전 버전은
        [버전·비교]에 남는다). 다시 쓰지 못한 섹션은 이전 내용 그대로 + failed 로 알린다."""
        try:
            owner, rid = await own(request, run_id)
            result = await manager.regenerate(
                owner,
                rid,
                body.request,
                mode=body.mode,
                base_version=body.base_version,
                priority_evidence=body.priority_evidence,
            )
            state = await manager.status(owner, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "제안서를 찾을 수 없습니다.") from exc
        except RunBusy as exc:
            raise HTTPException(
                409, "생성·검토가 진행 중입니다 — 끝난 뒤 다시 시도하십시오."
            ) from exc
        except EditRejected as exc:  # VersionConflict 포함
            raise HTTPException(409, str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            **regenerate_payload(result, titles=titles()),
            **version_payload(result.version, clean=clean, run_id=rid),
        }

    @app.post(f"{base}/evidence-decisions/bulk-approve")
    async def bulk_approve_route(
        request: Request, run_id: str, body: BulkApproveIn | None = None
    ) -> dict[str, Any]:
        body = body or BulkApproveIn()
        try:
            owner, rid = await own(request, run_id)
            version = await manager.bulk_approve_evidence(
                owner, rid, base_version=body.base_version
            )
            state = await manager.status(owner, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "제안서를 찾을 수 없습니다.") from exc
        except FeatureDisabled as exc:
            raise HTTPException(503, str(exc)) from exc
        except (VersionConflict, EditRejected) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            **version_payload(version, clean=clean, run_id=rid),
        }
