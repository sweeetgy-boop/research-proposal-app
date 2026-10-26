"""로컬 LLM 서버(mlx_lm.server) 프로세스의 RSS 를 `ps` 로 읽는다 (벤치 최대 메모리 보고용)."""

from __future__ import annotations

import subprocess  # noqa: S404 - 고정 인자(ps -axo ...)만 실행한다


def server_rss_mb(pattern: str = "mlx_lm.server") -> float | None:
    """pattern 이 든 프로세스들의 RSS 합(MB). 없으면 None. 실패해도 예외를 내지 않는다."""
    try:
        out = subprocess.run(  # noqa: S603
            ["/bin/ps", "-axo", "rss=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    total_kb = 0
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and pattern in parts[1] and parts[0].isdigit():
            total_kb += int(parts[0])
    return round(total_kb / 1024, 1) if total_kb else None
