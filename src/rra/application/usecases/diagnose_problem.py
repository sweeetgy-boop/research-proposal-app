"""문제 정의 카드 진단 — AI 1회 + 규칙 검증 (ADR 0065, 계약 problem-card.md 2·3·6절).

`problem_card_contract.ProblemDiagnosis` 구현.

- 설정이 꺼져 있으면 `status="off"`(카드 없음) — 호출자는 종전 방식으로 진행한다.
- AI 는 `ArgonFirst` 로 **1회**(형식 오류면 교정 재요청 1회, 오류 응답일 때만 로컬). 응답은 JSON 만
  파싱하고 `domain/rules/problem_card` 가 검증한다(지어낸 숫자·기관명·법령명이 든 칸은 비움).
- `timeout_seconds` 를 넘으면 `failed`/`timeout` — 카드 없이 진행(화면은 기다리지 않는다).
- 분류 코드는 코드마다 `ClassCodeCheck` 로 함께 확인한다(없거나 늦으면 unverified).
- 본인 예시: 그 사용자의 수정 짝 중 지금 입력과 비슷한 것만 지시문에 넣는다. 공용 계정·로그인
  없음이면 넣지 않는다. **다른 사용자 줄은 어떤 경우에도 넣지 않는다.**
- 프롬프트 입력은 이름·연락처를 지우고 태그를 무력화한다. 로그에는 건수·상태·예외 클래스명만.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from rra.application.ports import EmbeddingPort, PromptLibraryPort
from rra.application.usecases.argon_first import ArgonFirst
from rra.application.usecases.problem_card_contract import (
    CardEditLogPort,
    ClassCodeCheck,
    DiagnoseOutcome,
)
from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import ProblemCard, ProblemCardConfig
from rra.domain.rules import card_edits
from rra.domain.rules import problem_card as rules
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.llm_output import parse_object
from rra.domain.rules.novelty import ProblemAxisRule
from rra.domain.rules.privacy import strip_personal
from rra.domain.rules.trust import escape_untrusted

logger = logging.getLogger("rra.problem_card")

PROMPT_HEAD = "[문제 진단]"
DERIVE_HEAD = "[문제 진단: 다시 만들기]"
REASON_TIMEOUT = "timeout"
PROVIDER_LOCAL = "local"
EXAMPLE_POOL = 50  # 유사도를 볼 최근 수정 짝 수(임베딩 1회 호출의 크기 상한)
CODE_CHECK_SECONDS = 5.0  # 분류 코드 확인이 이보다 늦으면 확인 못 함으로 둔다
INPUT_KEYS = ("title_hint", "current_state", "root_cause", "limitation", "goal")


def safe_text(text: str | None) -> str:
    """프롬프트에 넣을 제안자 글 — 이름·연락처 제거 + 구획 태그 무력화."""
    return escape_untrusted(strip_personal(text or "").text)


def input_block(req: ProposalRequest) -> str:
    view = {k: safe_text(getattr(req, k)) for k in INPUT_KEYS if getattr(req, k)}
    return "[제안 입력]\n" + json.dumps(view, ensure_ascii=False)


async def check_codes(
    card: ProblemCard,
    code_check: ClassCodeCheck | None,
    *,
    kinds: tuple[str, ...] = ("ipc", "science_class"),
    seconds: float = CODE_CHECK_SECONDS,
) -> ProblemCard:
    """분류 코드마다 함께 확인해 verified·count·label 을 채운다. 실패·지연은 unverified."""
    todo = [(kind, c.code) for kind in kinds for c in getattr(card, kind)]
    if code_check is None or not todo:
        return card

    async def one(kind: str, code: str) -> tuple[str, int | None, str]:
        try:
            found = await code_check(kind, code)  # type: ignore[arg-type]
        except Exception as exc:  # 계약상 예외를 내지 않지만, 내더라도 카드는 살린다
            logger.info("problem_card.code_check.failed error=%s", type(exc).__name__)
            return "unverified", None, ""
        return found.verified, found.count, found.label

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(one(kind, code) for kind, code in todo)), timeout=seconds
        )
    except TimeoutError:
        logger.info("problem_card.code_check.timeout codes=%d", len(todo))
        return card
    return rules.with_code_checks(card, dict(zip(todo, results, strict=True)))


@dataclass
class DiagnoseProblem:
    ask: ArgonFirst
    prompts: PromptLibraryPort
    config: ProblemCardConfig
    axis: ProblemAxisRule | None = None
    keywords: KeywordRule | None = None
    code_check: ClassCodeCheck | None = None
    edit_log: CardEditLogPort | None = None
    embedding: EmbeddingPort | None = None
    max_tokens: int | None = None
    argon_provider: str = "gemini"
    clock: Callable[[], float] = time.monotonic

    def _rule(self) -> KeywordRule:
        return self.keywords or KeywordRule()

    async def _examples(self, req: ProposalRequest, principal: Principal | None) -> list[Mapping]:
        """본인 수정 예시 — 그 가명 ID 의 줄에서만. 실패하면 예시 없이 진행한다."""
        learning = self.config.learning
        if (
            principal is None
            or principal.kind == "guest"
            or not learning.examples
            or learning.max_examples <= 0
            or self.edit_log is None
            or self.embedding is None
        ):
            return []
        try:
            mine = card_edits.learnable(
                self.edit_log.by_user(principal.id, limit=200),
                user=principal.id,
                polish_similarity=learning.polish_similarity,
            )[:EXAMPLE_POOL]
            if not mine:
                return []
            texts = [req.search_text(), *(card_edits.example_text(r) for r in mine)]
            vectors = await self.embedding.embed(texts)
            sims = [card_edits.cosine(vectors[0], v) for v in vectors[1:]]
            return card_edits.pick_examples(
                mine,
                sims,
                user=principal.id,
                min_similarity=learning.example_min_similarity,
                polish_similarity=learning.polish_similarity,
                limit=learning.max_examples,
            )
        except Exception as exc:
            logger.info("problem_card.examples.failed error=%s", type(exc).__name__)
            return []

    def _prompt(
        self, req: ProposalRequest, previous: ProblemCard | None, examples: list[Mapping]
    ) -> str:
        parts = [PROMPT_HEAD, input_block(req)]
        fixed = {k: safe_text(v) for k, v in rules.user_items_view(previous).items()}
        if fixed:
            parts.append(
                "[제안자가 고친 항목 — 그대로 둔다]\n" + json.dumps(fixed, ensure_ascii=False)
            )
        block = card_edits.examples_block(examples, rules.FIELD_LABELS)
        if block:
            parts.append("[이 제안자가 전에 고친 예]\n" + escape_untrusted(block))
        parts.append("[출력] 지시한 칸을 가진 JSON 객체 하나.")
        return "\n\n".join(parts)

    async def _run(
        self,
        req: ProposalRequest,
        previous: ProblemCard | None,
        examples: list[Mapping],
    ) -> tuple[Any, rules.ParsedCard | None]:
        def check(raw: str) -> tuple[rules.ParsedCard | None, str | None]:
            data = parse_object(raw)
            if not isinstance(data, dict):
                return None, "invalid"
            parsed = rules.parse_card(data, req, axis=self.axis, rule=self._rule())
            # 기능 문장이 비면 진단 실패(계약 2절) — 형식 오류처럼 교정 재요청 1회
            return (parsed, None) if parsed.card is not None else (None, "invalid")

        res = await self.ask.ask(
            self._prompt(req, previous, examples),
            system=self.prompts.diagnose(),
            check=check,
            max_tokens=self.max_tokens,
        )
        return res, res.value

    async def __call__(
        self,
        req: ProposalRequest,
        *,
        previous: ProblemCard | None = None,
        principal: Principal | None = None,
    ) -> DiagnoseOutcome:
        if not self.config.enabled:
            return DiagnoseOutcome(status="off")
        started = self.clock()
        examples = await self._examples(req, principal)
        try:
            res, parsed = await asyncio.wait_for(
                self._run(req, previous, examples), timeout=self.config.timeout_seconds
            )
        except TimeoutError:
            seconds = round(self.clock() - started, 1)
            logger.info("problem_card.diagnose status=failed reason=timeout seconds=%.1f", seconds)
            return DiagnoseOutcome(
                status="failed", reason=REASON_TIMEOUT, seconds=seconds, examples=len(examples)
            )
        remote = res.remote_calls > 0 and not res.fallback
        provider = (self.argon_provider if remote else PROVIDER_LOCAL) if res.calls else None
        if parsed is None or parsed.card is None:
            seconds = round(self.clock() - started, 1)
            logger.info(
                "problem_card.diagnose status=failed reason=%s calls=%d seconds=%.1f",
                res.reason,
                res.calls,
                seconds,
            )
            return DiagnoseOutcome(
                status="failed",
                reason=res.reason or "invalid",
                provider=provider,
                model=res.model,
                fallback=res.fallback,
                seconds=seconds,
                examples=len(examples),
            )
        card = rules.keep_user_items(parsed.card, previous)
        card = rules.recheck_cause(card, req, self._rule())
        card = await check_codes(card, self.code_check)
        seconds = round(self.clock() - started, 1)
        logger.info(
            "problem_card.diagnose status=ok calls=%d fallback=%s cleared=%d changed=%d "
            "examples=%d seconds=%.1f",
            res.calls,
            res.fallback,
            len(parsed.cleared),
            len(parsed.changed),
            len(examples),
            seconds,
        )
        return DiagnoseOutcome(
            status="ok",
            card=card,
            provider=provider,
            model=res.model,
            fallback=res.fallback,
            seconds=seconds,
            examples=len(examples),
        )
