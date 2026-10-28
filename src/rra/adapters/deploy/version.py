"""현재 배포 버전 — 화면 하단·`GET /healthz` 가 보여 준다 (시범 운영, 2026-10-28).

우선순위:
1. `<data_dir>/deploy/version.json` — `tools/deploy.sh` 가 재시작 직전에 쓴다
   {"commit": 전체 해시, "short": 7자, "deployed_at": ISO 시각, "prs": ["#61", …]}.
2. 없으면 저장소의 `git rev-parse HEAD` + 프로세스 시작 시각(source=git). 개발기에서 `rra api` 를
   손으로 띄웠을 때.
값은 공개 저장소의 커밋 해시와 시각뿐이다(비밀 없음). 읽기 실패는 조용히 {"source": "unknown"}.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HEX = re.compile(r"^[0-9a-f]{7,40}$")
SHORT = 7


def _git_head(repo_root: Path) -> str:
    git = shutil.which("git")
    if not git:
        return ""
    try:
        out = subprocess.run(  # noqa: S603 — 고정 인자, 사용자 입력 없음
            [git, "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    value = out.stdout.strip().lower()
    return value if out.returncode == 0 and _HEX.match(value) else ""


def read_version(
    path: Path, *, repo_root: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """{"commit", "short", "deployed_at", "prs", "source"} — 값이 없으면 빈 문자열·빈 목록."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and _HEX.match(str(data.get("commit", "")).lower()):
        commit = str(data["commit"]).lower()
        prs = [str(p) for p in (data.get("prs") or []) if isinstance(p, str | int)][:50]
        return {
            "commit": commit,
            "short": commit[:SHORT],
            "deployed_at": str(data.get("deployed_at") or ""),
            "prs": prs,
            "source": "deploy",
        }
    head = _git_head(repo_root) if repo_root else ""
    started = (now or datetime.now(UTC)).astimezone().isoformat(timespec="seconds")
    source = "git" if head else "unknown"
    return {
        "commit": head,
        "short": head[:SHORT],
        "deployed_at": started,
        "prs": [],
        "source": source,
    }
