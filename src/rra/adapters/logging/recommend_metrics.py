"""차별화 과제안 측정 파일 — JSONL(데이터 폴더 cache/recommend_metrics.jsonl, ADR 0055 덧붙임).

추천 호출 한 번 = 한 줄. 칸은 `domain/rules/recommend_metrics.FIELDS` 만
(건수·시간·열거값, 본문 없음). 시험 계정 세션의 줄만 끝에 `"test": true`(`OPTIONAL_FIELDS`).
`ts` 는 응답 시간 파일(`llm_budget.latency.jsonl`)과 같은 모양 — 서버 지역 시각(KST)의 ISO, 초 단위.

- 권한: 폴더 700(`ensure_dir`), 파일 600(O_APPEND·O_NOFOLLOW 로 연다). 같은 프로세스 안은
  잠금으로 한 줄씩.
- 크기 상한: 쓰기 전에 파일이 `max_bytes`(기본 5 MB, 한 줄 약 250바이트 → 2만 회 안팎) 이상이면
  `recommend_metrics.jsonl.1` 로 이름을 바꾸고(옛 `.1` 은 덮어씀) 새 파일에 쓴다 — 많아야 두
  파일, 약 10 MB.
- 쓰기 실패(OSError)는 debug 한 줄만 남기고 삼킨다 — 추천을 막지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from rra.adapters.runs._fs import FILE_MODE, ensure_dir
from rra.domain.rules.recommend_metrics import FIELDS, OPTIONAL_FIELDS, ROW_FIELDS, TEST_FIELD

logger = logging.getLogger("rra.recommend")

MAX_BYTES = 5 * 1024 * 1024
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class JsonlRecommendMetrics:
    def __init__(self, path: str | Path, *, max_bytes: int = MAX_BYTES):
        self.path = Path(path)
        self.max_bytes = max(1, int(max_bytes))

    def __repr__(self) -> str:
        return f"JsonlRecommendMetrics({self.path})"

    def record(self, row: Mapping[str, object]) -> None:
        extra = set(row) - set(ROW_FIELDS) - set(OPTIONAL_FIELDS)
        if extra:  # 허용 칸 밖은 쓰지 않는다 (본문이 섞여 들어오는 길을 막는다)
            raise ValueError(f"측정 줄에 허용되지 않은 키: {sorted(extra)}")
        line: dict[str, object] = {"ts": _now(), **{k: row.get(k) for k in ROW_FIELDS}}
        out = {k: line[k] for k in FIELDS}
        if row.get(TEST_FIELD) is True:  # 시험 계정 세션만 — 그 밖의 줄에는 키가 없다
            out[TEST_FIELD] = True
        body = json.dumps(out, ensure_ascii=False) + "\n"
        try:
            with _LOCK:
                ensure_dir(self.path.parent)
                self._rotate()
                fd = os.open(
                    self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, FILE_MODE
                )
                with os.fdopen(fd, "a", encoding="utf-8") as f:
                    f.write(body)
        except OSError as exc:
            logger.debug("recommend.metrics_failed kind=%s", type(exc).__name__)

    def _rotate(self) -> None:
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size >= self.max_bytes:
            os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
