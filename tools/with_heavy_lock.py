"""무거운 작업 대기열 — 프로세스 간 파일 락(runs/.heavy.lock, FlockSlot 방식)으로 한 번에 하나만
돌린다.

사용: .venv/bin/python tools/with_heavy_lock.py [--wait-log 경로] -- <명령…>
mlx 서버 사용(생성·평가·벤치), 임베딩·재색인, 대량 파싱·OCR, 적재, 측정이 대상이다. 락을 기다린
시간과 시작·끝 시각을 stderr(와 --wait-log 파일)에 남긴다. 명령의 종료 코드를 그대로 돌려준다.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    wait_log: Path | None = None
    if argv[:1] == ["--wait-log"]:
        wait_log, argv = Path(argv[1]), argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        print("사용: with_heavy_lock.py [--wait-log 경로] -- <명령…>", file=sys.stderr)
        return 2
    lock_path = Path(os.environ.get("RRA_HEAVY_LOCK", "runs/.heavy.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # 다른 프로세스가 쥐고 있으면 여기서 기다린다
        waited = time.time() - started
        line = f"[heavy] 대기 {waited:.0f}s → 시작 {time.strftime('%H:%M:%S')}: {' '.join(argv)}"
        print(line, file=sys.stderr)
        if wait_log:
            wait_log.parent.mkdir(parents=True, exist_ok=True)
            wait_log.open("a", encoding="utf-8").write(line + "\n")
        code = subprocess.call(argv)  # noqa: S603 — 호출자가 준 명령을 그대로 실행한다
        done = f"[heavy] 끝 {time.strftime('%H:%M:%S')} 종료 코드 {code}: {argv[0]}"
        print(done, file=sys.stderr)
        if wait_log:
            wait_log.open("a", encoding="utf-8").write(done + "\n")
        return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
