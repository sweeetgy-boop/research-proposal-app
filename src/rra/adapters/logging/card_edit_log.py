"""문제 정의 카드 수정 짝 — JSONL 파일(데이터 폴더 feedback/card_edits.jsonl, ADR 0065).

`CardEditLogPort` 구현. 허용 칸만 쓴다(`domain/rules/card_edits.EDIT_KEYS` — 가명 ID·해시·항목
이름·변경 전후 글, 이름·연락처는 규칙이 미리 지운다). 파일은 600, 폴더는 700. 같은 프로세스 안의
동시 쓰기는 잠금으로 한 줄씩. `by_user` 는 그 가명 ID 의 줄만 돌려준다.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from rra.domain.rules.card_edits import EDIT_KEYS


def _checked(record: dict[str, Any]) -> dict[str, Any]:
    extra = set(record) - EDIT_KEYS
    if extra:
        raise ValueError(f"수정 기록에 허용되지 않은 키: {sorted(extra)}")
    if not isinstance(record.get("user"), str) or not record["user"]:
        raise ValueError("수정 기록에 가명 ID 가 없습니다")
    return dict(record)


class JsonlCardEditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(_checked(record), ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.path.parent, 0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def by_user(self, user: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not user or limit <= 0:
            return []
        with self._lock:
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        out: list[dict[str, Any]] = []
        for line in reversed(lines):  # 최근 것부터
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("user") == user:
                out.append(row)
                if len(out) >= limit:
                    break
        return out


class MemoryCardEditLog:
    """가짜 모드·테스트 — 데이터 폴더를 건드리지 않는다."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, record: dict[str, Any]) -> None:
        self.records.append(_checked(record))

    def by_user(self, user: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not user or limit <= 0:
            return []
        return [dict(r) for r in reversed(self.records) if r.get("user") == user][:limit]
