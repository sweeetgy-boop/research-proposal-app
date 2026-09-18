"""B. 외부 파일 파서 격리 실행기.

파서는 항상 별도 프로세스(`python -I -m rra.adapters.sources._worker`)에서 돈다.

- 입력: 부모가 이미 검증한 fd 를 그대로 자식 stdin 으로 넘긴다. 경로는 넘기지 않는다
  (검사한 파일과 파싱하는 파일이 같음을 보장, TOCTOU 제거).
- 환경: 최소 env(LANG·PATH)만. `RRA_*` 비밀은 자식에 전달되지 않는다 (D).
- stderr 는 버린다. 자식 트레이스백에 파일 내용이 섞일 수 있다.
- 상한: 벽시계 타임아웃(프로세스 그룹 kill), stdout 크기, 메모리.
  메모리는 두 겹이다. 자식이 RLIMIT_AS/DATA 를 걸고(Linux·WSL 에서 유효),
  부모가 자식 RSS 를 주기적으로 읽어 넘으면 kill 한다(macOS 는 RLIMIT_AS 를 강제하지 않으므로
  이쪽이 실제 방어선. 샘플링 간격 사이의 순간 초과는 못 잡는 best-effort).
- 실패는 `SandboxError` 하위 클래스로만 올라온다. 메시지에 경로·내용을 넣지 않는다.
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import json
import os
import signal
import sys
from dataclasses import asdict, dataclass
from typing import Any

WORKER_MODULE = "rra.adapters.sources._worker"
EXIT_MEMORY = 86  # 자식이 MemoryError 를 만나면 이 코드로 끝낸다
EXIT_INPUT = 87  # 입력이 상한을 넘음
POLL_SEC = 0.05


class SandboxError(RuntimeError):
    """격리 파싱 실패. 메시지에는 경로·내용이 없다."""


class ParseTimeout(SandboxError):
    pass


class ParseCrashed(SandboxError):
    pass


class ParseMemoryExceeded(SandboxError):
    pass


class OutputTooLarge(SandboxError):
    pass


class InputTooLarge(SandboxError):
    pass


class ParseRejected(SandboxError):
    """파서가 예외로 거부함. `error` 는 자식 쪽 예외 클래스명 (식별자 문자만)."""

    def __init__(self, error: str):
        self.error = error if error.isidentifier() else "Unknown"
        super().__init__(self.error)


@dataclass(frozen=True)
class SandboxLimits:
    timeout_sec: float = 120.0
    mem_mb: int = 2048
    max_input_mb: float = 200.0
    max_output_mb: float = 32.0
    max_zip_ratio: int = 100
    max_zip_entries: int = 2000
    max_pdf_pages: int = 600
    max_text_chars: int = 5_000_000
    max_csv_rows: int = 200_000
    test_mode: bool = False  # tests/ 전용 가짜 파서(_test_*) 허용

    @classmethod
    def from_security_config(cls, security: dict[str, Any]) -> SandboxLimits:
        f = security.get("file_limits") or {}
        return cls(
            timeout_sec=float(f.get("parse_timeout_sec", 120)),
            mem_mb=int(f.get("parse_mem_mb", 2048)),
            max_input_mb=float(f.get("max_file_mb", 200)),
            max_output_mb=float(f.get("max_output_mb", 32)),
            max_zip_ratio=int(f.get("max_zip_ratio", 100)),
            max_zip_entries=int(f.get("max_zip_entries", 2000)),
            max_pdf_pages=int(f.get("max_pdf_pages", 600)),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def child_env() -> dict[str, str]:
    return {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": os.defpath}


async def run_parser(fd: int, fmt: str, limits: SandboxLimits) -> dict[str, Any]:
    """fd(읽기 위치 0)를 자식 파서에 넘기고 결과 dict 를 돌려준다."""
    if not fmt.replace("_", "").isalnum():
        raise ValueError("잘못된 형식 이름")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        WORKER_MODULE,
        fmt,
        limits.to_json(),
        stdin=fd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=child_env(),
        cwd="/",
        start_new_session=True,
    )
    cap = int(limits.max_output_mb * 1024 * 1024)
    mem = limits.mem_mb * 1024 * 1024
    reader = asyncio.create_task(_read_capped(proc.stdout, cap))
    monitor = asyncio.create_task(_watch_memory(proc.pid, mem))
    try:
        async with asyncio.timeout(limits.timeout_sec):
            done, _ = await asyncio.wait({reader, monitor}, return_when=asyncio.FIRST_COMPLETED)
            if monitor in done:
                monitor.result()  # ParseMemoryExceeded
            out = reader.result()  # OutputTooLarge 가능
            rc = await proc.wait()
    except TimeoutError:
        raise ParseTimeout("timeout") from None
    finally:
        for task in (reader, monitor):
            task.cancel()
        await asyncio.gather(reader, monitor, return_exceptions=True)  # 취소 완료까지 대기
        if proc.returncode is None:
            _kill_group(proc.pid)
            # 3.12 의 Process.wait() 는 파이프가 닫혀야 끝난다. 읽기를 멈춘 채로 두면
            # 버퍼가 찬 stdout 이 EOF 에 닿지 못해 영원히 기다린다 → 남은 출력을 버리며 비운다.
            await _drain(proc.stdout)
            await proc.wait()
    return _interpret(rc, out)


def _interpret(rc: int, out: bytes) -> dict[str, Any]:
    if rc == EXIT_MEMORY:
        raise ParseMemoryExceeded("memory")
    if rc == EXIT_INPUT:
        raise InputTooLarge("input")
    if rc in (-signal.SIGXCPU, -signal.SIGKILL):
        raise ParseTimeout("cpu")  # RLIMIT_CPU 초과 (SIGKILL 은 hard limit)
    if rc != 0:
        raise ParseCrashed("crashed")
    try:
        payload = json.loads(out)
    except ValueError:
        raise ParseCrashed("bad output") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        raise ParseCrashed("bad output")
    if not payload["ok"]:
        raise ParseRejected(str(payload.get("error", "Unknown")))
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ParseCrashed("bad output")
    return result


async def _read_capped(stream: asyncio.StreamReader | None, cap: int) -> bytes:
    if stream is None:  # PIPE 로 열었으므로 일어나지 않는다
        raise ParseCrashed("no stdout")
    buf = bytearray()
    while chunk := await stream.read(65536):
        buf.extend(chunk)
        if len(buf) > cap:
            raise OutputTooLarge("output")
    return bytes(buf)


async def _drain(stream: asyncio.StreamReader | None) -> None:
    if stream is not None:
        while await stream.read(65536):
            pass


async def _watch_memory(pid: int, limit: int) -> None:
    while True:
        rss = rss_bytes(pid)
        if rss is not None and rss > limit:
            raise ParseMemoryExceeded("memory")
        await asyncio.sleep(POLL_SEC)


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)  # start_new_session=True → pgid == pid
    except (ProcessLookupError, PermissionError):
        pass


# ── 자식 RSS 읽기 (플랫폼별) ─────────────────────────────
def rss_bytes(pid: int) -> int | None:
    if sys.platform == "darwin":
        return _rss_darwin(pid)
    return _rss_linux(pid)


def _rss_linux(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/statm", encoding="ascii") as f:
            resident_pages = int(f.read().split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return resident_pages * os.sysconf("SC_PAGE_SIZE")


_RUSAGE_INFO_V2 = 2
_PHYS_FOOTPRINT_OFFSET = 72  # rusage_info_v2: uuid[16] + u64 × 7 → ri_phys_footprint
_libproc: Any = None


def _rss_darwin(pid: int) -> int | None:
    global _libproc
    if _libproc is None:
        path = ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib"
        try:
            _libproc = ctypes.CDLL(path, use_errno=True)
        except OSError:
            _libproc = False
    if not _libproc:
        return None
    buf = ctypes.create_string_buffer(256)
    if _libproc.proc_pid_rusage(ctypes.c_int(pid), ctypes.c_int(_RUSAGE_INFO_V2), buf) != 0:
        return None
    return int.from_bytes(buf.raw[_PHYS_FOOTPRINT_OFFSET : _PHYS_FOOTPRINT_OFFSET + 8], "little")
