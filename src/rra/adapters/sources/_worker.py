"""격리 파서 프로세스 진입점. `_sandbox.run_parser()` 만 이 모듈을 실행한다.

    python -I -m rra.adapters.sources._worker <fmt> <limits-json>  < 검증된 파일

stdout 으로 JSON 한 개만 낸다:
    {"ok": true, "result": {...}} / {"ok": false, "error": "<ClassName>"}
예외 메시지·트레이스백은 내보내지 않는다 (파일 내용·경로 노출 방지).
파서 모듈은 rlimit 을 건 **뒤에** import 한다.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import resource
import sys
from typing import Any

EXIT_MEMORY = 86  # _sandbox.EXIT_MEMORY 와 같아야 한다 (부모 모듈 import 를 피하려고 복제)
EXIT_INPUT = 87

PARSERS = {
    "pdf": "rra.adapters.sources.alio.extract.pdf",
    "hwpx": "rra.adapters.sources.alio.extract.hwpx",
    "csv": "rra.adapters.sources.alio.extract.csv_catalog",
}
TEST_PARSERS = {
    "_test_echo",
    "_test_sleep",
    "_test_crash",
    "_test_alloc",
    "_test_flood",
    "_test_raise",
    "_test_env",
}


def _setrlimit(which: int, soft: int, hard: int | None = None) -> None:
    try:
        resource.setrlimit(which, (soft, soft if hard is None else hard))
    except (ValueError, OSError):
        pass  # 플랫폼이 거부하는 한도는 부모 쪽 감시(타임아웃·RSS)가 대신한다


def apply_limits(limits: dict[str, Any]) -> None:
    mem = int(limits["mem_mb"]) * 1024 * 1024
    cpu = math.ceil(float(limits["timeout_sec"])) + 1
    _setrlimit(resource.RLIMIT_AS, mem)
    _setrlimit(resource.RLIMIT_DATA, mem)
    _setrlimit(resource.RLIMIT_CPU, cpu, cpu + 5)
    _setrlimit(resource.RLIMIT_FSIZE, 0)  # 파일 쓰기 금지 (stdout 파이프는 해당 없음)
    _setrlimit(resource.RLIMIT_CORE, 0)
    _setrlimit(resource.RLIMIT_NOFILE, 64)


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


def _run_test_parser(fmt: str, data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import time

    if fmt == "_test_echo":
        return {"text": data.decode("utf-8", "replace")}
    if fmt == "_test_sleep":
        time.sleep(3600)
    if fmt == "_test_crash":
        os.abort()
    if fmt == "_test_alloc":
        hog = []
        while True:
            hog.append(bytearray(b"\x01") * (16 * 1024 * 1024))  # 실제로 페이지를 채운다
            time.sleep(0.01)
    if fmt == "_test_flood":
        chunk = b"x" * (1024 * 1024)
        while True:
            sys.stdout.buffer.write(chunk)
    if fmt == "_test_raise":
        raise KeyError("/secret/path/보고서.pdf 내용")  # 메시지는 밖으로 나가면 안 된다
    if fmt == "_test_env":
        return {"env": sorted(os.environ)}
    raise LookupError(fmt)


def main(argv: list[str]) -> int:
    fmt, limits = argv[1], json.loads(argv[2])
    apply_limits(limits)
    cap = int(float(limits["max_input_mb"]) * 1024 * 1024)
    data = sys.stdin.buffer.read(cap + 1)
    if len(data) > cap:
        return EXIT_INPUT
    try:
        if fmt in PARSERS:
            result = importlib.import_module(PARSERS[fmt]).extract(data, limits)
        elif fmt in TEST_PARSERS and limits.get("test_mode"):
            result = _run_test_parser(fmt, data, limits)
        else:
            raise LookupError("unknown format")
    except MemoryError:
        return EXIT_MEMORY
    except Exception as exc:
        _emit({"ok": False, "error": type(exc).__name__})
        return 0
    _emit({"ok": True, "result": result})
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv)
    except MemoryError:
        code = EXIT_MEMORY
    os._exit(code)  # atexit·버퍼 정리 중 추가 실패가 없도록 즉시 종료 (stdout 은 이미 flush)
