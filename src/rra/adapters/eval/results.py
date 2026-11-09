"""평가 결과 JSON 저장소 (계약 §1) — `eval/results/<YYYY-MM-DD>-<suite>[-<label>].json`, 수치만.

`eval/results/` 는 git 에 커밋한다(문제 본문·doc_id 가 없으므로). 쓰기는 원자적 교체.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import date
from pathlib import Path

from rra.domain.models.eval_result import EvalResult

_LABEL_SAFE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


def safe_label(label: str) -> str:
    return _LABEL_SAFE.sub("-", label.strip())[:40].strip("-")


class JsonResultStore:
    def __init__(self, base_dir: str | Path, *, today: date | None = None):
        self.base_dir = Path(base_dir)
        self._today = today

    def default_path(self, result: EvalResult) -> Path:
        day = (self._today or date.today()).isoformat()
        label = safe_label(result.label)
        name = f"{day}-{result.suite}" + (f"-{label}" if label else "") + ".json"
        return self.base_dir / name

    def write(self, result: EvalResult, *, path: Path | None = None) -> Path:
        target = Path(path) if path is not None else self.default_path(result)
        target.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(result.model_dump(), ensure_ascii=False, indent=2) + "\n"
        tmp = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
        return target

    def read(self, path: Path) -> EvalResult:
        return EvalResult.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
