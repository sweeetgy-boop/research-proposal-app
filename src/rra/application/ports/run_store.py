from __future__ import annotations

from typing import Protocol

from rra.domain.models import Draft, ProposalRequest, RetrievalSnapshot, RunState, Section


class RunNotFound(LookupError):
    """해당 사용자에게 그런 run 이 없다 (다른 사용자의 run 도 여기에 해당)."""


class RunBusy(RuntimeError):
    """다른 실행(같은 프로세스든 다른 프로세스든)이 이 run 을 잡고 있다."""


class RunClaim(Protocol):
    def release(self) -> None: ...


class RunStorePort(Protocol):
    """생성 실행의 상태·체크포인트 저장소. 사용자별로 격리된다."""

    def create(self, user: str, req: ProposalRequest, steps: list[str], now: str) -> RunState: ...

    def load_state(self, user: str, run_id: str) -> RunState: ...

    def save_state(self, state: RunState) -> None: ...

    def load_request(self, user: str, run_id: str) -> ProposalRequest: ...

    def save_snapshot(self, user: str, run_id: str, snapshot: RetrievalSnapshot) -> None: ...

    def load_snapshot(self, user: str, run_id: str) -> RetrievalSnapshot | None: ...

    def save_section(self, user: str, run_id: str, section: Section) -> None: ...

    def load_sections(self, user: str, run_id: str) -> dict[str, Section]: ...

    def save_draft(self, user: str, run_id: str, draft: Draft) -> None: ...

    def list_runs(self, user: str, limit: int = 50) -> list[RunState]: ...

    def claim(self, user: str, run_id: str) -> RunClaim:
        """run 전용 락. 이미 잡혀 있으면 RunBusy. 잡은 프로세스가 죽으면 풀린다."""
        ...

    def is_alive(self, user: str, run_id: str) -> bool:
        """누군가 이 run 의 락을 잡고 있으면 True (= 실행 중이거나 대기 중)."""
        ...
