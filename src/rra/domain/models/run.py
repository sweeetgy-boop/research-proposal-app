"""생성 실행(run) 상태. 재개 단위는 step: retrieve → section:<key> × N → finalize."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

from .document import Chunk
from .gap import OverlapAlert

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
    parse: str | None = None  # section 만: ok | fence | json | schema (rules/llm_output.py)
    raw_chars: int | None = None  # section 만: LLM 원본 응답 길이 (원문은 저장하지 않음)


class RunState(BaseModel):
    run_id: str
    user: str
    status: RunStatus = "queued"
    steps: list[StepRecord]
    problems: list[dict[str, str]] = Field(default_factory=list)  # LintProblem dump
    model: str | None = None
    template: str | None = None  # 생성 때의 양식 id. None 이면 양식 개정 전 run (재개 불가)
    created_at: str
    updated_at: str

    def step(self, name: str) -> StepRecord:
        found = next((s for s in self.steps if s.name == name), None)
        if found is None:
            raise KeyError(name)
        return found

    @property
    def section_keys(self) -> list[str]:
        """이 run 이 계획한 섹션 순서. 양식이 바뀐 뒤에도 예전 run 은 자기 순서로 보인다."""
        n = len(SECTION_PREFIX)
        return [s.name[n:] for s in self.steps if s.name.startswith(SECTION_PREFIX)]

    @property
    def progress(self) -> tuple[int, int]:
        return sum(1 for s in self.steps if s.status == "done"), len(self.steps)


class RetrievalSnapshot(BaseModel):
    """retrieve 단계 결과. 재개 시 다시 검색하지 않고 이 집합으로만 근거를 검증한다.

    overlap: 같은 단계에서 계산한 유사과제 판정 (5. 특이사항). 그 doc_id 도 근거로 인용할 수 있다.
    """

    query_hash: str
    chunks: list[Chunk]
    overlap: list[OverlapAlert] = Field(default_factory=list)
    overlap_checked: bool = False  # False 면 유사과제 판정을 하지 않은 것 ("없음"과 구분)
    # retrieve 시점에 한 건도 적재되지 않았던 자료원. None = 확인하지 않음 (이전 스냅샷)
    uncollected: list[str] | None = None

    @classmethod
    def of(
        cls, query: str, chunks: list[Chunk], overlap: list[OverlapAlert] | None = None
    ) -> RetrievalSnapshot:
        return cls(
            query_hash=hashlib.sha256(query.encode()).hexdigest(),
            chunks=chunks,
            overlap=list(overlap or []),
            overlap_checked=overlap is not None,
        )

    @property
    def scope(self) -> dict[str, int]:
        """검토 범위 — 스냅샷에 들어간 자료원별 문서 수 (검색 청크 + 유사과제 판정 문서)."""
        doc_ids = {c.doc_id for c in self.chunks} | {a.doc_id for a in self.overlap}
        out: dict[str, int] = {}
        for doc_id in doc_ids:
            source = doc_id.split(":", 1)[0]
            out[source] = out.get(source, 0) + 1
        return out

    @property
    def retrieved_ids(self) -> set[str]:
        return (
            {c.chunk_id for c in self.chunks}
            | {c.doc_id for c in self.chunks}
            | {a.doc_id for a in self.overlap}
        )
