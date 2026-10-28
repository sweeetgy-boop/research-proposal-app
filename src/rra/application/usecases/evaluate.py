"""초안 품질 강화 효과 측정 (`rra eval`, [Q] Q9) — 골든셋 아이디어마다 실제 흐름(②precheck → ③생성
→ v1 → Argon 1차 검토 → v2)을 RunManager 로 돌리고 지표를 모은다.

지표(아이디어마다):
- v1·v2 알림 수(DraftVersion.alerts), 섹션별 문장 수, 규칙 검사 자동 정리 수·경고 수
- 근거 관련도: 인용된 근거 id 수, 논문(openalex) 인용 수, 무관 근거 인용 수(한글 청크인데 질의
  키워드가 하나도 없는 청크를 인용한 문장 — 대리 지표)
- 1차 검토: 4개 기준 점수, 자동 반영 수, 추가 문장 제안·반영 수, 필수 요소 충족률, 후보 선택
- precheck: 알림 수·상위 doc_id, 정답(expected_similar)이 있으면 적중 여부
- 단계별 시간(step 기록, 초 단위)·전체 시간, 서버 RSS, reranker 호출·지연

pipeline 구성(모두 끔·모두 켬·하나씩 끔)별로 한 번씩 돌려 JSON 으로 남기고, 표는
entrypoints/views.eval_markdown 이 만든다. Gemini 호출 수는 작성(compose_calls —
Argon 작성·대체 작성) + 검토 transfer.calls 합이다. 그림 이미지 호출은 figure_calls 로 따로 센다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from rra.application.ports.reranker import rerank_stats
from rra.domain.models import ProposalRequest
from rra.domain.rules.keywords import KeywordRule, keyword_overlap
from rra.domain.rules.lint import STYLE_CODES
from rra.domain.rules.relevance import has_hangul
from rra.domain.rules.writer import gemini_calls, local_sections


@dataclass
class EvalIdea:
    name: str
    run_id: str
    status: str
    seconds: float  # 생성 + 1차 검토 전체(벽시계)
    step_seconds: dict[str, float] = field(default_factory=dict)
    v1_alerts: int = 0
    v2_alerts: int | None = None
    v1_sentences: dict[str, int] = field(default_factory=dict)
    v2_sentences: dict[str, int] = field(default_factory=dict)
    style_fixed: int = 0
    style_warnings: int = 0
    cited_ids: int = 0
    paper_citations: int = 0
    irrelevant_citations: int = 0
    scores: dict[str, int] = field(default_factory=dict)
    applied: int = 0
    additions: int = 0
    additions_applied: int = 0
    checklist_coverage: float | None = None
    candidates: dict[str, str] = field(default_factory=dict)
    outline_sections: int | None = None
    exemplars: int = 0
    section_search: bool = False
    precheck_alerts: int = 0
    precheck_blocking: int = 0
    precheck_top: list[str] = field(default_factory=list)
    precheck_hit: bool | None = None
    gemini_calls: int = 0
    dropped_sentences: int = 0
    review_status: str | None = None
    failed_sections: list[str] = field(default_factory=list)  # 빈 초안 금지(ADR 0027) 실패 섹션
    fallback_sections: list[str] = field(default_factory=list)  # 대체 작성(Gemini) 섹션
    fallback_calls: int = 0  # 대체 작성 Gemini 호출 수 (gemini_calls 는 검토만)
    # [3] ADR 0032 — 작성자(gemini|local), 로컬 대체 섹션, 작성 단계 Gemini 호출 수
    # (Argon 작성 + 대체 작성), 단계별 Gemini 호출 {compose, review, figures, total},
    # local_check 불일치 수
    writer: str = "local"
    local_sections: list[str] = field(default_factory=list)
    compose_calls: int = 0
    gemini_by_stage: dict[str, int] = field(default_factory=dict)
    local_check_mismatches: int | None = None
    # [G] 그림: 만든 수·Nano Banana 채택 수·기본 그림 수·건너뛴 수·이미지 호출 수·그림 단계
    # 시간(초)·그림 의견(검토 지적) 수
    figures_total: int = 0
    figures_nano: int = 0
    figures_baseline: int = 0
    figures_skipped: int = 0
    figure_calls: int = 0
    figure_seconds: float | None = None
    figure_comments: int = 0

    @property
    def sentences_v1(self) -> int:
        return sum(self.v1_sentences.values())

    @property
    def sentences_v2(self) -> int:
        return sum(self.v2_sentences.values())


def _avg(values: list[float | None]) -> float | None:
    got = [v for v in values if v is not None]
    return round(sum(got) / len(got), 1) if got else None


@dataclass
class EvalResult:
    label: str
    pipeline: dict[str, Any]
    ideas: list[EvalIdea]
    total_seconds: float
    started_at: str
    model: str | None = None
    review_model: str | None = None
    max_rss_mb: float | None = None
    reranker: dict[str, float | int] = field(default_factory=dict)

    @property
    def gemini_calls(self) -> int:
        """작성(Argon·대체) + 검토 호출. 그림 이미지 호출은 figure_calls 로 따로."""
        return sum(i.gemini_calls + max(i.compose_calls, i.fallback_calls) for i in self.ideas)

    def totals(self) -> dict[str, float | int]:
        n = len(self.ideas) or 1
        coverage = [i.checklist_coverage for i in self.ideas if i.checklist_coverage is not None]
        scored = [i for i in self.ideas if i.scores]
        return {
            "ideas": len(self.ideas),
            "v1_alerts": sum(i.v1_alerts for i in self.ideas),
            "v2_alerts": sum(i.v2_alerts or 0 for i in self.ideas),
            "sentences_v1": sum(i.sentences_v1 for i in self.ideas),
            "sentences_v2": sum(i.sentences_v2 for i in self.ideas),
            "style_fixed": sum(i.style_fixed for i in self.ideas),
            "style_warnings": sum(i.style_warnings for i in self.ideas),
            "cited_ids": sum(i.cited_ids for i in self.ideas),
            "paper_citations": sum(i.paper_citations for i in self.ideas),
            "irrelevant_citations": sum(i.irrelevant_citations for i in self.ideas),
            "applied": sum(i.applied for i in self.ideas),
            "additions_applied": sum(i.additions_applied for i in self.ideas),
            "checklist_coverage": round(sum(coverage) / len(coverage), 3) if coverage else None,
            "score_sum": sum(sum(i.scores.values()) for i in scored),
            "score_avg": round(
                sum(sum(i.scores.values()) for i in scored)
                / max(1, sum(len(i.scores) for i in scored)),
                2,
            )
            if scored
            else None,
            "precheck_hits": sum(1 for i in self.ideas if i.precheck_hit),
            "precheck_known": sum(1 for i in self.ideas if i.precheck_hit is not None),
            "seconds_avg": round(sum(i.seconds for i in self.ideas) / n, 1),
            "gemini_calls": self.gemini_calls,
            "dropped_sentences": sum(i.dropped_sentences for i in self.ideas),
            "invalid": sum(1 for i in self.ideas if i.status == "invalid"),
            "failed_sections": sum(len(i.failed_sections) for i in self.ideas),
            "fallback_sections": sum(len(i.fallback_sections) for i in self.ideas),
            "local_sections": sum(len(i.local_sections) for i in self.ideas),
            "compose_calls": sum(i.compose_calls for i in self.ideas),
            # [G] 그림 — 성공률 = Nano Banana 채택 / 만든 그림, 추가 시간 = 그림 단계 평균
            "figures_total": sum(i.figures_total for i in self.ideas),
            "figures_nano": sum(i.figures_nano for i in self.ideas),
            "figures_baseline": sum(i.figures_baseline for i in self.ideas),
            "figures_skipped": sum(i.figures_skipped for i in self.ideas),
            "figure_calls": sum(i.figure_calls for i in self.ideas),
            "figure_seconds_avg": _avg([i.figure_seconds for i in self.ideas]),
            "figure_comments": sum(i.figure_comments for i in self.ideas),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k != "ideas"},
            "ideas": [
                {**asdict(i), "sentences_v1": i.sentences_v1, "sentences_v2": i.sentences_v2}
                for i in self.ideas
            ],
            "gemini_calls": self.gemini_calls,
            "totals": self.totals(),
        }


def _seconds_between(a: str | None, b: str | None) -> float | None:
    from datetime import datetime

    if not a or not b:
        return None
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except ValueError:
        return None


class EvaluateQuality:
    """RunManager(실제 조립 또는 가짜)로 골든셋을 돌려 EvalResult 를 만든다."""

    def __init__(
        self,
        manager: Any,
        precheck: Any,
        *,
        label: str,
        pipeline: Mapping[str, Any],
        user: str = "local",
        model: str | None = None,
        review_model: str | None = None,
        rss_sampler: Callable[[], float | None] | None = None,
        reranker: Any | None = None,
        keywords: KeywordRule | None = None,
        clock: Callable[[], float] = time.perf_counter,
        expected: Mapping[str, list[str]] | None = None,
    ):
        self.manager, self.precheck, self.label = manager, precheck, label
        self.pipeline = dict(pipeline)
        self.user, self.model, self.review_model = user, model, review_model
        self.rss_sampler, self.reranker = rss_sampler, reranker
        self.keywords = keywords or KeywordRule()
        self._clock = clock
        self.expected = {k: list(v) for k, v in (expected or {}).items()}

    async def __call__(self, ideas: list[tuple[str, ProposalRequest]]) -> EvalResult:
        started = self._clock()
        out: list[EvalIdea] = []
        rss: list[float] = []
        for name, req in ideas:
            out.append(await self.one(name, req))
            if self.rss_sampler is not None:
                sample = self.rss_sampler()
                if sample is not None:
                    rss.append(sample)
        return EvalResult(
            label=self.label,
            pipeline=self.pipeline,
            ideas=out,
            total_seconds=round(self._clock() - started, 1),
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            model=self.model,
            review_model=self.review_model,
            max_rss_mb=max(rss) if rss else None,
            reranker=rerank_stats(self.reranker) if self.reranker is not None else {},
        )

    async def one(self, name: str, req: ProposalRequest) -> EvalIdea:
        alerts = await self.precheck(req)
        top = [a.doc_id for a in alerts[:5]]
        expected = self.expected.get(name)
        hit: bool | None = None
        if expected is not None:  # 정답이 비면 "차단 알림이 없어야" 적중, 있으면 상위 5 안에 하나
            blocking = [a for a in alerts if a.blocking]
            hit = (not blocking) if not expected else any(d in top for d in expected)
        if expected is not None and hasattr(self.manager.generate, "exemplar_exclude"):
            # [4] 정답 유사과제는 Q4 본보기에서 뺀다 (정답을 베끼는 것을 막는다)
            self.manager.generate.exemplar_exclude = frozenset(expected)
        t0 = self._clock()
        state = await self.manager.submit(self.user, req)
        state = await self.manager.wait(self.user, state.run_id)
        seconds = round(self._clock() - t0, 1)
        rid = state.run_id
        store = self.manager.store
        idea = EvalIdea(
            name=name,
            run_id=rid,
            status=state.status,
            seconds=seconds,
            precheck_alerts=len(alerts),
            precheck_blocking=sum(1 for a in alerts if a.blocking),
            precheck_top=top,
            precheck_hit=hit,
        )
        for step in state.steps:
            dt = _seconds_between(step.started_at, step.finished_at)
            if dt is not None:
                idea.step_seconds[step.name] = dt
            if step.name.startswith("section:"):
                idea.dropped_sentences += step.dropped
            if step.name == "finalize":
                idea.style_fixed = step.dropped
            if step.name == "outline" and step.status == "done":
                idea.outline_sections = step.sentences
            if step.name == "figures":
                idea.figure_seconds = dt
                idea.figures_skipped = step.dropped
        idea.style_warnings = sum(1 for p in state.problems if p.get("code") in STYLE_CODES)
        idea.failed_sections = [f.key for f in getattr(state, "failed_sections", [])]
        idea.fallback_sections = [
            str(x.get("key", "")) for x in getattr(state, "fallback_sections", [])
        ]
        idea.fallback_calls = sum(
            int(x.get("calls", 0) or 0) for x in getattr(state, "fallback_sections", [])
        )
        writers = dict(getattr(state, "writers", None) or {})
        idea.writer = str(getattr(state, "writer", "local") or "local")
        idea.local_sections = local_sections(writers, state.section_keys)
        local_check = getattr(state, "local_check", None)
        if local_check:
            idea.local_check_mismatches = int(local_check.get("mismatches") or 0)
        snapshot = store.load_snapshot(self.user, rid)
        if snapshot is not None:
            idea.exemplars = len(snapshot.exemplars)
            idea.section_search = bool(snapshot.section_chunks)
        v1 = store.load_version(self.user, rid, 1)
        if v1 is not None:
            figs = list(getattr(v1, "figures", []) or [])
            idea.figures_total = len(figs)
            idea.figures_nano = sum(1 for f in figs if f.renderer == "nano_banana")
            idea.figures_baseline = sum(1 for f in figs if f.renderer == "baseline")
            idea.figure_calls = sum(f.calls for f in figs)
            idea.v1_alerts = v1.alerts
            idea.v1_sentences = {s.key: len(s.sentences) for s in v1.sections}
            self._citations(idea, v1, snapshot, req)
        v2 = store.load_version(self.user, rid, 2)
        if v2 is not None:
            idea.v2_alerts = v2.alerts
            idea.v2_sentences = {s.key: len(s.sentences) for s in v2.sections}
        review = (
            store.load_review(self.user, rid, 1) if store.list_reviews(self.user, rid) else None
        )
        if review is not None:
            idea.review_status = review.status
            idea.gemini_calls = review.transfer.calls
            idea.scores = {s.criterion: s.score for s in review.scores}
            idea.applied = len(review.applied_ids)
            additions = [c for c in review.comments if c.kind == "addition"]
            idea.additions = len(additions)
            idea.additions_applied = sum(1 for c in additions if c.id in review.applied_ids)
            idea.checklist_coverage = review.checklist_coverage
            idea.candidates = {k: v.get("choice", "") for k, v in review.candidate_choices.items()}
            idea.figure_comments = sum(1 for c in review.comments if c.kind == "figure")
        reviews = [
            r
            for n in store.list_reviews(self.user, rid)
            if (r := store.load_review(self.user, rid, n)) is not None
        ]
        idea.gemini_by_stage = gemini_calls(
            writers,
            getattr(state, "fallback_sections", []) or [],
            [r.transfer.calls for r in reviews],
            getattr(state, "figures", []) or [],
        )
        idea.compose_calls = idea.gemini_by_stage["compose"]
        return idea

    def _citations(self, idea: EvalIdea, version: Any, snapshot: Any, req: ProposalRequest) -> None:
        texts = {c.chunk_id: c.text for c in snapshot.chunks} if snapshot else {}
        query = req.search_text()
        cited: set[str] = set()
        for sec in version.sections:
            for s in sec.sentences:
                for e in s.evidence:
                    cited.add(e)
                    text = texts.get(e)
                    if (
                        text
                        and has_hangul(text)
                        and not keyword_overlap(query, text, self.keywords)
                    ):
                        idea.irrelevant_citations += 1
        idea.cited_ids = len(cited)
        idea.paper_citations = sum(1 for e in cited if e.startswith("openalex:"))
