"""평가 문제 자동 생성 (ADR 0058, 계약 docs/contracts/eval-results.md §3) — `ProblemGenerator`.

DB 는 `CorpusAccessPort.documents_of(source)` 로만 읽는다(과제형 자료원: own·alio·ntis rnd_project,
config/eval.yaml l1.sources). 문서의 제목·초록·본문만 쓰고 internal 문서는 재료에서 뺀다(원격 판정에
보내지 않도록). 규칙은 `domain/rules/eval_problems` 에 있고 여기서는 seed 로 뽑고 섞는다:

- 역방향: 재료 문서를 seed 로 섞어 차례로 `reverse_problem` — 글이 짧으면 다음 문서.
- 함정: 서로 다른 자료원(또는 같은 자료원의 먼 문서) 두 건을 seed 로 짝지어 `trap_problem` — 같은
  주제(자카드 ≥ 0.15)면 다음 짝.
- 새 영역: 주제 사전을 seed 로 섞고, `rule_check`(규칙 판정만 — LLM 없음)가 차단이라고 하는 주제는
  뺀다. 사전이 모자라면 있는 만큼만.

매 실행 새 seed(기본 오늘 날짜 숫자). 봉인 묶음은 `sealed_seed` 로 한 번 만들어 600 권한으로 둔다.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from datetime import date

from rra.application.ports.table_facts import CorpusAccessPort
from rra.domain.models import Document, ProposalRequest
from rra.domain.models.eval_problem import (
    EvalProblem,
    NovelTopic,
    ProblemMix,
    ProblemSource,
)
from rra.domain.rules.eval_problems import novel_problem, reverse_problem, trap_problem
from rra.domain.rules.keywords import KeywordRule

logger = logging.getLogger("rra.eval")
RuleCheck = Callable[[ProposalRequest], Awaitable[bool]]  # True = 규칙 판정이 차단


def today_seed(day: date | None = None) -> int:
    d = day or date.today()
    return d.year * 10000 + d.month * 100 + d.day


class ProblemGenerator:
    def __init__(
        self,
        repo: CorpusAccessPort,
        *,
        sources: Sequence[ProblemSource],
        topics: Sequence[NovelTopic],
        keywords: KeywordRule | None = None,
        rule_check: RuleCheck | None = None,
        min_text_chars: int = 150,
        max_docs_per_source: int | None = None,
    ):
        self.repo = repo
        self.sources = list(sources)
        self.topics = list(topics)
        self.keywords = keywords or KeywordRule()
        self.rule_check = rule_check
        self.min_text_chars = min_text_chars
        self.max_docs = max_docs_per_source

    async def materials(self) -> list[Document]:
        """재료 문서 — 자료원·doc_type 필터, internal 제외, doc_id 순(결정적)."""
        out: list[Document] = []
        for member in self.sources:
            docs = await self.repo.documents_of(member.source, limit=self.max_docs)
            for d in docs:
                if member.doc_types and d.doc_type not in member.doc_types:
                    continue
                if d.visibility == "internal":
                    continue
                out.append(d)
        out.sort(key=lambda d: d.doc_id)
        return out

    async def generate(self, *, seed: int, n: int, mix: ProblemMix) -> list[EvalProblem]:
        counts = mix.counts(n)
        rng = random.Random(seed)  # noqa: S311 — 재현 가능한 표본 추출
        docs = await self.materials()
        problems: list[EvalProblem] = []
        problems += self._reverse(docs, counts["reverse"], rng, seed)
        problems += self._trap(docs, counts["trap"], rng, seed)
        problems += await self._novel(counts["novel"], rng, seed)
        rng.shuffle(problems)
        logger.info(
            "eval.problems seed=%s n=%s reverse=%s trap=%s novel=%s materials=%s",
            seed,
            len(problems),
            sum(p.kind == "reverse" for p in problems),
            sum(p.kind == "trap" for p in problems),
            sum(p.kind == "novel" for p in problems),
            len(docs),
        )
        return problems

    def _reverse(self, docs, count, rng, seed) -> list[EvalProblem]:
        order = list(docs)
        rng.shuffle(order)
        out: list[EvalProblem] = []
        for doc in order:
            if len(out) >= count:
                break
            p = reverse_problem(doc, self.keywords, min_chars=self.min_text_chars, seed=seed)
            if p is not None:
                out.append(p)
        return out

    def _trap(self, docs, count, rng, seed) -> list[EvalProblem]:
        if count <= 0 or len(docs) < 2:
            return []
        out: list[EvalProblem] = []
        seen: set[tuple[str, str]] = set()
        tries = 0
        while len(out) < count and tries < count * 40:
            tries += 1
            a, b = rng.sample(docs, 2)
            if a.source == b.source and len({d.source for d in docs}) > 1 and rng.random() < 0.5:
                continue  # 자료원이 다른 짝을 더 자주
            key = (a.doc_id, b.doc_id)
            if key in seen:
                continue
            seen.add(key)
            p = trap_problem(a, b, self.keywords, min_chars=self.min_text_chars, seed=seed)
            if p is not None:
                out.append(p)
        return out

    async def _novel(self, count, rng, seed) -> list[EvalProblem]:
        topics = list(self.topics)
        rng.shuffle(topics)
        out: list[EvalProblem] = []
        for topic in topics:
            if len(out) >= count:
                break
            p = novel_problem(topic, seed=seed)
            if self.rule_check is not None:
                try:
                    blocked = await self.rule_check(p.to_request())
                except Exception as exc:  # 사전 확인 실패는 문제를 막지 않는다
                    logger.warning("eval.novel_precheck_failed err=%s", type(exc).__name__)
                    blocked = False
                if blocked:
                    continue  # 저장 자료에 유사 과제가 있는 주제는 새 영역이 아니다
            out.append(p)
        return out


def precheck_blocks(precheck) -> RuleCheck:
    """PrecheckOverlap → 규칙 판정만(ai=False) 돌려 차단 여부를 주는 함수."""

    async def check(req: ProposalRequest) -> bool:
        result = await precheck.run(req, ai=False)
        return bool(result.blocking)

    return check
