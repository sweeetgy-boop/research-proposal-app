from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rra.domain.models import (
    Confirmation,
    Draft,
    DraftVersion,
    ProposalRequest,
    RetrievalSnapshot,
    ReviewRound,
    RunState,
    Section,
    UsageRecord,
    VersionMarks,
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

    # 항목 17 — 초안이 있는 run 에서 ①·② 입력을 바꿔 다시 쓸 때만 덮어쓴다
    def save_request(self, user: str, run_id: str, req: ProposalRequest) -> None: ...

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

    # 항목 21 상태 표시(확인 기록) — 버전 파일은 그대로 두고 버전마다 표시 파일(marks_vN)에 쌓는다
    def save_marks(self, user: str, run_id: str, marks: VersionMarks) -> None: ...

    def load_marks(self, user: str, run_id: str, version: int) -> VersionMarks | None: ...

    def save_outline(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        """Q2 섹션 설계도(Outline.model_dump) — outline.json."""
        ...

    def load_outline(self, user: str, run_id: str) -> dict[str, Any] | None: ...

    def save_candidates(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        """Q7 핵심 섹션의 고르지 않은 후보 — candidates.json (버전에 넣지 않는다)."""
        ...

    def load_candidates(self, user: str, run_id: str) -> dict[str, Any] | None: ...

    def save_working(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        """④ 임시 저장(autosave) — 서버 작업 사본 draft_working.json (버전 아님)."""
        ...

    def load_working(self, user: str, run_id: str) -> dict[str, Any] | None: ...

    def clear_working(self, user: str, run_id: str) -> None: ...

    def save_recommendations(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        """차별화 과제 추천 결과 전체를 run 에 복사 (recommendations.json)."""
        ...

    def load_recommendations(self, user: str, run_id: str) -> dict[str, Any] | None: ...

    def save_idea_versions(self, user: str, run_id: str, data: list[dict[str, Any]]) -> None:
        """② 과제안 버전(원래 아이디어·고른 카드·직접 고친 안)을 run 에 복사
        (idea_versions.json)."""
        ...

    def load_idea_versions(self, user: str, run_id: str) -> list[dict[str, Any]] | None: ...

    # U3 섹션 다시 쓰기 후보(rewrite_<key>.json)·제안자 보완 메모(proposer_notes.json)
    def save_rewrite(self, user: str, run_id: str, key: str, data: dict[str, Any]) -> None: ...

    def load_rewrite(self, user: str, run_id: str, key: str) -> dict[str, Any] | None: ...

    def clear_rewrite(self, user: str, run_id: str, key: str) -> None: ...

    def save_notes(self, user: str, run_id: str, data: dict[str, Any]) -> None: ...

    def load_notes(self, user: str, run_id: str) -> dict[str, Any] | None: ...

    # U8 시범운영 측정 기록 (usage.json). 개인정보·본문 없음
    def save_usage(self, user: str, run_id: str, usage: UsageRecord) -> None: ...

    def load_usage(self, user: str, run_id: str) -> UsageRecord | None: ...

    def save_figure_image(self, user: str, run_id: str, sha: str, data: bytes, mime: str) -> None:
        """[G] 그림 파일(채택 그림·밑그림)을 해시 이름으로 저장 — 어느 버전이든 해시로 참조한다."""
        ...

    def load_figure_image(self, user: str, run_id: str, sha: str) -> tuple[bytes, str] | None:
        """(바이트, mime) 또는 None."""
        ...

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
