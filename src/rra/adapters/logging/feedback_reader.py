"""FeedbackReaderPort 구현 — JSONL 두 파일을 읽기만 한다 (2026-11-04, ADR 0056 덧붙임).

- 선택 기록 `<data_dir>/feedback/similar_choices.jsonl`, 과제안 측정 `<data_dir>/cache/
  recommend_metrics.jsonl`(5 MB 회전으로 생긴 `.1` 을 먼저 읽는다).
- 쓰기·권한 변경·폴더 생성 없음. 링크는 따라가지 않는다(O_NOFOLLOW). JSON 객체가 아닌 줄은
  개수만 센다(내용은 어디에도 내보내지 않는다).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rra.application.ports.feedback_reader import JsonlRows

ROTATED_SUFFIX = ".1"


def _read(paths: list[Path]) -> JsonlRows:
    rows: list[dict[str, Any]] = []
    found = False
    bad = 0
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            continue
        found = True
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    bad += 1
    return JsonlRows(rows=tuple(rows), found=found, unreadable=bad)


class JsonlFeedbackReader:
    def __init__(self, choice_path: str | Path, metrics_path: str | Path):
        self.choice_path = Path(choice_path)
        self.metrics_path = Path(metrics_path)

    def __repr__(self) -> str:
        return f"JsonlFeedbackReader({self.choice_path}, {self.metrics_path})"

    def choice_rows(self) -> JsonlRows:
        return _read([self.choice_path])

    def metrics_rows(self) -> JsonlRows:
        rotated = self.metrics_path.with_name(self.metrics_path.name + ROTATED_SUFFIX)
        return _read([rotated, self.metrics_path])
