"""문제 묶음 JSONL 저장소 (계약 §3) — 봉인 `data/eval/sealed/<suite>.jsonl`(폴더 700·파일 600),
연습 `data/eval/practice/<suite>-<seed>.jsonl`.

문제 본문이 들어 있으므로 `.gitignore`(`/data/`) 아래에만 두고, 봉인 묶음은 개선 작업 중 열람 금지
(docs/eval-protocol.md). 링크는 따라가지 않는다(O_NOFOLLOW).
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from rra.domain.models.eval_problem import EvalProblem

DIR_MODE = 0o700
FILE_MODE = 0o600


class JsonlProblemStore:
    def __init__(self, sealed_dir: str | Path, practice_dir: str | Path):
        self.sealed_dir = Path(sealed_dir)
        self.practice_dir = Path(practice_dir)

    def __repr__(self) -> str:
        return f"JsonlProblemStore({self.sealed_dir}, {self.practice_dir})"

    def sealed_path(self, suite: str) -> Path:
        return self.sealed_dir / f"{suite}.jsonl"

    def practice_path(self, suite: str, seed: int) -> Path:
        return self.practice_dir / f"{suite}-{int(seed)}.jsonl"

    def exists(self, path: Path) -> bool:
        return Path(path).is_file()

    def load(self, path: Path) -> list[EvalProblem]:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        out: list[EvalProblem] = []
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(EvalProblem.model_validate(json.loads(line)))
        return out

    def save(self, path: Path, problems: Sequence[EvalProblem]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
        os.chmod(path.parent, DIR_MODE)
        tmp = path.with_name(f".{path.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for p in problems:
                f.write(json.dumps(p.model_dump(), ensure_ascii=False) + "\n")
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
        return path
