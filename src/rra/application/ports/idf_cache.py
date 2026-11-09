"""말뭉치 IDF 표 캐시 포트 (레인 E, ADR 0059). 구현은 adapters/terms/idf_cache.py(JSON 파일,
`data/cache/idf.json`). 파일이 없으면 None — 가중 없음(= 종전)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rra.domain.rules.idf import IdfWeights


@runtime_checkable
class IdfCachePort(Protocol):
    def load(self) -> IdfWeights | None:
        """캐시된 표. 없거나 읽을 수 없으면 None."""
        ...

    def save(self, weights: IdfWeights) -> None:
        """표를 통째로 바꾼다 (임시 파일 → 교체)."""
        ...
