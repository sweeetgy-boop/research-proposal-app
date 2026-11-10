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

from rra.domain.rules.card_edits import CHOICE_LINE_EXTRA_KEYS

ALLOWED_KEYS = frozenset(
    {
        "at",
        # ADR 0056 후속 — apply([선택 적용]) | generate(생성 요청). 이 키가 없는 옛 줄은 2026-11-04
        # 이전의 생성 요청 기록(generate 로 본다)
        "event",
        "idea",
        "doc_id",
        "merged_ids",
        "choice",
        "source",  # ADR 0056 — user | ai_prefill. 이 키가 없는 옛 줄은 2026-11-04 이전(출처 모름)
        "tier",
        "similarity",
        "rerank_score",
        "keywords",
        "rule_blocking",
        "judgment",
        "judged_by",
        "blocking",
        "released",
        # ADR 0056 2026-11-04 덧붙임 — 시험 계정(배포 확인용 임시 사번) 세션의 줄만 true. 그 밖의
        # 줄에는 키가 없다. `rra feedback stats` 는 기본으로 이 줄을 세지 않는다
        "test",
        # ADR 0065 — 문제 정의 카드 수정 줄(event: card_edit): 항목 이름·변경 전후 80자 요약·
        # 실행한 방법·신호 (domain/rules/card_edits.choice_line)
        *CHOICE_LINE_EXTRA_KEYS,
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
