"""RunStorePort 구현 — runs/<user>/<run_id>/ 디렉터리 하나가 run 하나.

    runs/.generate.lock                      (전역 슬롯, FlockSlot)
    runs/<user>/<run_id>/state.json          상태·step 기록 (원문 일부 포함: lint 메시지)
                        request.json         제안 입력 (민감)
                        context.json         검색 스냅샷 (청크 본문)
                        sections/<key>.json  근거 검증을 통과한 섹션 체크포인트
                        draft.json           완성 초안
                        confirmed.json       사용자가 확정한 선택값 (선택지 id 만)
                        versions/draft_vN.json  초안 버전 (v1=로컬 초안, 편집·되돌리기마다 +1)
                        reviews/review_rN.json  검토 차수 결과 (의견·수정안·전송 범위)
                        manifest.json        해시·id 만 (FileRunLog)
                        .lock                run 락 (살아있는 실행 표시)

user·run_id·section key 는 정규식으로 검증한 뒤에만 경로에 쓴다. 디렉터리 700, 파일 600.
개인정보(제안자 성명·연락처)는 저장하지 않는다 — ProposalRequest 에 그런 필드가 없다.
"""

from __future__ import annotations

import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import ensure_dir, read_json, write_json
from rra.adapters.runs.locks import FileLockClaim, is_locked, try_lock
from rra.application.ports import RunBusy, RunNotFound
from rra.domain.models import (
    Confirmation,
    Draft,
    DraftVersion,
    ProposalRequest,
    RetrievalSnapshot,
    ReviewRound,
    RunState,
    Section,
    StepRecord,
    UsageRecord,
)
from rra.domain.models.run import is_valid_run_id

_USER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_SECTION = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class FileRunStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def __repr__(self) -> str:
        return "FileRunStore()"

    # ── 경로 ─────────────────────────────────────────────
    def _user_dir(self, user: str) -> Path:
        if not _USER.match(user):
            raise ValueError("user 형식이 올바르지 않습니다.")
        return self.root / user

    def _run_dir(self, user: str, run_id: str, *, must_exist: bool = True) -> Path:
        if not is_valid_run_id(run_id):
            raise RunNotFound("run_id 형식이 올바르지 않습니다.")
        path = self._user_dir(user) / run_id
        if must_exist and not (path / "state.json").is_file():
            raise RunNotFound("run 이 없습니다.")
        return path

    # ── 생성·상태 ────────────────────────────────────────
    def create(self, user: str, req: ProposalRequest, steps: list[str], now: str) -> RunState:
        ensure_dir(self.root)
        ensure_dir(self._user_dir(user))
        while True:
            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            run_id = f"{stamp}-{secrets.token_hex(4)}"
            path = self._run_dir(user, run_id, must_exist=False)
            if not path.exists():
                break
        ensure_dir(path)
        ensure_dir(path / "sections")
        state = RunState(
            run_id=run_id,
            user=user,
            steps=[StepRecord(name=n) for n in steps],
            created_at=now,
            updated_at=now,
        )
        write_json(path / "request.json", req.model_dump(mode="json"))
        write_json(path / "state.json", state.model_dump(mode="json"))
        return state

    def load_state(self, user: str, run_id: str) -> RunState:
        return RunState.model_validate(read_json(self._run_dir(user, run_id) / "state.json"))

    def save_state(self, state: RunState) -> None:
        path = self._run_dir(state.user, state.run_id)
        write_json(path / "state.json", state.model_dump(mode="json"))

    def load_request(self, user: str, run_id: str) -> ProposalRequest:
        return ProposalRequest.model_validate(
            read_json(self._run_dir(user, run_id) / "request.json")
        )

    # ── 체크포인트 ───────────────────────────────────────
    def save_snapshot(self, user: str, run_id: str, snapshot: RetrievalSnapshot) -> None:
        write_json(self._run_dir(user, run_id) / "context.json", snapshot.model_dump(mode="json"))

    def load_snapshot(self, user: str, run_id: str) -> RetrievalSnapshot | None:
        path = self._run_dir(user, run_id) / "context.json"
        return RetrievalSnapshot.model_validate(read_json(path)) if path.is_file() else None

    def save_section(self, user: str, run_id: str, section: Section) -> None:
        if not _SECTION.match(section.key):
            raise ValueError("section key 형식이 올바르지 않습니다.")
        path = ensure_dir(self._run_dir(user, run_id) / "sections")
        write_json(path / f"{section.key}.json", section.model_dump(mode="json"))

    def load_sections(self, user: str, run_id: str) -> dict[str, Section]:
        path = self._run_dir(user, run_id) / "sections"
        out: dict[str, Section] = {}
        if path.is_dir():
            for f in sorted(path.glob("*.json")):
                if _SECTION.match(f.stem):
                    section = Section.model_validate(read_json(f))
                    if section.key == f.stem:
                        out[section.key] = section
        return out

    def save_draft(self, user: str, run_id: str, draft: Draft) -> None:
        write_json(self._run_dir(user, run_id) / "draft.json", draft.model_dump(mode="json"))

    def save_confirmation(self, user: str, run_id: str, confirmation: Confirmation) -> None:
        for key in confirmation.choices:
            if not _SECTION.match(key):
                raise ValueError("section key 형식이 올바르지 않습니다.")
        write_json(
            self._run_dir(user, run_id) / "confirmed.json", confirmation.model_dump(mode="json")
        )

    def load_confirmation(self, user: str, run_id: str) -> Confirmation | None:
        path = self._run_dir(user, run_id) / "confirmed.json"
        return Confirmation.model_validate(read_json(path)) if path.is_file() else None

    # ── [5] 버전·검토 ────────────────────────────────────
    @staticmethod
    def _number(value: int, what: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 10_000:
            raise ValueError(f"{what} 번호가 올바르지 않습니다.")
        return value

    def save_version(self, user: str, run_id: str, version: DraftVersion) -> None:
        n = self._number(version.version, "버전")
        path = ensure_dir(self._run_dir(user, run_id) / "versions")
        write_json(path / f"draft_v{n}.json", version.model_dump(mode="json"))

    def load_version(self, user: str, run_id: str, version: int) -> DraftVersion | None:
        n = self._number(version, "버전")
        path = self._run_dir(user, run_id) / "versions" / f"draft_v{n}.json"
        return DraftVersion.model_validate(read_json(path)) if path.is_file() else None

    def list_versions(self, user: str, run_id: str) -> list[int]:
        return self._numbers(self._run_dir(user, run_id) / "versions", "draft_v")

    def save_working(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        write_json(self._run_dir(user, run_id) / "draft_working.json", data)

    def load_working(self, user: str, run_id: str) -> dict[str, Any] | None:
        path = self._run_dir(user, run_id) / "draft_working.json"
        return read_json(path) if path.is_file() else None

    def clear_working(self, user: str, run_id: str) -> None:
        path = self._run_dir(user, run_id) / "draft_working.json"
        if path.is_file():
            path.unlink()

    def save_recommendations(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        write_json(self._run_dir(user, run_id) / "recommendations.json", data)

    def load_recommendations(self, user: str, run_id: str) -> dict[str, Any] | None:
        path = self._run_dir(user, run_id) / "recommendations.json"
        return read_json(path) if path.is_file() else None

    # ── U3 다시 쓰기 후보·보완 메모 / U8 usage ─────────────────
    def _rewrite_path(self, user: str, run_id: str, key: str) -> Path:
        if not _SECTION.match(key):
            raise ValueError("section key 형식이 올바르지 않습니다.")
        return ensure_dir(self._run_dir(user, run_id) / "rewrites") / f"rewrite_{key}.json"

    def save_rewrite(self, user: str, run_id: str, key: str, data: dict[str, Any]) -> None:
        write_json(self._rewrite_path(user, run_id, key), data)

    def load_rewrite(self, user: str, run_id: str, key: str) -> dict[str, Any] | None:
        path = self._rewrite_path(user, run_id, key)
        return read_json(path) if path.is_file() else None

    def clear_rewrite(self, user: str, run_id: str, key: str) -> None:
        path = self._rewrite_path(user, run_id, key)
        if path.is_file():
            path.unlink()

    def save_notes(self, user: str, run_id: str, data: dict[str, Any]) -> None:
        write_json(self._run_dir(user, run_id) / "proposer_notes.json", data)

    def load_notes(self, user: str, run_id: str) -> dict[str, Any] | None:
        path = self._run_dir(user, run_id) / "proposer_notes.json"
        return read_json(path) if path.is_file() else None

    def save_usage(self, user: str, run_id: str, usage: UsageRecord) -> None:
        write_json(self._run_dir(user, run_id) / "usage.json", usage.model_dump(mode="json"))

    def load_usage(self, user: str, run_id: str) -> UsageRecord | None:
        path = self._run_dir(user, run_id) / "usage.json"
        return UsageRecord.model_validate(read_json(path)) if path.is_file() else None

    def save_review(self, user: str, run_id: str, review: ReviewRound) -> None:
        n = self._number(review.round, "차수")
        path = ensure_dir(self._run_dir(user, run_id) / "reviews")
        write_json(path / _review_file(n), review.model_dump(mode="json"))

    def load_review(self, user: str, run_id: str, round_no: int) -> ReviewRound | None:
        n = self._number(round_no, "차수")
        folder = self._run_dir(user, run_id) / "reviews"
        for name in (_review_file(n), f"review_r{n}.json"):  # 새 이름 → 옛 이름(review_rN)
            path = folder / name
            if path.is_file():
                data = read_json(path)
                data.setdefault("kind", "draft" if n == 1 else "final")
                return ReviewRound.model_validate(data)
        return None

    def list_reviews(self, user: str, run_id: str) -> list[int]:
        folder = self._run_dir(user, run_id) / "reviews"
        if not folder.is_dir():
            return []
        rounds: set[int] = set()
        for p in folder.glob("*.json"):
            n = _review_round(p.name)
            if n is not None:
                rounds.add(n)
        return sorted(rounds)

    @staticmethod
    def _numbers(directory: Path, prefix: str) -> list[int]:
        if not directory.is_dir():
            return []
        found = []
        for f in directory.glob(f"{prefix}*.json"):
            tail = f.stem[len(prefix) :]
            if tail.isdigit():
                found.append(int(tail))
        return sorted(found)

    def list_runs(self, user: str, limit: int = 50) -> list[RunState]:
        base = self._user_dir(user)
        if not base.is_dir():
            return []
        ids = sorted((p.name for p in base.iterdir() if is_valid_run_id(p.name)), reverse=True)
        out: list[RunState] = []
        for run_id in ids[:limit]:
            try:
                out.append(self.load_state(user, run_id))
            except (RunNotFound, ValueError):
                continue  # 만들다 만 디렉터리·깨진 상태 파일은 건너뛴다
        return out

    def list_users(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and _USER.match(p.name))

    def delete_run(self, user: str, run_id: str) -> None:
        """run 디렉터리 삭제. 경로는 검증된 user·run_id 로만 만들고 root 안인지 다시 확인한다."""
        path = self._run_dir(user, run_id)
        if path.resolve().parent.parent != self.root.resolve():
            raise RunNotFound("run 경로가 저장소 밖입니다.")
        shutil.rmtree(path)

    # ── 락 ───────────────────────────────────────────────
    def claim(self, user: str, run_id: str) -> FileLockClaim:
        fd = try_lock(self._run_dir(user, run_id) / ".lock")
        if fd is None:
            raise RunBusy("다른 실행이 이 run 을 잡고 있습니다.")
        return FileLockClaim(fd)

    def is_alive(self, user: str, run_id: str) -> bool:
        return is_locked(self._run_dir(user, run_id) / ".lock")


def _review_file(round_no: int) -> str:
    """round 1 = 1차 검토(review_draft.json), round n ≥ 2 = 최종 검토(review_final_r{n-1}.json)."""
    return "review_draft.json" if round_no == 1 else f"review_final_r{round_no - 1}.json"


_LEGACY_REVIEW = re.compile(r"^review_r(\d+)\.json$")
_FINAL_REVIEW = re.compile(r"^review_final_r(\d+)\.json$")


def _review_round(name: str) -> int | None:
    if name == "review_draft.json":
        return 1
    if m := _FINAL_REVIEW.match(name):
        return int(m.group(1)) + 1
    if m := _LEGACY_REVIEW.match(name):
        return int(m.group(1))
    return None
