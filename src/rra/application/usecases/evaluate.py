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

[5] 통합 측정(2026-10-28, ADR 0032 뒤):
- 시간: ② precheck(precheck_seconds), 제출 → 생성 완료(draft_seconds — 실행 작업이 끝난 때, 그림
  포함·1차 검토 제외), 전체(seconds). final_review=True 면 ⑤ 최종 검토(기준별 점수·평균·시간),
  finalize=True 면 ⑥ 마무리(선택형은 제안값, 제안부서만 렌더 인자) 뒤 HWPX 검증(hwpx_ok)·
  그림 배치 수.
- 품질: 유효(valid), 빈 초안(필수 섹션 문장 0), 수치 알림(unsupported_number), 근거 불일치(검토
  support "불일치" + local_evidence_mismatch), local_check 불일치·건너뜀. 측정 끝의 상태로 센다.
- 실시간 검색(레인 C — 필드가 없으면 0·None): 인용 문서 중 실시간(live) 비율, 자료원별 {status,
  count, seconds} → 합계에서 자료원별 평균 응답 시간·실패율.
- concurrent=N: N건씩 묶어 precheck 는 차례로, 제출은 한꺼번에(같은 RunManager — runs.max_concurrent
  를 그대로 따른다) 하고 모두 기다린다. 묶음 벽시계(batches)와 건별 draft_seconds 를 남긴다.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from rra.application.ports.reranker import rerank_stats
from rra.domain.models import ProposalRequest
from rra.domain.models.proposer import ProposerInfo
from rra.domain.models.review import SUPPORT_MISMATCH
from rra.domain.rules.keywords import KeywordRule, keyword_overlap
from rra.domain.rules.lint import STYLE_CODES, UNSUPPORTED_NUMBER
from rra.domain.rules.relevance import has_hangul
from rra.domain.rules.writer import LOCAL_EVIDENCE_MISMATCH, gemini_calls, local_sections

NUMBER_CODES = (
    UNSUPPORTED_NUMBER,
)  # 수치 알림 — 입력·인용 근거에 없는 수치 (domain/rules/numbers)
VALID_STATUSES = ("drafted", "editing", "final_reviewing", "final_reviewed", "finalized")
DEFAULT_DEPARTMENT = "철도연구원"  # ⑥ 마무리 측정의 제안부서 (렌더 인자로만, 저장 안 함)


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
    figures_planned: int = 0  # 만든 그림 + 건너뛴 그림 (성공률 분모)
    # [5] 통합 측정 — 시간(초): ② precheck, 제출 → 생성 완료(그림 포함, 1차 검토 제외)
    precheck_seconds: float | None = None
    draft_seconds: float | None = None
    batch: int | None = None  # concurrent 모드의 묶음 번호 (0부터)
    final_status: str | None = None  # 측정이 끝났을 때의 run 상태
    # ⑤ 최종 검토 (final_review=True): 상태(done|failed|skipped|error:<예외>)·기준별 점수·평균·시간
    final_review_status: str | None = None
    final_scores: dict[str, int] = field(default_factory=dict)
    final_score_avg: float | None = None
    final_review_seconds: float | None = None
    # ⑥ 마무리 (finalize=True): 성공 여부·HWPX 크기·검증(zip·섹션 XML)·그림 배치 수·거부(예외 이름)
    finalized: bool | None = None
    hwpx_bytes: int = 0
    hwpx_ok: bool | None = None
    figure_placements: int | None = None
    finalize_error: str | None = None
    # 품질 — 유효, 빈 초안(필수 섹션 문장 0), 수치 알림, 근거 불일치(검토 support·로컬 대조)
    valid: bool = False
    empty_draft: bool = False
    empty_required_sections: list[str] = field(default_factory=list)
    number_alerts: int = 0
    review_mismatch: int = 0
    local_evidence_mismatch: int = 0
    local_check_skipped: int | None = None
    # 실시간 검색(레인 C) — 인용 문서 중 실시간 수 / 인용 문서 수, 자료원별 {status, count, seconds}
    live_cited: int = 0
    cited_docs: int = 0
    live_status: str | None = None
    live_sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def sentences_v1(self) -> int:
        return sum(self.v1_sentences.values())

    @property
    def sentences_v2(self) -> int:
        return sum(self.v2_sentences.values())


def _avg(values: Iterable[float | None]) -> float | None:
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
    # [5] 측정 구성(작성자·local_check·그림·동시 칸 수·최종 검토·마무리)과 실행 방식
    config: dict[str, Any] = field(default_factory=dict)
    mode: str = "sequential"  # sequential | concurrent
    concurrent: int = 1
    batches: list[dict[str, Any]] = field(default_factory=list)  # {ideas, draft_seconds, seconds}

    @property
    def gemini_calls(self) -> int:
        """작성(Argon·대체) + 검토 호출. 그림 이미지 호출은 figure_calls 로 따로."""
        return sum(i.gemini_calls + max(i.compose_calls, i.fallback_calls) for i in self.ideas)

    def totals(self) -> dict[str, Any]:
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
            "figure_seconds_avg": _avg(i.figure_seconds for i in self.ideas),
            "figure_comments": sum(i.figure_comments for i in self.ideas),
            **self._integrated_totals(),
        }

    def _integrated_totals(self) -> dict[str, Any]:
        """[5] 통합 측정 합계 — 비교표(views.eval_markdown "통합 비교")가 쓴다."""
        ideas = self.ideas
        valid = sum(1 for i in ideas if i.valid)
        finals = [i for i in ideas if i.final_scores]
        criteria: dict[str, list[int]] = {}
        for i in finals:
            for k, v in i.final_scores.items():
                criteria.setdefault(k, []).append(v)
        planned = sum(i.figures_planned for i in ideas)
        live_cited = sum(i.live_cited for i in ideas)
        cited_docs = sum(i.cited_docs for i in ideas)
        stage = {
            k: sum(int(i.gemini_by_stage.get(k, 0)) for i in ideas)
            for k in ("compose", "review", "figures", "total")
        }
        tried = [i for i in ideas if i.finalized is not None]
        return {
            "precheck_seconds_avg": _avg(i.precheck_seconds for i in ideas),
            "draft_seconds_avg": _avg(i.draft_seconds for i in ideas),
            "final_review_seconds_avg": _avg(i.final_review_seconds for i in ideas),
            "valid": valid,
            "valid_rate": round(valid / len(ideas), 3) if ideas else None,
            "empty_drafts": sum(1 for i in ideas if i.empty_draft),
            "final_reviewed": len(finals),
            "final_score_avg": round(
                sum(sum(i.final_scores.values()) for i in finals)
                / max(1, sum(len(i.final_scores) for i in finals)),
                2,
            )
            if finals
            else None,
            "final_scores_avg": {k: round(sum(v) / len(v), 2) for k, v in criteria.items()},
            "number_alerts": sum(i.number_alerts for i in ideas),
            "review_mismatch": sum(i.review_mismatch for i in ideas),
            "local_evidence_mismatch": sum(i.local_evidence_mismatch for i in ideas),
            "local_check_mismatches": sum(i.local_check_mismatches or 0 for i in ideas),
            "local_check_skipped": sum(i.local_check_skipped or 0 for i in ideas),
            "live_cited": live_cited,
            "cited_docs": cited_docs,
            "live_share": round(live_cited / cited_docs, 3) if cited_docs else None,
            "live_sources": source_stats(i.live_sources for i in ideas),
            "figures_planned": planned,
            "figures_success_rate": round(sum(i.figures_nano for i in ideas) / planned, 3)
            if planned
            else None,
            "gemini_compose": stage["compose"],
            "gemini_review": stage["review"],
            "gemini_figures": stage["figures"],
            "gemini_total": stage["total"],
            "finalize_tried": len(tried),
            "finalized": sum(1 for i in tried if i.finalized),
            "hwpx_ok": sum(1 for i in tried if i.hwpx_ok),
            "figure_placements": sum(i.figure_placements or 0 for i in ideas),
            "batch_draft_seconds_avg": _avg(b.get("draft_seconds") for b in self.batches),
            "batch_seconds_avg": _avg(b.get("seconds") for b in self.batches),
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


def source_stats(per_idea: Iterable[Mapping[str, Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    """실시간 검색 자료원별 합계 — {source: {runs, failures, failure_rate, seconds_avg, count_sum}}.

    per_idea: 아이디어마다 {source: {status, count, seconds}}. status 가 ok 가 아니면 실패로 센다
    (skipped·timeout·error·IP 거부 등 — 그 자료원이 결과를 주지 못했다)."""
    acc: dict[str, dict[str, Any]] = {}
    for sources in per_idea:
        for name, row in (sources or {}).items():
            a = acc.setdefault(name, {"runs": 0, "failures": 0, "seconds": [], "count_sum": 0})
            a["runs"] += 1
            if str(row.get("status") or "") != "ok":
                a["failures"] += 1
            if row.get("seconds") is not None:
                a["seconds"].append(float(row["seconds"]))
            a["count_sum"] += int(row.get("count") or 0)
    return {
        name: {
            "runs": a["runs"],
            "failures": a["failures"],
            "failure_rate": round(a["failures"] / a["runs"], 3),
            "seconds_avg": round(sum(a["seconds"]) / len(a["seconds"]), 2)
            if a["seconds"]
            else None,
            "count_sum": a["count_sum"],
        }
        for name, a in sorted(acc.items())
    }


def live_sources(live_search: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """RunState.live_search(레인 C) → {source: {status, count, seconds}}. 없으면 빈 dict."""
    out: dict[str, dict[str, Any]] = {}
    for row in (live_search or {}).get("sources") or []:
        if not isinstance(row, Mapping) or not row.get("source"):
            continue
        seconds = row.get("seconds")
        out[str(row["source"])] = {
            "status": row.get("status"),
            "count": int(row.get("count") or 0),
            "seconds": float(seconds) if seconds is not None else None,
        }
    return out


async def live_citations(
    citations: Iterable[Any], get_document: Callable[[str], Awaitable[Any]]
) -> tuple[int, int]:
    """인용 문서 중 실시간 검색 결과 수와 인용 문서 수 — (live_cited, total_cited).

    문서 단위로 센다(한 문서의 여러 청크를 인용해도 1). 인용(citation)에 live 표시가 있으면 그것을,
    없으면 저장소 문서의 raw["live"] 를 본다 (레인 C 이전 run 은 모두 0)."""
    flags: dict[str, bool] = {}
    for c in citations:
        doc_id = str(getattr(c, "doc_id", "") or "")
        if not doc_id:
            continue
        live = getattr(c, "live", None) is True
        if not live and doc_id not in flags:
            doc = await get_document(doc_id)
            live = doc is not None and (getattr(doc, "raw", None) or {}).get("live") is True
        flags[doc_id] = flags.get(doc_id, False) or live
    return sum(flags.values()), len(flags)


def _seconds_between(a: str | None, b: str | None) -> float | None:
    from datetime import datetime

    if not a or not b:
        return None
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except ValueError:
        return None


@dataclass
class _Pending:
    """제출한 아이디어 — precheck 결과와 제출 시각."""

    name: str
    req: ProposalRequest
    run_id: str
    t0: float
    precheck: dict[str, Any]


class EvaluateQuality:
    """RunManager(실제 조립 또는 가짜)로 골든셋을 돌려 EvalResult 를 만든다.

    final_review: 생성 뒤 ⑤ 최종 검토까지. finalize: 그 뒤 ⑥ 마무리(선택형은 제안값, 제안부서
    department) — verify_hwpx(bytes → bool) 가 있으면 HWPX zip·섹션 XML 검증 결과를 남긴다.
    concurrent: N(>1)이면 N건씩 한꺼번에 제출한다."""

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
        final_review: bool = False,
        finalize: bool = False,
        department: str = DEFAULT_DEPARTMENT,
        verify_hwpx: Callable[[bytes], bool] | None = None,
        concurrent: int = 1,
        config: Mapping[str, Any] | None = None,
    ):
        self.manager, self.precheck, self.label = manager, precheck, label
        self.pipeline = dict(pipeline)
        self.user, self.model, self.review_model = user, model, review_model
        self.rss_sampler, self.reranker = rss_sampler, reranker
        self.keywords = keywords or KeywordRule()
        self._clock = clock
        self.expected = {k: list(v) for k, v in (expected or {}).items()}
        self.final_review, self.finalize = final_review, finalize
        self.department, self.verify_hwpx = department, verify_hwpx
        self.concurrent = max(1, int(concurrent))
        self.config = dict(config or {})

    def _config(self) -> dict[str, Any]:
        gen = self.manager.generate
        return {
            "writer": getattr(gen, "writer", None),
            "local_check": getattr(gen, "local_check", None),
            "figures": getattr(self.manager, "figures", None) is not None,
            "first_pass": getattr(self.manager, "first_pass", None),
            "final_review": self.final_review,
            "finalize": self.finalize,
            "concurrent": self.concurrent,
            **self.config,
        }

    async def __call__(self, ideas: list[tuple[str, ProposalRequest]]) -> EvalResult:
        started = self._clock()
        out: list[EvalIdea] = []
        rss: list[float] = []
        batches: list[dict[str, Any]] = []
        size = self.concurrent
        for b, start in enumerate(range(0, len(ideas), size)):
            group = ideas[start : start + size]
            if size == 1:
                out.append(await self.one(*group[0]))
            else:
                done, record = await self._batch(group, b)
                out.extend(done)
                batches.append(record)
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
            config=self._config(),
            mode="concurrent" if size > 1 else "sequential",
            concurrent=size,
            batches=batches,
        )

    async def one(self, name: str, req: ProposalRequest) -> EvalIdea:
        pre = await self._precheck(name, req)
        self._exclude(self.expected.get(name))
        pending = await self._submit(name, req, pre)
        return await self._complete(pending)

    async def _batch(
        self, group: list[tuple[str, ProposalRequest]], index: int
    ) -> tuple[list[EvalIdea], dict[str, Any]]:
        """N건 동시 — precheck 는 차례로(② 는 제출 전 단계), 제출은 한꺼번에, 모두 기다린다.

        본보기 제외(exemplar_exclude)는 유스케이스 한 곳의 값이라 묶음 정답의 합집합으로 둔다."""
        pres = [await self._precheck(name, req) for name, req in group]
        exclude = [d for name, _ in group for d in (self.expected.get(name) or [])]
        if any(name in self.expected for name, _ in group):
            self._exclude(exclude)
        t0 = self._clock()
        pending = [
            await self._submit(name, req, pre) for (name, req), pre in zip(group, pres, strict=True)
        ]
        drafted: list[float] = []

        async def finish(p: _Pending) -> EvalIdea:
            idea = await self._complete(p, on_drafted=drafted.append)
            idea.batch = index
            return idea

        done = list(await asyncio.gather(*(finish(p) for p in pending)))
        end = self._clock()
        return done, {
            "batch": index,
            "ideas": [name for name, _ in group],
            "draft_seconds": round(max(drafted) - t0, 1) if drafted else None,
            "seconds": round(end - t0, 1),
        }

    def _exclude(self, expected: list[str] | None) -> None:
        if expected is not None and hasattr(self.manager.generate, "exemplar_exclude"):
            # [4] 정답 유사과제는 Q4 본보기에서 뺀다 (정답을 베끼는 것을 막는다)
            self.manager.generate.exemplar_exclude = frozenset(expected)

    async def _precheck(self, name: str, req: ProposalRequest) -> dict[str, Any]:
        t = self._clock()
        alerts = await self.precheck(req)
        seconds = round(self._clock() - t, 2)
        top = [a.doc_id for a in alerts[:5]]
        expected = self.expected.get(name)
        hit: bool | None = None
        if expected is not None:  # 정답이 비면 "차단 알림이 없어야" 적중, 있으면 상위 5 안에 하나
            blocking = [a for a in alerts if a.blocking]
            hit = (not blocking) if not expected else any(d in top for d in expected)
        return {
            "precheck_alerts": len(alerts),
            "precheck_blocking": sum(1 for a in alerts if a.blocking),
            "precheck_top": top,
            "precheck_hit": hit,
            "precheck_seconds": seconds,
        }

    async def _submit(self, name: str, req: ProposalRequest, pre: dict[str, Any]) -> _Pending:
        t0 = self._clock()
        state = await self.manager.submit(self.user, req)
        return _Pending(name=name, req=req, run_id=state.run_id, t0=t0, precheck=pre)

    async def _await_draft(self, run_id: str) -> None:
        """생성 실행 작업이 끝날 때까지 — 자동 1차 검토는 따로 도는 작업이라 기다리지 않는다."""
        runner = self.manager.runner
        if runner.is_running(run_id):
            await runner.wait(run_id)

    async def _complete(
        self, p: _Pending, *, on_drafted: Callable[[float], None] | None = None
    ) -> EvalIdea:
        rid = p.run_id
        await self._await_draft(rid)
        drafted_at = self._clock()
        if on_drafted is not None:
            on_drafted(drafted_at)
        state = await self.manager.wait(self.user, rid)
        seconds = round(self._clock() - p.t0, 1)
        idea = EvalIdea(
            name=p.name,
            run_id=rid,
            status=state.status,
            seconds=seconds,
            draft_seconds=round(drafted_at - p.t0, 1),
            **p.precheck,
        )
        idea.valid = state.status in VALID_STATUSES
        self._draft_metrics(idea, state, p.req)
        if self.final_review and idea.valid:
            await self._final_review(idea)
        if self.finalize and idea.valid:
            await self._finalize(idea)
        state = await self.manager.status(self.user, rid)
        idea.final_status = state.status
        await self._quality(idea, state)
        return idea

    def _draft_metrics(self, idea: EvalIdea, state: Any, req: ProposalRequest) -> None:
        """생성·1차 검토 지표 (예전 측정과 같은 항목)."""
        rid = idea.run_id
        store = self.manager.store
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
        idea.figures_planned = idea.figures_total + idea.figures_skipped
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

    async def _final_review(self, idea: EvalIdea) -> None:
        """⑤ 최종 검토 1회 — 시간·상태·기준별 점수. 거부·예산 소진은 예외 이름만 남긴다."""
        t = self._clock()
        try:
            await self.manager.final_review(self.user, idea.run_id)
            await self.manager.wait(self.user, idea.run_id)
        except Exception as exc:  # 측정은 계속 — 어느 단계에서 막혔는지만 남긴다
            idea.final_review_status = f"error:{type(exc).__name__}"
            idea.final_review_seconds = round(self._clock() - t, 1)
            return
        idea.final_review_seconds = round(self._clock() - t, 1)
        final = self._last_review(idea.run_id, kind="final")
        if final is None:
            idea.final_review_status = "missing"
            return
        idea.final_review_status = final.status
        idea.final_scores = {s.criterion: s.score for s in final.scores}
        if idea.final_scores:
            idea.final_score_avg = round(
                sum(idea.final_scores.values()) / len(idea.final_scores), 2
            )

    async def _finalize(self, idea: EvalIdea) -> None:
        """⑥ 마무리 — 선택형은 제안값, 제안부서만 렌더 인자(저장 안 함). HWPX 검증·그림 배치 수."""
        try:
            res = await self.manager.finalize(
                self.user, idea.run_id, proposer=ProposerInfo(department=self.department)
            )
        except Exception as exc:  # 거부(검토 전·임시 편집)·렌더 실패 — 예외 이름만
            idea.finalized, idea.hwpx_ok = False, False
            idea.finalize_error = type(exc).__name__
            return
        data = res.data or b""
        idea.finalized = True
        idea.hwpx_bytes = len(data)
        idea.hwpx_ok = bool(data) and (self.verify_hwpx is None or bool(self.verify_hwpx(data)))
        idea.figure_placements = sum(1 for f in res.state.figures if f.get("placement"))

    def _last_review(self, run_id: str, *, kind: str | None = None) -> Any:
        store = self.manager.store
        for n in reversed(store.list_reviews(self.user, run_id)):
            r = store.load_review(self.user, run_id, n)
            if r is not None and (kind is None or r.kind == kind):
                return r
        return None

    async def _quality(self, idea: EvalIdea, state: Any) -> None:
        """측정이 끝난 상태(최신 버전·알림·검토·실시간 검색)로 품질 지표를 센다."""
        rid = idea.run_id
        store = self.manager.store
        problems = list(state.problems or [])
        idea.number_alerts = sum(1 for p in problems if p.get("code") in NUMBER_CODES)
        idea.local_evidence_mismatch = sum(
            1 for p in problems if p.get("code") == LOCAL_EVIDENCE_MISMATCH
        )
        local_check = getattr(state, "local_check", None)
        if local_check:
            idea.local_check_mismatches = int(local_check.get("mismatches") or 0)
            idea.local_check_skipped = len(local_check.get("skipped_sections") or [])
        latest = (
            store.load_version(self.user, rid, state.draft_version) if state.draft_version else None
        )
        required = list(getattr(self.manager.generate.rules, "required_sections", []) or [])
        counts = {s.key: len(s.sentences) for s in latest.sections} if latest else {}
        idea.empty_required_sections = [k for k in required if not counts.get(k)]
        idea.empty_draft = latest is None or (
            bool(required) and len(idea.empty_required_sections) == len(required)
        )
        reviews = [
            r
            for n in store.list_reviews(self.user, rid)
            if (r := store.load_review(self.user, rid, n)) is not None
        ]
        last = next((r for r in reversed(reviews) if r.support), None)
        if last is not None:
            idea.review_mismatch = sum(1 for v in last.support.values() if v == SUPPORT_MISMATCH)
        idea.gemini_by_stage = gemini_calls(
            dict(getattr(state, "writers", None) or {}),
            getattr(state, "fallback_sections", []) or [],
            [r.transfer.calls for r in reviews],
            getattr(state, "figures", []) or [],
        )
        idea.compose_calls = idea.gemini_by_stage["compose"]
        live = getattr(state, "live_search", None)
        if isinstance(live, Mapping):
            idea.live_status = str(live.get("status")) if live.get("status") else None
            idea.live_sources = live_sources(live)
        if latest is not None:
            try:
                view = await self.manager.get_draft(self.user, rid)
            except Exception:  # 조회 실패는 실시간 비율만 비운다
                return
            idea.live_cited, idea.cited_docs = await live_citations(
                view.citations, self.manager.generate.repo.get_document
            )

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
