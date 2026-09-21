"""수동 투입 폴더(inbox) 공통 처리 — 원문 filedrop 과 공개 요약 경로가 함께 쓴다.

- 실패한 파일은 `_quarantine/` 으로 옮기고, 로그에는
  **예외 클래스명과 sha256 접두(또는 무작위 ref)만** 남긴다.
  경로·파일명·예외 메시지·본문은 기록하지 않는다.
- 저장이 끝난 파일은 `acknowledge()` 로 `_done/<sha256>.<fmt>` 로 옮긴다.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from pathlib import Path
from typing import Any

from rra.adapters.sources.alio.filecheck import extension_of

DONE_DIR = "_done"
QUARANTINE_DIR = "_quarantine"
_STEM_UNSAFE = re.compile(r"[^\w-]")


def error_name(exc: BaseException) -> str:
    # ParseRejected 는 자식 쪽 예외 클래스명(식별자 문자만 보장)을 쓴다
    return getattr(exc, "error", None) or type(exc).__name__


def inbox_status(inbox: Path) -> dict[str, int]:
    def count(d: Path) -> int:
        return (
            sum(1 for p in d.iterdir() if p.is_file() and not p.name.startswith("."))
            if d.is_dir()
            else 0
        )

    pending = (
        sum(1 for p in inbox.iterdir() if p.is_file() and not p.name.startswith((".", "_")))
        if inbox.is_dir()
        else 0
    )
    return {
        "pending": pending,
        "done": count(inbox / DONE_DIR),
        "quarantine": count(inbox / QUARANTINE_DIR),
    }


class Inbox:
    def __init__(self, root: Path, *, formats: frozenset[str], logger: logging.Logger, event: str):
        self.root = Path(root)
        self.formats = formats
        self._logger = logger
        self._event = event  # 로그 이벤트 접두 (예: "alio")

    def pending(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.iterdir() if not p.name.startswith((".", "_")))

    def quarantine(self, path: Path, exc: BaseException, *, sha256: str | None) -> None:
        ref = f"sha256:{sha256[:8]}" if sha256 else f"rej:{secrets.token_hex(4)}"
        self._logger.warning("%s.rejected error=%s file=%s", self._event, error_name(exc), ref)
        ext = extension_of(path)
        ext = ext if ext in self.formats else "bin"
        stem = _STEM_UNSAFE.sub("_", path.stem)[:80]
        target = self.root / QUARANTINE_DIR / f"{ref.replace(':', '-')}__{stem}.{ext}"
        self._move(path, target)

    def acknowledge(self, raws: list[dict[str, Any]]) -> None:
        for raw in raws:
            path = Path(raw["_file"])
            if path.parent != self.root:
                continue  # 이 inbox 가 만든 raw 가 아니다
            self._move(path, self.root / DONE_DIR / f"{raw['sha256']}.{raw['fmt']}")

    def _move(self, src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.replace(src, dest)  # 심볼릭 링크면 링크 자체를 옮긴다 (대상은 건드리지 않음)
        except OSError as exc:
            self._logger.warning("%s.move_failed error=%s", self._event, type(exc).__name__)
