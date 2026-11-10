"""`ClassCodeCheck` 구현 (ADR 0065, 계약 problem-card.md 2절·0절 3번).

확인 순서: (공식 코드표 — 1차 미구현, 꺼짐) → 저장 자료에 실제로 붙어 있는 코드(`CodeCountPort`)
→ KIPRIS 분류 검색 건수(`PatentClassCount`, 레인 B 가 구현 — 조립이 넣는다, 없으면 건너뜀).

- 건수가 1 이상이면 그 경로로 확인됨(corpus | kipris). 모두 0 이면 unverified.
- 실패(예외·건수 모름)는 unverified 이고 **캐시하지 않는다**. 답을 다 받은 결과만 코드별로 캐시한다
  (`cache_days`). 예외를 밖으로 내지 않는다.
- 이름(label)은 코드표가 있을 때만 채운다 — 1차에는 늘 빈 값(지어내지 않는다).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from rra.application.ports.code_count import CodeCountPort
from rra.domain.models.problem_card import CodeKind
from rra.domain.rules.problem_card import ipc_group_prefix, normalize_ipc

logger = logging.getLogger("rra.problem_card")

# 레인 B 의 KIPRIS 분류 건수(`problem_card_contract.PatentClassCount` 와 같은 모양) — 어댑터는
# 유스케이스 모듈을 import 할 수 없어 모양만 적는다
PatentCount = Callable[[str], Awaitable[int | None]]


@dataclass(frozen=True)
class CodeCheck:
    """`problem_card_contract.CodeCheck` 와 같은 칸(verified·count·label) — 호출자는 칸만 읽는다."""

    verified: str
    count: int | None = None
    label: str = ""


CACHE_VERSION = "class-code:v1"
_VERIFIED = ("table", "corpus", "kipris", "unverified")


class _Cache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any) -> None: ...


class StoredClassCodeCheck:
    def __init__(
        self,
        repo: Any,
        *,
        patent_count: PatentCount | None = None,
        cache: _Cache | None = None,
        use_corpus: bool = True,
        use_kipris: bool = True,
    ) -> None:
        self._repo = repo if isinstance(repo, CodeCountPort) else None
        self._patent_count = patent_count
        self._cache = cache
        self._use_corpus = use_corpus
        self._use_kipris = use_kipris

    def _cached(self, key: str) -> CodeCheck | None:
        if self._cache is None:
            return None
        found = self._cache.get(key)
        if not isinstance(found, dict) or found.get("verified") not in _VERIFIED:
            return None
        count = found.get("count")
        return CodeCheck(
            verified=found["verified"],
            count=count if isinstance(count, int) and count >= 0 else None,
            label=str(found.get("label") or "")[:80],
        )

    def _remember(self, key: str, check: CodeCheck) -> None:
        if self._cache is None:
            return
        try:
            self._cache.set(
                key, {"verified": check.verified, "count": check.count, "label": check.label}
            )
        except OSError as exc:
            logger.info("problem_card.code_check.cache_failed error=%s", type(exc).__name__)

    async def _corpus(self, kind: CodeKind, code: str) -> int | None:
        """저장 자료 건수. 볼 수 없으면 None."""
        if self._repo is None or not self._use_corpus:
            return None
        if kind == "ipc":
            prefix = ipc_group_prefix(code)
            return None if prefix is None else await self._repo.count_by_code(prefix)
        return await self._repo.count_by_science_class(code)

    async def __call__(self, kind: CodeKind, code: str) -> CodeCheck:
        if kind == "ipc":
            code = normalize_ipc(code) or ""
        code = " ".join((code or "").split())
        if not code:
            return CodeCheck(verified="unverified")
        key = f"{CACHE_VERSION}:{kind}:{code}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        complete = True  # 켜진 확인이 모두 답했는가 — 아니면 캐시하지 않는다
        try:
            n = await self._corpus(kind, code)
            if n:
                check = CodeCheck(verified="corpus", count=int(n))
                self._remember(key, check)
                return check
            if kind == "ipc" and self._use_kipris and self._patent_count is not None:
                total = await self._patent_count(code)
                if total is None:
                    complete = False
                elif total >= 1:
                    check = CodeCheck(verified="kipris", count=int(total))
                    self._remember(key, check)
                    return check
        except Exception as exc:  # 확인 실패는 '확인 못 함' — 진단을 막지 않는다
            logger.info("problem_card.code_check.failed error=%s", type(exc).__name__)
            return CodeCheck(verified="unverified")
        check = CodeCheck(verified="unverified", count=0 if complete else None)
        if complete:
            self._remember(key, check)
        return check
