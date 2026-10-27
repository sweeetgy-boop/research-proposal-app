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
from rra.application.usecases.clarify_input import ClarifyInput, apply_answers
from rra.application.usecases.differentiate import Differentiate
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.application.usecases.recommend_projects import RecommendProjects
from rra.domain.models import (
    Chunk,
    Confirmation,
    DifferentiationProposal,
    OverlapAlert,
    ProjectRecommendation,
    ProposalRequest,
    RecommendationPreview,
    RecommendationResult,
    RunState,
)
from rra.domain.models.run import FINISHED
from rra.domain.rules import agent_policy as policy
from rra.domain.rules.overlap import uncollected_sources
from rra.domain.rules.recommendation import apply_recommendation

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
    # 차단 알림이 있으면 자동으로 만든 차별화 제안 (없으면 None — 근접 알림은 담당자 요청 시)
    differentiation: DifferentiationProposal | None = None
    # precheck 뒤 자동 1회 만든 차별화 과제 추천 (recommend.auto). 유스케이스가 없거나 끄면 None
    recommendations: RecommendationResult | None = None


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
        recommend: RecommendProjects | None = None,
        recommend_auto: bool = True,
        clarify: ClarifyInput | None = None,
    ):
        self.precheck, self.manager, self.repo, self.user = precheck, manager, repo, user
        self.differentiate_usecase = differentiate  # None 이면 기능 2 를 쓸 수 없다 (LLM 없음)
        self.recommend_usecase = recommend  # None 이면 과제 추천을 쓸 수 없다
        self.recommend_auto = recommend_auto
        self.clarify_usecase = clarify  # Q1 입력 보강 질문 (pipeline.clarify 가 켜져 있을 때만)
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
        decisions = policy.after_precheck(
            alerts, req, corpus_size=corpus, recommend_auto=self.recommend_auto
        )
        for d in decisions:
            if d.tool is None:
                self._log(d, d.action)
        proposal = None
        if policy.has_blocking(alerts) and self.differentiate_usecase is not None:
            proposal = await self.differentiate(req, alerts)  # 차단 → 자동, 근접만이면 수동
        recommendations = None
        if self.recommend_auto and self.recommend_usecase is not None:
            recommendations = await self.recommend(req, alerts)  # precheck 완료 → 자동 1회
        return IntakeResult(
            alerts, decisions, uncollected_sources(counts), corpus, proposal, recommendations
        )

    # ── precheck 완료 → rra_recommend (차별화 과제 추천, ADR 0012) ──
    async def recommend(
        self, req: ProposalRequest, alerts: list[OverlapAlert], *, again: bool = False
    ) -> RecommendationResult | None:
        """기존 과제와 차별성을 갖는 과제 0~5건. 유스케이스가 없으면(LLM 없음) None."""
        decision = policy.on_recommend(auto=not again)
        if self.recommend_usecase is None:
            self._log(decision, "과제 추천 LLM 없음 — 건너뜀")
            return None
        result = await self.recommend_usecase(req, alerts)
        where = "로컬 모델" if result.fallback_local else (result.provider or "LLM")
        if result.skipped_reason:
            summary = f"건너뜀 ({result.skipped_reason})"
        elif not result.recommendations:
            summary = f"추천 없음 — {result.no_recommendation_reason} ({where})"
        else:
            summary = (
                f"추천 {len(result.recommendations)}건, 제외 {len(result.discarded)}건 ({where})"
            )
        self._log(decision, summary)
        return result

    # ── ③ 시작 전 입력 보강 질문 (Q1) → rra_clarify ─────────
    async def clarify(self, req: ProposalRequest) -> list[str]:
        """빠진 정보 질문 최대 3개 (로컬 모델). 유스케이스가 없으면 0개 → 바로 생성."""
        questions = await self.clarify_usecase(req) if self.clarify_usecase is not None else []
        self._log(policy.on_clarify(questions=len(questions)), f"질문 {len(questions)}개")
        return questions

    @staticmethod
    def apply_clarification(req: ProposalRequest, answers: dict[str, str]) -> ProposalRequest:
        """답을 보충 정보(supplement)로 붙인 입력. 건너뛰면(빈 답) 그대로."""
        return apply_answers(req, answers)

    @staticmethod
    def preview_recommendation(
        req: ProposalRequest, rec: ProjectRecommendation, index: int
    ) -> tuple[ProposalRequest, RecommendationPreview]:
        """추천 하나를 입력에 반영한 미리보기 — 사용자가 고쳐 확정한다 (LLM 없음)."""
        return apply_recommendation(req, rec, index)

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
        recommendations: RecommendationResult | None = None,
        chosen_recommendation: int | None = None,
    ) -> RunState:
        if not policy.may_generate(alerts, acknowledged=acknowledged):
            raise HumanConfirmationRequired("차단 경보를 확인한 뒤에만 초안을 생성합니다.")
        decisions = policy.after_precheck(alerts, req, corpus_size=1, acknowledged=acknowledged)
        decision = next(d for d in decisions if d.tool == "rra_generate")
        transfer = None
        if differentiation is not None:
            transfer = {**differentiation.transfer(), "chosen": bool(req.differentiation.strip())}
        state = await self.manager.submit(
            self.user,
            req,
            differentiation=transfer,
            recommendations=recommendations,
            chosen_recommendation=chosen_recommendation,
        )
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
