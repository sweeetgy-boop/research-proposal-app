"""② 아이디어 4축 분해 유스케이스 (레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md §2).

로컬 모델(clarify 단계 = 로컬, 로컬 슬롯 안) 우선 → 출력이 JSON 객체가 아니거나 축 4개가 아니거나
80자를
넘으면 규칙(`domain/rules/facets.split_by_rule`). Argon 은 쓰지 않는다 — 판정 전 단계라 외부 전송을
늘리지 않는다. 호출자(PrecheckOverlap)는 스위치 `facets.enabled` 일 때만 부른다.

입력은 제안자 입력뿐(수집 문서 없음)이지만 출력은 비신뢰(보안 A) — 글자만 쓰고 길이 상한을 둔다.
로그는 출처(local|rule)와 예외 클래스명만.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from rra.application.ports.llm import LLMPort
from rra.domain.models import ProposalRequest
from rra.domain.models.facets import Facets
from rra.domain.rules.facets import parse_facets, split_by_rule
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.llm_output import parse_object

logger = logging.getLogger("rra.facet_split")

FACET_SYSTEM = (
    "너는 한국철도공사 철도연구원의 연구과제 검토 보조자다. 제안자의 아이디어를 네 축으로 나눈다.\n"
    "- target(대상): 다루는 시설·차량·설비·업무·공간 명사구\n"
    "- problem(문제): 해결하려는 현상·결함·불편\n"
    "- method(방법): 쓰려는 기술·기법·장치·분석 방법\n"
    "- place(장소): 역·구간·노선·지역 (없으면 빈 문자열)\n"
    "각 값은 한국어 한 줄 80자 이내, 입력에 있는 말만 쓴다(새 사실·수치를 지어내지 않는다). "
    '출력은 JSON 객체 하나 {"facets": {"target": "...", "problem": "...", "method": "...", '
    '"place": "..."}} 뿐이다.'
)
IDEA_FIELDS = ("title_hint", "current_state", "root_cause", "limitation", "goal", "method", "scope")


@dataclass
class FacetSplitter:
    local: LLMPort | None = None  # 로컬 모델 (clarify 단계). None 이면 규칙만
    keyword_rule: KeywordRule | None = None
    local_slot: Any | None = None  # GenerationSlot — 생성과 같은 슬롯
    max_tokens: int = 300
    calls: int = 0

    async def __call__(
        self, req: ProposalRequest, core_keywords: list[str] | None = None
    ) -> Facets:
        if self.local is not None:
            found = await self._ask_local(req)
            if found is not None:
                return found
        rule = self.keyword_rule or KeywordRule()
        facets = split_by_rule(req.search_text(), core_keywords, rule)
        logger.info("facet_split.rule empty=%s", facets.is_empty())
        return facets

    def build_prompt(self, req: ProposalRequest) -> str:
        view = req.prompt_view()
        idea = {k: view[k] for k in IDEA_FIELDS if k in view}
        return "[아이디어 — 제안자 입력]\n" + json.dumps(idea, ensure_ascii=False)

    async def _ask_local(self, req: ProposalRequest) -> Facets | None:
        gate = (
            self.local_slot.acquire() if self.local_slot is not None else contextlib.nullcontext()
        )
        self.calls += 1
        try:
            async with gate:
                raw = await self.local.complete(  # type: ignore[union-attr]
                    self.build_prompt(req),
                    system=FACET_SYSTEM,
                    max_tokens=self.max_tokens,
                    json_mode=True,
                )
        except Exception as exc:  # 로컬 실패는 규칙으로
            logger.warning("facet_split.local_failed err=%s", type(exc).__name__)
            return None
        facets = parse_facets(parse_object(raw))
        if facets is None:
            logger.info("facet_split.local_invalid")
        return facets
