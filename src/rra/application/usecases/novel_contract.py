"""새 과제 추천 갈래의 협력자 계약 (ADR 0057, docs/contracts/novel-recommend.md).

0단계에서만 고친다. 레인 B 가 구현하고(usecases/novelty.py), 레인 A 의 추천 유스케이스가 받아 쓴다.
조립(composition)이 둘을 잇는다 — 레인끼리 서로의 모듈을 import 하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from rra.domain.models import OverlapAlert, ProposalRequest
from rra.domain.models.novel import Analogy, NoveltyCoverage


@dataclass(frozen=True)
class NoveltyOutcome:
    """새로움 확인 결과.

    coverage: 실제로 확인한 자료원·실시간 여부(확인 안 한 자료원은 넣지 않는다).
    new_alerts: 넓힌 검색에서 새로 걸린 유사 과제(원래 알림에 없던 doc_id, ② 판정과 같은 규칙).
      비어 있지 않으면 추천 유스케이스는 novel 을 취소하고 differentiate 로 되돌리며, 이 행을
      `RecommendationResult.novelty_alerts` 에 담는다.
    """

    coverage: NoveltyCoverage
    new_alerts: list[OverlapAlert] = field(default_factory=list)


@runtime_checkable
class NoveltyCheck(Protocol):
    """novel 판정 뒤 실시간 검색 범위를 넓혀 한 번 더 확인한다. 같은 입력이면 세션 안에서 재사용."""

    async def __call__(
        self,
        req: ProposalRequest,
        alerts: list[OverlapAlert],
        *,
        core_keywords: list[str] | None = None,
    ) -> NoveltyOutcome: ...


@runtime_checkable
class AnalogySearch(Protocol):
    """유추 검색 — '문제' 축만 남긴 질의로 저장 자료 + 실시간 검색, 철도 밖 분야 상위 5건.
    관련도 하한(0.79)은 기존 규칙. 같은 입력이면 세션 안에서 재사용."""

    async def __call__(
        self,
        req: ProposalRequest,
        *,
        core_keywords: list[str] | None = None,
    ) -> list[Analogy]: ...
