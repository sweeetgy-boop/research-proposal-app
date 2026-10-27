"""용어 후보 YAML 쓰기 (P2-9). 후보 파일만 적는다 — config/overlap.yaml 은 건드리지 않는다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

HEADER = (
    "# 자동 생성된 후보 목록 — config/overlap.yaml 에 자동 반영되지 않는다. 사람이 검토해 옮긴다.\n"
    "# 만든 명령: rra terms candidates\n"
)


def write_candidates(out_dir: Path, payloads: dict[str, dict[str, Any]]) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, payload in payloads.items():
        if "/" in name or name.startswith("."):
            raise ValueError("후보 파일 이름이 잘못되었습니다")
        target = out_dir / name
        body = HEADER + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
        written.append(target)
    return written
