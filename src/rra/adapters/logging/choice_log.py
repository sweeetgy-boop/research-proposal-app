"""② 유사과제 선택 기록 — JSONL 파일(데이터 폴더 feedback/similar_choices.jsonl, 레인 A).

허용 키만 쓴다(원문·개인정보 없음). 파일은 600, 폴더는 700. 같은 프로세스 안의 동시 쓰기는 잠금으로
한 줄씩.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ALLOWED_KEYS = frozenset(
    {
        "at",
        "idea",
        "doc_id",
        "merged_ids",
        "choice",
        "tier",
        "similarity",
        "rerank_score",
        "keywords",
        "rule_blocking",
        "judgment",
        "judged_by",
        "blocking",
        "released",
    }
)


class JsonlChoiceLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        lines = []
        for r in records:
            extra = set(r) - ALLOWED_KEYS
            if extra:
                raise ValueError(f"선택 기록에 허용되지 않은 키: {sorted(extra)}")
            lines.append(json.dumps(r, ensure_ascii=False, sort_keys=True))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.path.parent, 0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")


class MemoryChoiceLog:
    """가짜 모드·테스트 — 데이터 폴더를 건드리지 않는다."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, records: list[dict[str, Any]]) -> None:
        self.records.extend(dict(r) for r in records)
