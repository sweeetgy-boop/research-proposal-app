"""RunStorePort 구현 — runs/<user>/<run_id>/ 디렉터리 하나가 run 하나.

    runs/.generate.lock                      (전역 슬롯, FlockSlot)
    runs/<user>/<run_id>/state.json          상태·step 기록 (원문 일부 포함: lint 메시지)
                        request.json         제안 입력 (민감)
                        context.json         검색 스냅샷 (청크 본문)
                        sections/<key>.json  근거 검증을 통과한 섹션 체크포인트
                        draft.json           완성 초안
                        confirmed.json       사용자가 확정한 선택값 (선택지 id 만)
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

from rra.adapters.runs._fs import ensure_dir, read_json, write_json
from rra.adapters.runs.locks import FileLockClaim, is_locked, try_lock
from rra.application.ports import RunBusy, RunNotFound
from rra.domain.models import (
    Confirmation,
    Draft,
    ProposalRequest,
    RetrievalSnapshot,
    RunState,
    Section,
    StepRecord,
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
