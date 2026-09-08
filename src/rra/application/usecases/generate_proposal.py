from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from rra.application.ports import (
    DocumentRepository,
    LLMPort,
    PromptLibraryPort,
    RendererPort,
    RunLogPort,
)
from rra.domain.models import Draft, ProposalRequest, Section, Sentence
from rra.domain.rules.lint import LintRules, lint
from rra.domain.rules.trust import enforce_evidence, wrap_untrusted


class DraftInvalid(Exception):
    def __init__(self, problems, dropped):
        super().__init__(f"{len(problems)} lint problems, {len(dropped)} sentences dropped")
        self.problems, self.dropped = problems, dropped


@dataclass
class GenerateProposal:
    llm: LLMPort
    repo: DocumentRepository
    renderer: RendererPort
    run_log: RunLogPort
    prompts: PromptLibraryPort
    rules: LintRules
    section_keys: list[str]
    k: int = 20

    async def __call__(self, req: ProposalRequest) -> tuple[Draft, bytes]:
        run_id = uuid.uuid4().hex[:12]
        queries = [req.search_text()]
        chunks = self.repo.hybrid_search(queries, k=self.k)
        retrieved = {c.chunk_id for c in chunks} | {c.doc_id for c in chunks}
        context = wrap_untrusted(chunks)

        system = self.prompts.system()
        sections: list[Section] = []
        for key in self.section_keys:
            prompt = (
                f"[섹션: {key}]\n{self.prompts.section(key)}\n\n"
                f"[제안 입력]\n{req.model_dump_json()}\n\n[자료]\n{context}"
            )
            raw = await self.llm.complete(prompt, system=system, json_mode=True)
            sections.append(Section(key=key, sentences=self._parse(raw)))

        draft = Draft(run_id=run_id, request=req, sections=sections, retrieved_ids=retrieved)
        draft, dropped = enforce_evidence(draft, set(self.rules.evidence_required))
        problems = lint(draft, self.rules)
        self.run_log.record(
            run_id,
            {
                "query_hash": hashlib.sha256(queries[0].encode()).hexdigest(),
                "retrieved": sorted(retrieved),
                "dropped": len(dropped),
                "problems": len(problems),
            },
        )
        if problems:
            raise DraftInvalid(problems, dropped)
        return draft, self.renderer.render(draft)

    @staticmethod
    def _parse(raw: str) -> list[Sentence]:
        """A: JSON 스키마 외 출력은 전부 거부."""
        try:
            data = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
            return [Sentence.model_validate(x) for x in data]
        except Exception:
            return []
