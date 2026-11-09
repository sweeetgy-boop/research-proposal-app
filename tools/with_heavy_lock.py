"""무거운 작업 대기열 — 프로세스 간 파일 락(원 저장소 runs/.heavy.lock, FlockSlot 방식)으로 한 번에
하나만 돌린다. worktree 에서 돌려도 같은 잠금 파일을 쓴다(git 공용 디렉터리 기준).

사용: .venv/bin/python tools/with_heavy_lock.py [--wait-log 경로] -- <명령…>
mlx 서버 사용(생성·평가·벤치), 임베딩·재색인, 대량 파싱·OCR, 적재, 측정이 대상이다. 락을 기다린
시간과 시작·끝 시각을 stderr(와 --wait-log 파일)에 남긴다. 명령의 종료 코드를 그대로 돌려준다.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _default_lock() -> Path:
    """기본 잠금 파일 — 원 저장소 `runs/.heavy.lock`. worktree 에서 돌려도 같은 파일을 쓰도록 git
    공용 디렉터리(`git rev-parse --git-common-dir`)의 부모를 기준으로 한다(2026-11-09: worktree 와
    원 저장소에서 각각 돌린 평가 두 건이 다른 잠금을 잡아 16분 겹쳐 돈 뒤). git 이 없으면 cwd 기준."""
    git = shutil.which("git")
    if git:
        try:
            out = subprocess.run(  # noqa: S603 — 고정 인자, 사용자 입력 없음
                [git, "rev-parse", "--git-common-dir"], capture_output=True, text=True, check=True
            ).stdout.strip()
            if out:
                return (Path(out).resolve().parent / "runs" / ".heavy.lock").resolve()
        except (OSError, subprocess.CalledProcessError):
            pass
    return Path("runs/.heavy.lock")


def main(argv: list[str]) -> int:
    wait_log: Path | None = None
    if argv[:1] == ["--wait-log"]:
        wait_log, argv = Path(argv[1]), argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        print("사용: with_heavy_lock.py [--wait-log 경로] -- <명령…>", file=sys.stderr)
        return 2
    lock_path = Path(os.environ.get("RRA_HEAVY_LOCK") or _default_lock())
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
