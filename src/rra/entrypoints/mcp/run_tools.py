"""MCP 쓰기 도구 본체 — rra_generate · rra_get_draft · rra_confirm · rra_review · rra_get_review ·
rra_edit · rra_finalize · rra_reopen. mcp SDK 를 import 하지 않는다.

권한 경계 (G-MCP):
- RunManager 를 받는 유일한 MCP 객체다. 읽기 도구(tools.py)는 이 모듈·RunManager 를
  import 할 수 없다 (import-linter 계약).
- 서버가 `--enable-generate` 로 떴을 때만 등록된다. 기본 서버는 읽기 도구 2개뿐이다.
- 사용자는 stdio 프로세스 소유자 한 명(`local`). 다른 사용자의 run 은 보이지 않는다.
- 생성은 백그라운드로 돌고 run_id 만 즉시 돌려준다. 진행은 rra_get_draft 로 폴링한다.
- 초안은 비신뢰 자료에서 파생된 텍스트다 → 경고 문구 + 구획 태그 무력화.
- 예산은 양식 칸에만 쓰는 사용자 입력이다. 제안자 성명·연락처는 받지 않는다 (렌더 시점 입력).
"""

from __future__ import annotations

import base64
from typing import Any

from rra.application.ports import RunBusy, RunNotFound
from rra.application.ports.renderer import RenderRejected
from rra.application.services import (
    ConfirmRejected,
    QueueFull,
    RenderUnavailable,
    RunManager,
    RunNotResumable,
)
from rra.application.services.run_manager import EditRejected, FinalizeRejected
from rra.domain.models import Budget, ProposalRequest, ProposerInfo
from rra.domain.models.proposer import Person
from rra.domain.models.review import EditRequest
from rra.domain.models.run import is_valid_run_id
from rra.domain.rules.review_flow import InvalidTransition
from rra.domain.rules.run_title import hwpx_filename
from rra.domain.rules.trust import UNTRUSTED_NOTICE, escape_untrusted
from rra.entrypoints.mcp.tools import ToolInputError
from rra.entrypoints.views import (
    diff_payload,
    differentiation_payload,
    draft_payload,
    recommendations_payload,
    render_check_payload,
    review_payload,
    version_payload,
    versions_payload,
)

POLL_HINT = "생성은 수 분 걸린다. rra_get_draft(run_id) 로 진행 상황과 부분 초안을 확인한다."


def _run_id(value: str) -> str:
    rid = (value or "").strip()
    if not is_valid_run_id(rid):
        raise ToolInputError("run_id 형식이 올바르지 않습니다.")
    return rid


class RraRunTools:
    def __init__(
        self,
        manager: RunManager,
        user: str = "local",
        *,
        precheck=None,
        differentiate=None,
        recommend=None,
        clarify=None,
    ):
        self._manager = manager
        self._user = user
        self._precheck = precheck
        self._differentiate = differentiate
        self._recommend = recommend
        self._clarify = clarify

    async def recommend(
        self,
        current_state: str,
        root_cause: str,
        limitation: str,
        goal: str,
        constraints: str = "",
        title_hint: str = "",
    ) -> dict[str, Any]:
        """차별화 과제 추천(ADR 0012) — precheck 뒤 기존 과제와 차별성을 갖는 과제 0~5건과 이유.
        추천할 것이 없으면 사유만. 외부 LLM 출력(비신뢰)."""
        if self._precheck is None or self._recommend is None:
            raise ToolInputError("과제 추천을 쓸 수 없습니다 (LLM 없음).")
        req = ProposalRequest(
            current_state=current_state,
            root_cause=root_cause,
            limitation=limitation,
            goal=goal,
            constraints=constraints,
            title_hint=title_hint,
        )
        alerts = await self._precheck(req)
        result = await self._recommend(req, alerts)
        return {
            "notice": UNTRUSTED_NOTICE,
            "blocking": any(a.blocking for a in alerts),
            **recommendations_payload(result, clean=escape_untrusted),
            "hint": (
                "고른 추천의 title 을 title_hint 로, differentiation 을 rra_generate 의 "
                "differentiation 으로 넘기고 goal 을 summary 로 보완하면 반영된다. "
                "원래 아이디어로 진행해도 된다."
            ),
        }

    async def differentiate(
        self,
        current_state: str,
        root_cause: str,
        limitation: str,
        goal: str,
        constraints: str = "",
        title_hint: str = "",
    ) -> dict[str, Any]:
        """기능 2 — precheck 뒤 차단·근접 유사과제별 활용·차별화 방향 (외부 LLM 출력, 비신뢰)."""
        if self._precheck is None or self._differentiate is None:
            raise ToolInputError("차별화 제안을 쓸 수 없습니다 (LLM 없음).")
        req = ProposalRequest(
            current_state=current_state,
            root_cause=root_cause,
            limitation=limitation,
            goal=goal,
            constraints=constraints,
            title_hint=title_hint,
        )
        alerts = await self._precheck(req)
        proposal = await self._differentiate(req, alerts)
        return {
            "notice": UNTRUSTED_NOTICE,
            "blocking": any(a.blocking for a in alerts),
            **differentiation_payload(proposal, clean=escape_untrusted),
            "hint": (
                "고른 방향(또는 고친 문장)을 rra_generate 의 differentiation 으로 넘기면 "
                "목적·방법·특이사항에 반영된다."
            ),
        }

    async def generate(
        self,
        current_state: str = "",
        root_cause: str = "",
        limitation: str = "",
        goal: str = "",
        constraints: str = "",
        resume_run_id: str | None = None,
        *,
        title_hint: str = "",
        policy_basis: str = "",
        beneficiaries: str = "",
        remarks: str = "",
        department: str = "",
        budget_account: str = "",
        budget_amount_thousand_krw: int | None = None,
        differentiation: str = "",
    ) -> dict[str, Any]:
        try:
            if resume_run_id:
                state = await self._manager.resume(self._user, _run_id(resume_run_id))
            else:
                budget = (
                    Budget(account=budget_account, amount_thousand_krw=budget_amount_thousand_krw)
                    if budget_account or budget_amount_thousand_krw is not None
                    else None
                )
                req = ProposalRequest(  # 필수 슬롯·길이 상한은 도메인 모델이 강제한다
                    current_state=current_state,
                    root_cause=root_cause,
                    limitation=limitation,
                    goal=goal,
                    constraints=constraints,
                    title_hint=title_hint,
                    policy_basis=policy_basis,
                    beneficiaries=beneficiaries,
                    remarks=remarks,
                    department=department,
                    budget=budget,
                    differentiation=differentiation,
                )
                state = await self._manager.submit(self._user, req)
        except (QueueFull, RunBusy, RunNotResumable, RunNotFound) as exc:
            raise ToolInputError(str(exc)) from exc
        done, total = state.progress
        return {
            "run_id": state.run_id,
            "status": state.status,
            "progress": [done, total],
            "hint": POLL_HINT,
        }

    async def get_draft(self, run_id: str) -> dict[str, Any]:
        try:
            view = await self._manager.get_draft(self._user, _run_id(run_id))
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        return {"notice": UNTRUSTED_NOTICE, **draft_payload(view, clean=escape_untrusted)}

    async def confirm(
        self,
        run_id: str,
        task_type: str | None = None,
        utilization: list[str] | None = None,
        strategy: list[str] | None = None,
    ) -> dict[str, Any]:
        """사용자가 고른 과제유형·활용계획·전략과제를 확정한다. 넘긴 항목만 덮어쓴다."""
        choices: dict[str, list[str]] = {}
        if task_type:
            choices["task_type"] = [task_type]
        if utilization:
            choices["utilization"] = list(utilization)
        if strategy:
            choices["strategy_alignment"] = list(strategy)
        try:
            confirmation = await self._manager.confirm(self._user, _run_id(run_id), choices)
        except (ConfirmRejected, RunNotFound) as exc:
            raise ToolInputError(str(exc)) from exc
        return {"run_id": run_id, "confirmed": confirmation.choices}

    # ── [5] 검토 → 편집 → 마무리 → 다시 열기 ───────────────
    async def final_review(self, run_id: str) -> dict[str, Any]:
        """⑤ Argon 최종 검토 — 최신 저장 버전으로 1회(다시 받기도 여기, 횟수 기록).

        임시 편집이 있으면 거부한다.
        """
        rid = _run_id(run_id)
        try:
            state = await self._manager.final_review(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except (QueueFull, RunBusy, InvalidTransition) as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            "final_reviews": state.final_reviews,
            "hint": "최종 검토는 수 분 걸린다. rra_get_final_review(run_id) 로 결과를 확인한다.",
        }

    async def get_final_review(self, run_id: str, round_no: int | None = None) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            review = await self._manager.get_review(self._user, rid, round_no, kind="final")
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        if review is None:
            raise ToolInputError("최종 검토 결과가 없습니다.")
        return {"notice": UNTRUSTED_NOTICE, **review_payload(review, clean=escape_untrusted)}

    async def versions(self, run_id: str) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            rows = await self._manager.versions(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        return {"run_id": rid, "versions": versions_payload(rows)}

    async def diff(self, run_id: str, from_version: int, to_version: int) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            a = await self._manager.get_version(self._user, rid, from_version)
            b = await self._manager.get_version(self._user, rid, to_version)
            rows = await self._manager.diff(self._user, rid, from_version, to_version)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except EditRejected as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "notice": UNTRUSTED_NOTICE,
            **diff_payload(a, b, rows, clean=escape_untrusted),
        }

    async def restore(self, run_id: str, to_version: int) -> dict[str, Any]:
        """복원 — 그 버전 내용으로 새 버전."""
        rid = _run_id(run_id)
        try:
            version = await self._manager.revert(self._user, rid, to_version)
            state = await self._manager.status(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except EditRejected as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            **version_payload(version, clean=escape_untrusted),
        }

    async def clarify(
        self,
        current_state: str,
        root_cause: str,
        limitation: str,
        goal: str,
        constraints: str = "",
        title_hint: str = "",
    ) -> dict[str, Any]:
        """③ 시작 전 입력 보강 질문(Q1). pipeline.clarify 가 꺼져 있으면 질문 0개."""
        req = ProposalRequest(
            current_state=current_state,
            root_cause=root_cause,
            limitation=limitation,
            goal=goal,
            constraints=constraints,
            title_hint=title_hint,
        )
        questions = await self._clarify(req) if self._clarify is not None else []
        return {"questions": questions, "skip_allowed": True}

    async def review(self, run_id: str) -> dict[str, Any]:
        """③ Argon 1차 검토(draft_review)를 시작한다 — 보통 초안 완료 뒤 자동. 검토 LLM 이 없으면
        건너뛰고 review_skipped 를 기록한다. 최종 검토는 rra_final_review."""
        rid = _run_id(run_id)
        try:
            state = await self._manager.review(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except (QueueFull, RunBusy, InvalidTransition) as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            "review_rounds": state.review_rounds,
            "review_skipped": state.review_skipped,
            "hint": "검토는 수 분 걸린다. rra_get_review(run_id) 로 결과를 확인한다.",
        }

    async def get_review(self, run_id: str, round_no: int | None = None) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            review = await self._manager.get_review(self._user, rid, round_no)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        if review is None:
            raise ToolInputError("검토 결과가 없습니다.")
        return {"notice": UNTRUSTED_NOTICE, **review_payload(review, clean=escape_untrusted)}

    async def edit(self, run_id: str, edits: dict[str, Any]) -> dict[str, Any]:
        """제안자 편집 반영 → 새 버전. edits = {sentences: [...], sections: [...], note: ""}."""
        rid = _run_id(run_id)
        request = EditRequest.model_validate(edits)  # 형식 오류는 ValidationError
        try:
            version = await self._manager.apply_edits(self._user, rid, request)
            state = await self._manager.status(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except EditRejected as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "status": state.status,
            **version_payload(version, clean=escape_untrusted),
        }

    async def finalize(
        self,
        run_id: str,
        *,
        task_type: str | None = None,
        utilization: list[str] | None = None,
        strategy: list[str] | None = None,
        proposed_on: str = "",
        department: str = "",
        proposer_rank: str = "",
        proposer_name: str = "",
        proposer_phone: str = "",
        head_rank: str = "",
        head_name: str = "",
        head_phone: str = "",
    ) -> dict[str, Any]:
        """최종 마무리 → HWPX(base64). 선택값은 넘긴 것만 덮어쓰고 나머지는 제안값. 제안자 정보는
        이 호출 인자로만 받고 저장하지 않는다. 양식 파일은 이 도구로만 만든다."""
        rid = _run_id(run_id)
        choices: dict[str, list[str]] = {}
        if task_type:
            choices["task_type"] = [task_type]
        if utilization:
            choices["utilization"] = list(utilization)
        if strategy:
            choices["strategy_alignment"] = list(strategy)
        proposer = ProposerInfo(
            proposed_on=proposed_on,
            department=department,
            proposer=Person(name=proposer_name, rank=proposer_rank, phone=proposer_phone),
            head=Person(name=head_name, rank=head_rank, phone=head_phone),
        )
        try:
            result = await self._manager.finalize(
                self._user, rid, choices=choices or None, proposer=proposer
            )
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except (FinalizeRejected, ConfirmRejected, RenderRejected, RenderUnavailable) as exc:
            raise ToolInputError(str(exc)) from exc
        return {
            "run_id": rid,
            "status": result.state.status,
            "version": result.version,
            "confirmed": result.confirmation.choices,
            "check": render_check_payload(
                result.check, titles=self._manager.generate.rules.titles, clean=escape_untrusted
            ),
            # 항목 2 — "<과제 제목>_v<번호>.hwpx" (파일 이름에 못 쓰는 글자는 뺀다)
            "filename": hwpx_filename(result.title, result.version),
            "media_type": "application/hwp+zip",
            "size": len(result.data),
            "content_base64": base64.b64encode(result.data).decode("ascii"),
        }

    async def reopen(self, run_id: str) -> dict[str, Any]:
        rid = _run_id(run_id)
        try:
            state = await self._manager.reopen(self._user, rid)
        except RunNotFound as exc:
            raise ToolInputError("해당 run 이 없습니다.") from exc
        except EditRejected as exc:
            raise ToolInputError(str(exc)) from exc
        return {"run_id": rid, "status": state.status}
