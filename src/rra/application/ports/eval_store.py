"""평가 체계 포트 (ADR 0058, 레인 D) — 결과 저장·문제 묶음 저장·LLM 응답 캐시.

`ports/__init__.py` 에는 아직 올리지 않았다(공용 파일 — 통합 때 메인이 export 줄을 더한다).
쓰는 쪽은
이 모듈에서 직접 import 한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from rra.domain.models.eval_problem import EvalProblem
from rra.domain.models.eval_result import EvalResult


@runtime_checkable
class EvalResultStorePort(Protocol):
    """결과 JSON(`eval/results/<날짜>-<suite>[-<label>].json`) 읽기·쓰기 — 수치만."""

    def write(self, result: EvalResult, *, path: Path | None = None) -> Path: ...

    def read(self, path: Path) -> EvalResult: ...


@runtime_checkable
class ProblemStorePort(Protocol):
    """문제 묶음(JSONL) — 봉인(`sealed/<suite>.jsonl`, 600)·연습
    (`practice/<suite>-<seed>.jsonl`)."""

    def sealed_path(self, suite: str) -> Path: ...

    def practice_path(self, suite: str, seed: int) -> Path: ...

    def exists(self, path: Path) -> bool: ...

    def load(self, path: Path) -> list[EvalProblem]: ...

    def save(self, path: Path, problems: Sequence[EvalProblem]) -> Path: ...


class CacheMiss(RuntimeError):
    """L0 캐시 재생에서 프롬프트 해시에 맞는 응답이 없다 — 유스케이스는 규칙 판정으로 간다."""


@runtime_checkable
class ReplayCountsPort(Protocol):
    """캐시 재생 LLM 의 적중·미스 수 (EvalResult.cache_hits·notes)."""

    @property
    def hits(self) -> int: ...

    @property
    def misses(self) -> int: ...

    @property
    def recorded(self) -> int:
        """미스 가운데 안쪽 LLM 을 불러 녹화한 수 (외부 호출로 센다)."""
        ...
