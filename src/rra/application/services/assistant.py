"""Agent — 기획서의 Tool 호출 조건(domain/rules/agent_policy)대로 유스케이스를 부르고 기록한다.

화면(Streamlit)·MCP 호스트가 공유하는 오케스트레이터. 로직은 agent_policy 에, 실행은 여기에.
LLM 은 판단에 쓰지 않는다. 모든 호출은 ToolCall 로 trace 에 남아 "Agent 활동 기록"이 된다.

주의: repo(sqlite)는 만든 스레드에서만 쓸 수 있다. 호출자가 한 이벤트 루프/스레드에서 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from rra.application.ports import DocumentRepository
from rra.application.services.run_manager import DraftView, RunManager
from rra.application.usecases.differentiate import Differentiate
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import (
    Chunk,
    Confirmation,
    DifferentiationProposal,
    OverlapAlert,
    ProposalRequest,
    RunState,
)
from rra.domain.models.run import FINISHED
from rra.domain.rules import agent_policy as policy
from rra.domain.rules.overlap import uncollected_sources

SEARCH_K_MAX = 10


class HumanConfirmationRequired(RuntimeError):
    """차단 경보가 있는데 담당자가 확인하지 않았다 — 생성하지 않는다."""


@dataclass(frozen=True)
class ToolCall:
    at: str
    condition: str
    tool: str | None
    summary: str


@dataclass(frozen=True)
class IntakeResult:
    alerts: list[OverlapAlert]
    decisions: list[policy.Decision]
    uncollected: list[str] = field(default_factory=list)
    corpus_size: int = 0


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ProposalAssistant:
    def __init__(
        self,
        precheck: PrecheckOverlap,
        manager: RunManager,
        repo: DocumentRepository,
        *,
        user: str = "local",
        clock=_utcnow,
        max_trace: int = 200,
        differentiate: Differentiate | None = None,
    ):
        self.precheck, self.manager, self.repo, self.user = precheck, manager, repo, user
        self.differentiate_usecase = differentiate  # None 이면 기능 2 를 쓸 수 없다 (LLM 없음)
        self._clock, self._max_trace = clock, max_trace
        self.trace: list[ToolCall] = []
        self._last_status: dict[str, str] = {}

    @property
    def rules(self):
        return self.manager.generate.rules

    def _log(self, decision: policy.Decision, summary: str) -> None:
        self.trace.append(ToolCall(self._clock(), decision.condition, decision.tool, summary))
        del self.trace[: -self._max_trace]

    # ── 아이디어 입력 수신 → rra_precheck ──────────────────
    async def intake(self, req: ProposalRequest) -> IntakeResult:
        alerts = await self.precheck(req)
        counts = await self.repo.count_by_source()
        corpus = sum(counts.values())
        blocking = sum(1 for a in alerts if a.blocking)
        self._log(
            policy.on_intake(), f"경보 {len(alerts)}건 (차단 {blocking}건), 적재 문서 {corpus}건"
        )
        decisions = policy.after_precheck(alerts, req, corpus_size=corpus)
        for d in decisions:
            if d.tool is None:
                self._log(d, d.action)
        return IntakeResult(alerts, decisions, uncollected_sources(counts), corpus)

    # ── 차단·근접 알림 → rra_differentiate (기능 2) ─────────
    async def differentiate(
        self, req: ProposalRequest, alerts: list[OverlapAlert]
    ) -> DifferentiationProposal | None:
        """겹친 과제별 활용·차별화 방향. 유스케이스가 없으면(LLM 없음) None."""
        if self.differentiate_usecase is None:
            self._log(policy.on_differentiate(), "차별화 제안 LLM 없음 — 건너뜀")
            return None
        proposal = await self.differentiate_usecase(req, alerts)
        where = "로컬 모델" if proposal.fallback_local else (proposal.provider or "LLM")
        summary = (
            f"건너뜀 ({proposal.skipped_reason})"
            if proposal.skipped_reason
            else f"제안 {len(proposal.items)}건, 폐기 {len(proposal.discarded)}건 ({where})"
        )
        self._log(policy.on_differentiate(), summary)
        return proposal

    # ── 경보 없음 / 담당자 진행 선택 → rra_generate ────────
    async def proceed(
        self,
        req: ProposalRequest,
        alerts: list[OverlapAlert],
        *,
        acknowledged: bool,
        differentiation: DifferentiationProposal | None = None,
    ) -> RunState:
        if not policy.may_generate(alerts, acknowledged=acknowledged):
            raise HumanConfirmationRequired("차단 경보를 확인한 뒤에만 초안을 생성합니다.")
        decisions = policy.after_precheck(alerts, req, corpus_size=1, acknowledged=acknowledged)
        decision = next(d for d in decisions if d.tool == "rra_generate")
        transfer = None
        if differentiation is not None:
            transfer = {**differentiation.transfer(), "chosen": bool(req.differentiation.strip())}
        state = await self.manager.submit(self.user, req, differentiation=transfer)
        self._log(
            decision,
            f"run {state.run_id} 대기열 등록" + (" (차단 경보 확인 후)" if acknowledged else ""),
        )
        return state

    async def resume(self, run_id: str) -> RunState:
        state = await self.manager.resume(self.user, run_id)
        self._log(
            policy.Decision("중단된 run 재개", "rra_generate(resume) 호출", "rra_generate"),
            f"run {run_id}",
        )
        return state

    # ── rra_get_draft 폴링 (상태가 바뀔 때만 기록) ──────────
    async def poll(self, run_id: str) -> DraftView:
        view = await self.manager.get_draft(self.user, run_id)
        status = view.state.status
        if self._last_status.get(run_id) != status:
            self._last_status[run_id] = status
            done, total = view.state.progress
            tail = " — 완료" if status in FINISHED else ""
            self._log(
                policy.Decision("진행 상황·초안 조회", "rra_get_draft 호출", "rra_get_draft"),
                f"run {run_id} {status} {done}/{total}{tail}",
            )
        return view

    def list_runs(self, limit: int = 10) -> list[RunState]:
        return self.manager.list_runs(self.user, limit=limit)

    # ── 담당자 자료 질의 → rra_search ───────────────────────
    async def ask(self, query: str, *, k: int = 5) -> list[Chunk]:
        q = query.strip()
        if not q:
            return []
        k = max(1, min(int(k), SEARCH_K_MAX))
        chunks = list(await self.repo.hybrid_search([q], k=k))
        self._log(policy.on_query(), f"구획 {len(chunks)}건 (k={k})")
        return chunks

    # ── 확정 → rra_confirm ─────────────────────────────────
    async def confirm(self, run_id: str, choices: dict[str, list[str]]) -> Confirmation:
        confirmation = await self.manager.confirm(self.user, run_id, choices)
        self._log(policy.on_confirm(), f"run {run_id} {', '.join(sorted(choices))}")
        return confirmation
