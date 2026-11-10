"""문제 정의 카드 재사용·고정 (ADR 0065, 계약 problem-card.md 4.4절).

같은 제안문에 부를 때마다 카드가 달라지면 유추 결과가 흔들린다. 그래서
- **공용 캐시**: 검증을 통과한 AI 카드를 입력 글 + 지시문 + 모델 기준 키로 보관해 다시 쓴다.
  카드만 저장한다(입력 원문·사용자 식별값 없음). 클라이언트가 보낸 카드는 넣지 않는다.
- **고정**: 사용자가 확인한 카드를 (가명 ID, 입력 글) 키로 보관해 그 사용자에게만 돌려준다.
  공용 계정(guest)·로그인 없음은 고정하지 않는다.

스위치(`enabled`·`reuse.enabled`)가 꺼져 있으면 저장소를 읽지도 쓰지도 않는다. 저장소 오류는
재사용 없이 진행한다(진단을 막지 않는다). 로그에는 종류·예외 클래스명만.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rra.application.ports import CachePort
from rra.domain.models import Principal, ProposalRequest
from rra.domain.models.problem_card import ProblemCard, ProblemCardConfig
from rra.domain.rules import card_reuse as rules

logger = logging.getLogger("rra.problem_card")


@dataclass
class CardReuse:
    """cache: 공용 캐시(보관 기간은 어댑터 ttl), pins: 고정 저장소(만료 없음).
    None 이면 그 기능 없음."""

    config: ProblemCardConfig
    cache: CachePort | None = None
    pins: CachePort | None = None

    @property
    def active(self) -> bool:
        return self.config.enabled and self.config.reuse.enabled

    def _get(self, store: CachePort | None, key: str) -> ProblemCard | None:
        if store is None:
            return None
        try:
            return rules.load_card(store.get(key))
        except Exception as exc:  # 저장소 오류는 재사용 없이 진행
            logger.info("card.reuse.read_failed error=%s", type(exc).__name__)
            return None

    def _set(self, store: CachePort | None, key: str, card: ProblemCard) -> bool:
        if store is None:
            return False
        try:
            store.set(key, card.model_dump(mode="json"))
        except Exception as exc:
            logger.info("card.reuse.write_failed error=%s", type(exc).__name__)
            return False
        return True

    def lookup(
        self, req: ProposalRequest, principal: Principal | None, version: str
    ) -> tuple[ProblemCard | None, rules.ReuseKind | None]:
        """고정한 카드(그 사용자 것만) → 공용 캐시 순. 없으면 (None, None)."""
        if not self.active:
            return None, None
        if principal is not None and rules.can_pin(principal):
            pinned = self._get(self.pins, rules.pin_key(principal.id, req))
            if pinned is not None:
                return pinned, rules.REUSE_PINNED
        cached = self._get(self.cache, rules.cache_key(req, version))
        if cached is not None:
            return cached, rules.REUSE_CACHED
        return None, None

    def store(self, req: ProposalRequest, card: ProblemCard, version: str) -> bool:
        """검증을 통과한 AI 카드를 공용 캐시에 넣는다(같은 키는 갈아 끼운다)."""
        if not self.active:
            return False
        return self._set(self.cache, rules.cache_key(req, version), card)

    def pin(
        self, req: ProposalRequest, card: ProblemCard | None, principal: Principal | None
    ) -> bool:
        """사용자가 확인한 카드를 그 사용자 몫으로 고정한다.
        공용 계정·로그인 없음·꺼짐이면 False."""
        if not self.active or card is None or principal is None:
            return False
        if not rules.can_pin(principal):
            return False
        done = self._set(self.pins, rules.pin_key(principal.id, req), card)
        if done:
            logger.info("card.pin done=1")
        return done
