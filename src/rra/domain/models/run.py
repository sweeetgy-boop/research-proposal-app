"""생성 실행(run) 상태. 재개 단위는 step: retrieve → section:<key> × N → finalize."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

from .document import Chunk

RunStatus = Literal["queued", "running", "interrupted", "failed", "invalid", "done"]
StepStatus = Literal["pending", "done", "error"]

ACTIVE: frozenset[str] = frozenset({"queued", "running"})
RESUMABLE: frozenset[str] = frozenset({"interrupted"})
FINISHED: frozenset[str] = frozenset({"done", "invalid", "failed"})

RETRIEVE = "retrieve"
FINALIZE = "finalize"
SECTION_PREFIX = "section:"

_RUN_ID = re.compile(r"^\d{14}-[0-9a-f]{8}$")


def is_valid_run_id(value: object) -> bool:
    """경로에 쓰이므로 형식이 정확할 때만 True (MCP·CLI 입력의 경로 조작 차단)."""
    return isinstance(value, str) and bool(_RUN_ID.match(value))


def section_step(key: str) -> str:
    return f"{SECTION_PREFIX}{key}"


def plan_steps(section_keys: list[str]) -> list[str]:
    return [RETRIEVE, *(section_step(k) for k in section_keys), FINALIZE]


class StepRecord(BaseModel):
    name: str
    status: StepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None  # 예외 클래스명만 (메시지·경로 금지)
    sentences: int = 0
    dropped: int = 0
    evidence: list[str] = Field(default_factory=list)
    prompt_hash: str | None = None


class RunState(BaseModel):
    run_id: str
    user: str
    status: RunStatus = "queued"
    steps: list[StepRecord]
    problems: list[dict[str, str]] = Field(default_factory=list)  # LintProblem dump
    model: str | None = None
    created_at: str
    updated_at: str

    def step(self, name: str) -> StepRecord:
        found = next((s for s in self.steps if s.name == name), None)
        if found is None:
            raise KeyError(name)
        return found

    @property
    def progress(self) -> tuple[int, int]:
        return sum(1 for s in self.steps if s.status == "done"), len(self.steps)


class RetrievalSnapshot(BaseModel):
    """retrieve 단계 결과. 재개 시 다시 검색하지 않고 이 집합으로만 근거를 검증한다."""

    query_hash: str
    chunks: list[Chunk]

    @classmethod
    def of(cls, query: str, chunks: list[Chunk]) -> RetrievalSnapshot:
        return cls(query_hash=hashlib.sha256(query.encode()).hexdigest(), chunks=chunks)

    @property
    def retrieved_ids(self) -> set[str]:
        return {c.chunk_id for c in self.chunks} | {c.doc_id for c in self.chunks}
