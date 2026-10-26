"""로컬 작성 모델 비교 벤치 (`rra llm-bench`) — 골든셋 아이디어마다 12개 섹션을 생성해 지표를 모음.

지표(모델 하나, 아이디어 3건 합계):
- JSON 형식 성공률(파싱 ok 섹션 / LLM 호출 섹션)·프롬프트 폴백 횟수
- 근거 대조 폐기 문장 수, 수치 알림 수(unsupported_number), 외국 문자 알림 수(foreign_script),
  정책명 규칙 위반 수(grounding 폐기)
- 섹션당 평균 시간·전체 시간, 최대 메모리(서버 RSS, 어댑터가 샘플링)
- 관련도 하한(이슈 #2): 근거로 남은 청크 수·하한 탈락 청크 수·인용된 근거 id 수·
  근거가 없어 빈칸이 된 섹션(no_relevant_evidence)
- 최대 문맥 길이와 실제 최대 프롬프트 토큰(usage.prompt_tokens)
기술적 중요도 문장은 모델별 비교용으로 3건 담는다.

RunManager 를 거치지 않고 GenerateProposal 을 직접 돈다 (run 폴더를 만들지 않는다). LLM 통계는
어댑터의 집계 속성(calls·fallbacks·max_prompt_tokens)에서 읽고, 없으면 0.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import ProposalRequest
from rra.domain.rules.lint import FOREIGN_SCRIPT, NO_RELEVANT_EVIDENCE, UNSUPPORTED_NUMBER

TECH_SECTION = "tech_importance"


@dataclass
class IdeaResult:
    name: str
    title: str
    seconds: float
    sections_llm: int
    parse_ok: int  # (b) 관용 처리·폴백 포함 최종 성공
    parse_ok_strict: int  # (a) 지시한 모양 그대로 응답한 섹션
    parse_failed: list[str]  # "섹션:사유"
    dropped: int
    ungrounded: int
    unsupported_numbers: int
    foreign_script: int
    problems: int
    overlap_alerts: int
    tech_sentences: list[str]
    section_seconds: dict[str, float] = field(default_factory=dict)
    parse_lenient: list[str] = field(default_factory=list)  # 관용 처리로 살린 섹션
    retries: int = 0  # 형식 교정 재요청 횟수
    parse_retried_ok: list[str] = field(default_factory=list)  # 재요청으로 살린 섹션
    evidence_chunks: int = 0  # 관련도 하한을 넘어 근거로 남은 청크 수 (유사과제 보탬 포함)
    dropped_chunks: int = 0  # 관련도 하한 탈락 청크 수
    empty_sections: list[str] = field(default_factory=list)  # 근거 없어 빈칸 (no_relevant_evidence)
    cited_chunks: int = 0  # 초안 문장이 실제 인용한 서로 다른 근거 id 수


@dataclass
class BenchResult:
    label: str
    model: str | None
    profile: str | None
    context_length: int | None
    ideas: list[IdeaResult]
    total_seconds: float
    llm_calls: int
    fallbacks: int
    max_prompt_tokens: int
    max_completion_tokens: int
    max_rss_mb: float | None
    started_at: str

    @property
    def sections_llm(self) -> int:
        return sum(i.sections_llm for i in self.ideas)

    @property
    def parse_ok(self) -> int:
        return sum(i.parse_ok for i in self.ideas)

    @property
    def parse_ok_strict(self) -> int:
        return sum(i.parse_ok_strict for i in self.ideas)

    @property
    def strict_success_rate(self) -> float:
        return self.parse_ok_strict / self.sections_llm if self.sections_llm else 0.0

    @property
    def json_success_rate(self) -> float:
        return self.parse_ok / self.sections_llm if self.sections_llm else 0.0

    @property
    def avg_section_seconds(self) -> float:
        n = sum(len(i.section_seconds) for i in self.ideas)
        return sum(sum(i.section_seconds.values()) for i in self.ideas) / n if n else 0.0

    @property
    def retries(self) -> int:
        return sum(i.retries for i in self.ideas)

    def totals(self) -> dict[str, int]:
        keys = (
            "dropped",
            "ungrounded",
            "unsupported_numbers",
            "foreign_script",
            "problems",
            "overlap_alerts",
            "retries",
            "evidence_chunks",
            "dropped_chunks",
            "cited_chunks",
        )
        out = {k: sum(getattr(i, k) for i in self.ideas) for k in keys}
        out["empty_sections"] = sum(len(i.empty_sections) for i in self.ideas)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k != "ideas"},
            "ideas": [asdict(i) for i in self.ideas],
            "sections_llm": self.sections_llm,
            "parse_ok": self.parse_ok,
            "parse_ok_strict": self.parse_ok_strict,
            "retries": self.retries,
            "json_success_rate": round(self.json_success_rate, 4),
            "strict_success_rate": round(self.strict_success_rate, 4),
            "avg_section_seconds": round(self.avg_section_seconds, 2),
            "totals": self.totals(),
        }


class BenchGenerate:
    def __init__(
        self,
        generate: GenerateProposal,
        *,
        label: str,
        model: str | None = None,
        profile: str | None = None,
        context_length: int | None = None,
        rss_sampler: Callable[[], float | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], str] | None = None,
    ):
        self.generate = generate
        self.label = label
        self.model = model
        self.profile = profile
        self.context_length = context_length
        self.rss_sampler = rss_sampler
        self.clock = clock
        self.now = now or (lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    async def __call__(self, ideas: list[tuple[str, ProposalRequest]]) -> BenchResult:
        started = self.now()
        t0 = self.clock()
        results: list[IdeaResult] = []
        max_rss: float | None = None
        for name, req in ideas:
            results.append(await self._idea(name, req))
            if self.rss_sampler is not None:
                sampled = self.rss_sampler()
                if sampled is not None:
                    max_rss = max(max_rss or 0.0, sampled)
        llm = self.generate.llm
        calls = getattr(llm, "calls", 0)  # 어댑터는 정수, fake 는 프롬프트 목록
        return BenchResult(
            label=self.label,
            model=self.model,
            profile=self.profile,
            context_length=self.context_length,
            ideas=results,
            total_seconds=round(self.clock() - t0, 1),
            llm_calls=len(calls) if isinstance(calls, list | tuple) else int(calls or 0),
            fallbacks=int(getattr(llm, "fallbacks", 0) or 0),
            max_prompt_tokens=int(getattr(llm, "max_prompt_tokens", 0) or 0),
            max_completion_tokens=int(getattr(llm, "max_completion_tokens", 0) or 0),
            max_rss_mb=max_rss,
            started_at=started,
        )

    async def _idea(self, name: str, req: ProposalRequest) -> IdeaResult:
        t0 = self.clock()
        snapshot = await self.generate.retrieve(req)
        sections = []
        parse_ok = parse_ok_strict = sections_llm = dropped = ungrounded = retries = 0
        failed: list[str] = []
        lenient: list[str] = []
        retried_ok: list[str] = []
        timings: dict[str, float] = {}
        for key in self.generate.section_keys:
            s0 = self.clock()
            composed = await self.generate.compose_section(key, req, snapshot)
            timings[key] = round(self.clock() - s0, 2)
            sections.append(composed.section)
            dropped += len(composed.dropped)
            ungrounded += len(composed.ungrounded)
            if composed.parse is not None:
                sections_llm += 1
                retries += composed.retries
                first = composed.first_parse or composed.parse
                if first.strict_ok:
                    parse_ok_strict += 1  # (a) 첫 응답이 지시 모양 그대로
                if composed.parse.ok:
                    parse_ok += 1  # (b) 관용·재요청 포함 최종 성공
                    if composed.retries and not first.ok:
                        retried_ok.append(key)
                    elif composed.parse.lenient:
                        lenient.append(key)
                else:
                    failed.append(f"{key}:{composed.parse.status}")
        draft, problems = self.generate.finalize(f"bench-{name}", req, snapshot, sections)
        tech = draft.section(TECH_SECTION)
        title = draft.section("title")
        cited = {e for s in draft.sections for st in s.sentences for e in st.evidence}
        return IdeaResult(
            name=name,
            title=title.text if title else "",
            seconds=round(self.clock() - t0, 1),
            sections_llm=sections_llm,
            parse_ok=parse_ok,
            parse_ok_strict=parse_ok_strict,
            parse_failed=failed,
            parse_lenient=lenient,
            retries=retries,
            parse_retried_ok=retried_ok,
            dropped=dropped,
            ungrounded=ungrounded,
            unsupported_numbers=sum(1 for p in problems if p.code == UNSUPPORTED_NUMBER),
            foreign_script=sum(1 for p in problems if p.code == FOREIGN_SCRIPT),
            problems=len(problems),
            overlap_alerts=len(snapshot.overlap),
            tech_sentences=[s.text for s in tech.sentences[:3]] if tech else [],
            section_seconds=timings,
            evidence_chunks=len(snapshot.chunks),
            dropped_chunks=len(snapshot.dropped_chunks),
            empty_sections=[p.section for p in problems if p.code == NO_RELEVANT_EVIDENCE],
            cited_chunks=len(cited),
        )
