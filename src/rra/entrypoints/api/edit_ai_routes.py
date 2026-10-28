"""작성·편집 AI 경로 (2026-10-28 레인 B) — create_app 이 register() 로 붙인다. 로직 없음.

- POST /v1/ideas/policy-cards           ③ 보강 질문: 정책적 중요도 작성안 최대 4개 (+ [다른 안
보기])
- POST /v1/ideas/policy-cards/polish    고른 안을 고친 글 → [AI로 다듬기]
- POST /v1/runs/{id}/policy-cards       ④ 빈 2-가-(1): 같은 작성안 (run 의 입력으로)
- POST /v1/runs/{id}/policy-cards/polish
- POST /v1/runs/{id}/policy-choice      고른 안(또는 "정책 근거 없음") → 새 버전
- GET  /v1/runs/{id}/changes            ④ "변경 n건" — 마지막 검토 이후 종류별 건수

모든 LLM 출력은 비신뢰(UNTRUSTED_NOTICE). 예외 → 404·409·503 (problem+json 은 앱 처리기).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from rra.application.ports import RunNotFound
from rra.application.services.run_manager import EditRejected, VersionConflict
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.api.schemas_editai import (
    PolicyCardsIn,
    PolicyChoiceIn,
    PolicyPolishIn,
    RunPolicyCardsIn,
    RunPolicyPolishIn,
)
from rra.entrypoints.views import version_payload
from rra.entrypoints.views_editai import (
    change_summary_payload,
    policy_cards_payload,
    policy_polish_payload,
)


def register(
    app: FastAPI,
    *,
    api_version: str,
    manager: Any,
    svc: Callable[[Request, str], Any],
    own: Callable[[Request, str], Awaitable[tuple[str, str]]],
    clean: Callable[[str], str],
) -> None:
    V = api_version

    def _cards(request: Request) -> Any:
        uc = svc(request, "policy_cards")
        if uc is None:
            raise HTTPException(503, "정책적 중요도 작성안을 쓸 수 없습니다 (정책 자료·모델 없음).")
        return uc

    @app.post(f"/{V}/ideas/policy-cards")
    async def policy_cards_route(request: Request, body: PolicyCardsIn) -> dict[str, Any]:
        """③ 보강 질문 — 정책 근거가 없을 때 수집 정책 자료(국토부·공사 전략·감사 지적·정부 R&D
        공고)
        에서 아이디어 관련 구간을 찾아 방향이 겹치지 않는 작성안 최대 4개. exclude_doc_ids 는
        [다른 안 보기] 때 이미 본 문서. 결과는 자동으로 들어가지 않는다 — 고른 것만
        RunIn.policy_choice 로."""
        result = await _cards(request)(body.request(), exclude_docs=body.exclude_doc_ids)
        return {"notice": UNTRUSTED_NOTICE, **policy_cards_payload(result, clean=clean)}

    @app.post(f"/{V}/ideas/policy-cards/polish")
    async def policy_polish_route(request: Request, body: PolicyPolishIn) -> dict[str, Any]:
        """[AI로 다듬기] — 고른 안을 제안자가 고친 글을 같은 근거 안에서 다듬는다 (Argon 먼저)."""
        result = await _cards(request).polish(body.request(), body.choice, body.text)
        return {"notice": UNTRUSTED_NOTICE, **policy_polish_payload(result, clean=clean)}

    @app.post(f"/{V}/runs/{{run_id}}/policy-cards")
    async def run_policy_cards_route(
        request: Request, run_id: str, body: RunPolicyCardsIn
    ) -> dict[str, Any]:
        """④ 빈 2-가-(1) — run 의 입력으로 작성안 최대 4개."""
        try:
            result = await manager.run_policy_cards(
                *await own(request, run_id), exclude_docs=body.exclude_doc_ids
            )
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"notice": UNTRUSTED_NOTICE, **policy_cards_payload(result, clean=clean)}

    @app.post(f"/{V}/runs/{{run_id}}/policy-cards/polish")
    async def run_policy_polish_route(
        request: Request, run_id: str, body: RunPolicyPolishIn
    ) -> dict[str, Any]:
        try:
            result = await manager.run_policy_polish(
                *await own(request, run_id), body.choice, body.text
            )
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"notice": UNTRUSTED_NOTICE, **policy_polish_payload(result, clean=clean)}

    @app.post(f"/{V}/runs/{{run_id}}/policy-choice")
    async def run_policy_choice_route(
        request: Request, run_id: str, body: PolicyChoiceIn
    ) -> dict[str, Any]:
        """고른 작성안(또는 mode none = "정책 근거 없음")으로 2-가-(1) 을 바꾼 새 버전. 인용 구간은
        저장소 원문과 대조해 통과한 것만 근거로 남는다."""
        user, rid = await own(request, run_id)
        try:
            version = await manager.choose_policy(
                user, rid, body.choice, base_version=body.base_version
            )
            state = await manager.status(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        except (EditRejected, VersionConflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            **version_payload(version, clean=clean, run_id=rid),
        }

    @app.get(f"/{V}/runs/{{run_id}}/changes")
    async def run_changes_route(request: Request, run_id: str) -> dict[str, Any]:
        """④ "변경 n건" — 마지막 검토(최종 검토 버전, 없으면 초안) 이후 바뀐 것을 종류별로. 저장하지
        않은 편집은 화면이 더한다."""
        user, rid = await own(request, run_id)
        try:
            summary = await manager.changes(user, rid)
        except RunNotFound as exc:
            raise HTTPException(404, "run 을 찾을 수 없습니다.") from exc
        return {"run_id": rid, **change_summary_payload(summary)}
