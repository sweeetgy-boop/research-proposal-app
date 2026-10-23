"""제안서 초안 생성. 재개 가능하도록 세 단계로 나뉜다.

    retrieve(req)                    → RetrievalSnapshot  (검색 1회 + 유사과제 판정, 결과를 고정)
    compose_section(key, req, snap)  → 섹션 1개 (LLM 최대 1회, 섹션 단위 근거 검증까지)
    finalize(run_id, req, snap, …)   → Draft + lint 문제

섹션 종류 (rules.yaml 이 정한다):
- 문장형: JSON 배열. 근거 필수(evidence_required)·금지(evidence_forbidden)·선택.
- 선택형(choices): {"choices", "sentences"} 객체. 선택지는 앱 목록 안에서만, 확정은 사용자가 한다.
- 입력 전용(requires_input): 근거가 될 입력이 비면 LLM 을 부르지 않고 빈칸으로 둔다 (lint 경고).
- 고유명 대조(input_grounded): 정책·계획명·차수·연도가 허용 출처에 없으면 문장을 폐기한다.
- 수치 대조(number_checked): 수치가 입력·인용 청크에 없으면 lint 경고만 (finalize, 폐기 없음).
- overlap_review: 유사과제 판정에서 중복 기준을 넘는 것이 없으면 앱이 확정 문장을 쓴다 (LLM 미사용).

상태 저장·재개·동시성은 application/services/run_manager.py 가 맡는다.
`__call__` 은 세 단계를 한 번에 도는 조합이다 (테스트·일회성 실행용).

보안 A: LLM 출력은 JSON 만 받고, 근거 id 는 이번 run 의 검색 집합(스냅샷)과 대조한다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Literal

from rra.application.ports import DocumentRepository, LLMPort, PromptLibraryPort
from rra.domain.models import (
    Chunk,
    Document,
    Draft,
    OverlapAlert,
    ProposalRequest,
    RetrievalSnapshot,
    Section,
    Sentence,
    StrategyCatalog,
)
from rra.domain.models.selection import (
    STRATEGY_SOURCE,
    TASK_TYPES,
    TASK_TYPES_SOURCE,
    UTILIZATION,
    UTILIZATION_SOURCE,
)
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.lint import LintProblem, LintRules, has_errors, lint, skipped_sections
from rra.domain.rules.llm_output import ParseResult, parse_choice_section, parse_sentences
from rra.domain.rules.overlap import OwnUnit, judge, no_overlap_statement, uncollected_sources
from rra.domain.rules.trust import enforce_section_evidence, wrap_untrusted

OVERLAP_SECTION = "overlap_review"
_OVERLAP_TEXT_CHARS = 1500

ComposeMode = Literal["llm", "skipped", "app"]


class DraftInvalid(Exception):
    def __init__(self, problems, dropped):
        super().__init__(f"{len(problems)} lint problems, {len(dropped)} sentences dropped")
        self.problems, self.dropped = problems, dropped


@dataclass(frozen=True)
class ComposedSection:
    section: Section
    dropped: list[str]
    # 시스템 프롬프트 + 섹션 지시문 해시 (입력·자료 미포함). LLM 미사용이면 None
    prompt_hash: str | None
    parse: ParseResult | None  # 파싱 사유·원본 길이. LLM 미사용이면 None
    mode: ComposeMode = "llm"  # skipped: 입력·목록이 비어 빈칸 / app: 앱 확정 문장


@dataclass
class GenerateProposal:
    llm: LLMPort
    repo: DocumentRepository
    prompts: PromptLibraryPort
    rules: LintRules
    section_keys: list[str]
    k: int = 20
    strategy: StrategyCatalog = field(default_factory=StrategyCatalog)
    # 유사과제 판정 (5. 특이사항). None 이면 판정하지 않는다 → overlap_review 도 LLM 이 쓴다
    own: OwnUnit | None = None
    check_overlap: bool = False
    overlap_k: int = 10
    keywords: KeywordRule | None = None  # 차단에 키워드 조건을 더한다 (None 이면 유사도만)

    @property
    def template(self) -> str | None:
        return self.rules.template

    def choice_options(self) -> dict[str, dict[str, str]]:
        """선택형 섹션 → {선택지 id: 표시 이름}. 전략 목록이 비면 빈 dict."""
        sources = {
            TASK_TYPES_SOURCE: TASK_TYPES,
            UTILIZATION_SOURCE: UTILIZATION,
            STRATEGY_SOURCE: self.strategy.options(),
        }
        return {key: dict(sources[spec.options]) for key, spec in self.rules.choices.items()}

    # ── retrieve ─────────────────────────────────────────
    async def retrieve(self, req: ProposalRequest) -> RetrievalSnapshot:
        query = req.search_text()
        chunks = list(await self.repo.hybrid_search([query], k=self.k))
        if not self.check_overlap:
            return RetrievalSnapshot.of(query, chunks)
        hits = await self.repo.find_similar(query, k=self.overlap_k)
        alerts = judge(hits, own=self.own, query=query, keywords=self.keywords)
        extra = self._overlap_chunks(hits, alerts, chunks)
        snapshot = RetrievalSnapshot.of(query, chunks + extra, alerts)
        snapshot.uncollected = uncollected_sources(await self.repo.count_by_source())
        return snapshot

    @staticmethod
    def _overlap_chunks(
        hits: list[tuple[Document, float]], alerts: list[OverlapAlert], chunks: list[Chunk]
    ) -> list[Chunk]:
        """중복 기준을 넘은 문서가 검색 청크에 없으면 제목·초록으로 청크 하나를 만든다 (비신뢰)."""
        have = {c.doc_id for c in chunks}
        blocking = {a.doc_id for a in alerts if a.blocking}
        out: list[Chunk] = []
        for doc, _ in hits:
            if doc.doc_id not in blocking or doc.doc_id in have:
                continue
            body = (doc.abstract or doc.body or "")[:_OVERLAP_TEXT_CHARS]
            out.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#overlap",
                    doc_id=doc.doc_id,
                    ordinal=0,
                    text=f"{doc.title}\n{body}".strip(),
                    basis=doc.text_basis,
                )
            )
            have.add(doc.doc_id)
        return out

    # ── compose ──────────────────────────────────────────
    async def compose_section(
        self, key: str, req: ProposalRequest, snapshot: RetrievalSnapshot
    ) -> ComposedSection:
        options = self.choice_options()
        if key in skipped_sections(req, self.rules, options):
            return ComposedSection(Section(key=key, sentences=[]), [], None, None, "skipped")
        if key == OVERLAP_SECTION and snapshot.overlap_checked:
            if not any(a.blocking for a in snapshot.overlap):
                texts = no_overlap_statement(snapshot.scope, snapshot.uncollected)
                sentences = [Sentence(text=t, origin="app") for t in texts]
                section = Section(key=key, sentences=sentences)
                return ComposedSection(section, [], None, None, "app")

        system = self.prompts.system()
        instruction = self.prompts.section(key)
        spec = self.rules.choices.get(key)
        prompt = self._prompt(key, instruction, req, snapshot, options.get(key) if spec else None)
        raw = await self.llm.complete(prompt, system=system, json_mode=True)
        if spec is not None:
            parsed = parse_choice_section(raw, options.get(key, {}), min_n=spec.min, max_n=spec.max)
        else:
            parsed = parse_sentences(raw)

        section, dropped = enforce_section_evidence(
            Section(key=key, sentences=parsed.sentences, choices=parsed.choices),
            snapshot.retrieved_ids,
            evidence_required=key in self.rules.evidence_required,
            evidence_forbidden=key in self.rules.evidence_forbidden,
        )
        section, lost = self._enforce_grounding(key, section, req)
        dropped.extend(lost)
        digest = hashlib.sha256(f"{system}\x1f{instruction}".encode()).hexdigest()[:16]
        return ComposedSection(section=section, dropped=dropped, prompt_hash=digest, parse=parsed)

    def _prompt(
        self,
        key: str,
        instruction: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        options: dict[str, str] | None,
    ) -> str:
        parts = [
            f"[섹션: {key}]\n{instruction}",
            f"[제안 입력]\n{json.dumps(req.prompt_view(), ensure_ascii=False)}",
        ]
        # 선택지·판정표는 앱이 만든 값이다 (비신뢰 구획 밖). 문서 제목은 넣지 않는다.
        if options is not None:
            listed = "\n".join(f"- {oid}: {label}" for oid, label in options.items())
            parts.append(f"[선택지 — 이 id 중에서만 고른다]\n{listed}")
        if key == OVERLAP_SECTION and snapshot.overlap_checked:
            rows = "\n".join(
                f"- id={a.doc_id} 구분={a.tier} 유사도={a.similarity:.2f} "
                f"중복기준초과={'예' if a.blocking else '아니오'} basis={a.basis or '-'} "
                f"겹친키워드={','.join(a.keywords) or '-'}"
                for a in snapshot.overlap
            )
            parts.append(f"[유사과제 판정 — 앱 계산]\n{rows}")
        if key in self.rules.evidence_forbidden:
            # 자료 인용 금지 섹션에 자료를 주면 약한 모델은 그래도 인용한다 → 아예 주지 않는다.
            parts.append(
                "[자료]\n(없음 — 이 섹션은 제안자 입력만 근거로 쓴다. evidence 는 빈 배열)"
            )
        else:
            parts.append(f"[자료]\n{wrap_untrusted(snapshot.chunks)}")
        return "\n\n".join(parts)

    def _enforce_grounding(
        self, key: str, section: Section, req: ProposalRequest
    ) -> tuple[Section, list[str]]:
        sources = self.rules.input_grounded.get(key)
        if not sources:
            return section, []
        allowed: list[str] = []
        for name in sources:
            if name == STRATEGY_SOURCE:
                allowed.extend(self.strategy.names())
                allowed.extend(self.strategy.options())  # id 도 허용
            else:
                value = getattr(req, name, "")
                allowed.append(value if isinstance(value, str) else "")
        kept: list[Sentence] = []
        dropped: list[str] = []
        for s in section.sentences:
            missing = ungrounded(s.text, allowed)
            if missing:
                dropped.append(f"{key}: 입력에 없는 고유명 {missing[:3]} → 폐기: {s.text[:40]}")
                continue
            kept.append(s)
        return section.model_copy(update={"sentences": kept}), dropped

    # ── finalize ─────────────────────────────────────────
    def finalize(
        self,
        run_id: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        sections: list[Section],
    ) -> tuple[Draft, list[LintProblem]]:
        draft = Draft(
            run_id=run_id,
            request=req,
            sections=sections,
            retrieved_ids=snapshot.retrieved_ids,
            template=self.template,
        )
        chunk_texts = {c.chunk_id: c.text for c in snapshot.chunks}
        problems = lint(
            draft, self.rules, choice_options=self.choice_options(), chunk_texts=chunk_texts
        )
        return draft, problems

    async def __call__(self, req: ProposalRequest) -> Draft:
        snapshot = await self.retrieve(req)
        sections: list[Section] = []
        dropped: list[str] = []
        for key in self.section_keys:
            composed = await self.compose_section(key, req, snapshot)
            sections.append(composed.section)
            dropped.extend(composed.dropped)
        draft, problems = self.finalize(uuid.uuid4().hex[:12], req, snapshot, sections)
        if has_errors(problems):
            raise DraftInvalid(problems, dropped)
        return draft
