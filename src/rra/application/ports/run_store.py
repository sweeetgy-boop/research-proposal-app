from __future__ import annotations

from typing import Protocol, runtime_checkable

from rra.domain.models import (
    Confirmation,
    Draft,
    DraftVersion,
    ProposalRequest,
    RetrievalSnapshot,
    ReviewRound,
    RunState,
    Section,
)


class RunNotFound(LookupError):
    """해당 사용자에게 그런 run 이 없다 (다른 사용자의 run 도 여기에 해당)."""


class RunBusy(RuntimeError):
    """다른 실행(같은 프로세스든 다른 프로세스든)이 이 run 을 잡고 있다."""


@runtime_checkable
class RunClaim(Protocol):
    def release(self) -> None: ...


@runtime_checkable
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

    def save_confirmation(self, user: str, run_id: str, confirmation: Confirmation) -> None:
        """사용자가 확정한 선택값 (선택지 id 만)."""
        ...

    def load_confirmation(self, user: str, run_id: str) -> Confirmation | None: ...

    # [5] 초안 버전(draft_vN)·검토 차수(review_rN). 모두 보존, 덮어쓰지 않는다.
    def save_version(self, user: str, run_id: str, version: DraftVersion) -> None: ...

    def load_version(self, user: str, run_id: str, version: int) -> DraftVersion | None: ...

    def list_versions(self, user: str, run_id: str) -> list[int]: ...

    def save_review(self, user: str, run_id: str, review: ReviewRound) -> None: ...

    def load_review(self, user: str, run_id: str, round_no: int) -> ReviewRound | None: ...

    def list_reviews(self, user: str, run_id: str) -> list[int]: ...

    def list_runs(self, user: str, limit: int = 50) -> list[RunState]: ...

    def claim(self, user: str, run_id: str) -> RunClaim:
        """run 전용 락. 이미 잡혀 있으면 RunBusy. 잡은 프로세스가 죽으면 풀린다."""
        ...

    def is_alive(self, user: str, run_id: str) -> bool:
        """누군가 이 run 의 락을 잡고 있으면 True (= 실행 중이거나 대기 중)."""
        ...

    def list_users(self) -> list[str]:
        """run 이 하나라도 있는 사용자 목록 (보존기간 삭제용)."""
        ...

    def delete_run(self, user: str, run_id: str) -> None:
        """run 폴더(상태·입력·초안·manifest)를 통째로 지운다. 없으면 RunNotFound."""
        ...
