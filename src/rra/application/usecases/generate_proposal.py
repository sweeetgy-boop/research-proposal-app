"""제안서 초안 생성. 재개 가능하도록 세 단계로 나뉜다.

    retrieve(req)                    → RetrievalSnapshot  (검색 1회, 결과를 고정)
    compose_section(key, req, snap)  → 섹션 1개 (LLM 1회, 섹션 단위 근거 검증까지)
    finalize(run_id, req, snap, …)   → Draft + lint 문제

상태 저장·재개·동시성은 application/services/run_manager.py 가 맡는다.
`__call__` 은 세 단계를 한 번에 도는 조합이다 (테스트·일회성 실행용).

보안 A: LLM 출력은 JSON 배열만 받고, 근거 id 는 이번 run 의 검색 집합(스냅샷)과 대조한다.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from rra.application.ports import DocumentRepository, LLMPort, PromptLibraryPort
from rra.domain.models import Draft, ProposalRequest, RetrievalSnapshot, Section
from rra.domain.rules.lint import LintProblem, LintRules, lint
from rra.domain.rules.llm_output import ParseResult, parse_sentences
from rra.domain.rules.trust import enforce_section_evidence, wrap_untrusted


class DraftInvalid(Exception):
    def __init__(self, problems, dropped):
        super().__init__(f"{len(problems)} lint problems, {len(dropped)} sentences dropped")
        self.problems, self.dropped = problems, dropped


@dataclass(frozen=True)
class ComposedSection:
    section: Section
    dropped: list[str]
    prompt_hash: str  # 시스템 프롬프트 + 섹션 지시문 해시 (입력·자료 미포함)
    parse: ParseResult  # 파싱 사유·원본 길이 (문장은 section 에 근거 검증 후 들어 있음)


@dataclass
class GenerateProposal:
    llm: LLMPort
    repo: DocumentRepository
    prompts: PromptLibraryPort
    rules: LintRules
    section_keys: list[str]
    k: int = 20

    def retrieve(self, req: ProposalRequest) -> RetrievalSnapshot:
        query = req.search_text()
        return RetrievalSnapshot.of(query, list(self.repo.hybrid_search([query], k=self.k)))

    async def compose_section(
        self, key: str, req: ProposalRequest, snapshot: RetrievalSnapshot
    ) -> ComposedSection:
        system = self.prompts.system()
        instruction = self.prompts.section(key)
        prompt = (
            f"[섹션: {key}]\n{instruction}\n\n"
            f"[제안 입력]\n{req.model_dump_json()}\n\n[자료]\n{wrap_untrusted(snapshot.chunks)}"
        )
        raw = await self.llm.complete(prompt, system=system, json_mode=True)
        parsed = parse_sentences(raw)
        section, dropped = enforce_section_evidence(
            Section(key=key, sentences=parsed.sentences),
            snapshot.retrieved_ids,
            evidence_required=key in self.rules.evidence_required,
        )
        digest = hashlib.sha256(f"{system}\x1f{instruction}".encode()).hexdigest()[:16]
        return ComposedSection(section=section, dropped=dropped, prompt_hash=digest, parse=parsed)

    def finalize(
        self,
        run_id: str,
        req: ProposalRequest,
        snapshot: RetrievalSnapshot,
        sections: list[Section],
    ) -> tuple[Draft, list[LintProblem]]:
        draft = Draft(
            run_id=run_id, request=req, sections=sections, retrieved_ids=snapshot.retrieved_ids
        )
        return draft, lint(draft, self.rules)

    async def __call__(self, req: ProposalRequest) -> Draft:
        snapshot = self.retrieve(req)
        sections: list[Section] = []
        dropped: list[str] = []
        for key in self.section_keys:
            composed = await self.compose_section(key, req, snapshot)
            sections.append(composed.section)
            dropped.extend(composed.dropped)
        draft, problems = self.finalize(uuid.uuid4().hex[:12], req, snapshot, sections)
        if problems:
            raise DraftInvalid(problems, dropped)
        return draft
