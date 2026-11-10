"""문제 정의 카드 수정 반영 — 고친 항목에 기대는 것만 다시 계산 + 기록 (ADR 0065, 계약 3.2·6절).

`problem_card_contract.CardEditor` 구현.

- `fields` 의 항목만 `after` 에서 가져와 origin=user 로 만든다(AI 값 보존). 나머지는 `before`.
- `function_ko` → 영문·사다리·문제어 중 사용자 항목이 아닌 것만 AI 1회로 다시 만든다. 실패해도
  수정은 반영하고 그 칸들은 그대로 둔다.
- `contradiction` → 발명 원리 재검증(규칙). `ipc`·`science_class` → 코드 확인. `cause` → '확인 필요'
  재판정.
- 서버는 과제안을 다시 만들지 않는다 — reruns 에 `plans_stale` 을 담아 화면이 버튼을 보이게 한다.
- 기록: 공용 계정·로그인 없음이면 남기지 않는다. 시험 계정 줄은 `test: true`. 변경 전후 의미
  유사도는 임베딩 코사인(없으면 None). 로그에는 건수·상태·예외 클래스명만.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from rra.application.ports import ChoiceLogPort, EmbeddingPort, PromptLibraryPort
from rra.application.usecases.argon_first import ArgonFirst
from rra.application.usecases.diagnose_problem import (
    DERIVE_HEAD,
    check_codes,
    input_block,
    safe_text,
)
from rra.application.usecases.problem_card_contract import (
    CardEdit,
    CardEditLogPort,
    ClassCodeCheck,
    EditOutcome,
)
from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import ProblemCard, ProblemCardConfig
from rra.domain.rules import card_edits
from rra.domain.rules import problem_card as rules
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.llm_output import parse_object
from rra.domain.rules.novelty import ProblemAxisRule
from rra.domain.rules.similar_choice import idea_hash

logger = logging.getLogger("rra.problem_card")


class CardDisabled(RuntimeError):
    """문제 정의 카드가 꺼져 있다 — 수정 요청을 받지 않는다."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class EditProblemCard:
    config: ProblemCardConfig
    prompts: PromptLibraryPort
    ask: ArgonFirst | None = None
    axis: ProblemAxisRule | None = None
    keywords: KeywordRule | None = None
    code_check: ClassCodeCheck | None = None
    edit_log: CardEditLogPort | None = None
    choice_log: ChoiceLogPort | None = None
    embedding: EmbeddingPort | None = None
    max_tokens: int | None = None
    now: Callable[[], str] = _now

    def _rule(self) -> KeywordRule:
        return self.keywords or KeywordRule()

    async def _derive(self, req: ProposalRequest, card: ProblemCard) -> tuple[ProblemCard, int]:
        """고친 기능 문장에 맞춰 영문·사다리·문제어를 다시 만든다(사용자 항목 제외). AI 1회
        (형식 교정·로컬 대체는 ArgonFirst 규칙). 실패하면 카드를 그대로 돌려준다."""
        wanted = [
            name
            for name, user in (
                ("function_en", card.function_en.origin == "user"),
                ("ladder", card.ladder_origin == "user"),
                ("terms", card.terms.origin == "user"),
            )
            if not user
        ]
        if self.ask is None or not wanted:
            return card, 0
        function_ko = card.function_ko.value
        prompt = "\n\n".join(
            [
                DERIVE_HEAD,
                input_block(req),
                "[제안자가 고친 항목 — 그대로 둔다]\n"
                + json.dumps({"기능 문장": safe_text(function_ko)}, ensure_ascii=False),
                "[출력] 고친 기능 문장에 맞춘 JSON 객체 하나 — "
                + "·".join(wanted)
                + " 칸만 채우고 나머지 칸은 넣지 않는다.",
            ]
        )

        def check(raw: str) -> tuple[ProblemCard | None, str | None]:
            data = parse_object(raw)
            if not isinstance(data, dict):
                return None, "invalid"
            parsed = rules.parse_card(
                data,
                req,
                axis=self.axis,
                rule=self._rule(),
                function_ko=function_ko,
                place=card.facets.place.value,
            )
            return (parsed.card, None) if parsed.card is not None else (None, "invalid")

        try:
            res = await asyncio.wait_for(
                self.ask.ask(
                    prompt, system=self.prompts.diagnose(), check=check, max_tokens=self.max_tokens
                ),
                timeout=self.config.timeout_seconds,
            )
        except TimeoutError:
            logger.info("problem_card.derive status=failed reason=timeout")
            return card, 1
        if res.value is None:
            logger.info("problem_card.derive status=failed reason=%s", res.reason)
            return card, int(res.calls > 0)
        return rules.apply_derived(card, res.value), 1

    async def _similarity(self, before: str, after: str) -> float | None:
        if self.embedding is None or not before or not after:
            return None
        try:
            a, b = await self.embedding.embed([before, after])
        except Exception as exc:
            logger.info("problem_card.similarity.failed error=%s", type(exc).__name__)
            return None
        return card_edits.cosine(a, b)

    async def _record(
        self,
        req: ProposalRequest,
        before: ProblemCard,
        card: ProblemCard,
        fields: list[str],
        principal: Principal | None,
    ) -> bool:
        """수정 짝 + card_edit 줄. 공용 계정·로그인 없음·저장 꺼짐이면 남기지 않는다."""
        if (
            principal is None
            or principal.kind == "guest"
            or not self.config.learning.store_edits
            or self.edit_log is None
        ):
            return False
        at, idea = self.now(), idea_hash(req.search_text())
        recorded = False
        lines = []
        for name in fields:
            old, new = rules.field_text(before, name), rules.field_text(card, name)
            if old == new:
                continue
            common = {
                "at": at,
                "idea": idea,
                "field": name,
                "before": old,
                "after": new,
                "methods": card.methods,
                "signals": card.signals,
                "test": principal.test,
            }
            try:
                self.edit_log.append(
                    card_edits.edit_record(
                        user=principal.id,
                        similarity=await self._similarity(old, new),
                        function=before.function_ko.value,
                        **common,
                    )
                )
            except Exception as exc:  # 기록 실패가 수정 반영을 막지 않는다
                logger.info("problem_card.edit_log.failed error=%s", type(exc).__name__)
                continue
            recorded = True
            lines.append(card_edits.choice_line(**common))
        if lines and self.choice_log is not None:
            try:
                self.choice_log.append(lines)
            except Exception as exc:
                logger.info("problem_card.choice_log.failed error=%s", type(exc).__name__)
        return recorded

    async def __call__(
        self,
        req: ProposalRequest,
        before: ProblemCard,
        after: ProblemCard,
        edits: list[CardEdit],
        *,
        principal: Principal | None = None,
    ) -> EditOutcome:
        if not self.config.enabled:
            raise CardDisabled
        fields = [e.field for e in edits]
        card, reruns = rules.apply_edits(before, after, fields)
        calls = 0
        if "derive" in reruns:
            card, calls = await self._derive(req, card)
        if "codes" in reruns:
            kinds = tuple(k for k in ("ipc", "science_class") if k in fields)
            card = await check_codes(card, self.code_check, kinds=kinds)
        if "checks" in reruns:
            card = rules.recheck_cause(card, req, self._rule())
        recorded = await self._record(req, before, card, list(dict.fromkeys(fields)), principal)
        logger.info(
            "problem_card.edit fields=%d reruns=%d calls=%d recorded=%s",
            len(fields),
            len(reruns),
            calls,
            recorded,
        )
        return EditOutcome(card=card, reruns=reruns, recorded=recorded, calls=calls)
