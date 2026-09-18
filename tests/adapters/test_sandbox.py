"""B. 격리 파서 실행기 — 가짜 파서(test_mode)로 타임아웃·크래시·메모리·출력 상한을 검증."""

import os
import sys

import pytest

from rra.adapters.sources._sandbox import (
    InputTooLarge,
    OutputTooLarge,
    ParseCrashed,
    ParseMemoryExceeded,
    ParseRejected,
    ParseTimeout,
    SandboxLimits,
    rss_bytes,
    run_parser,
)

LIMITS = SandboxLimits(timeout_sec=10, mem_mb=256, max_input_mb=1, max_output_mb=1, test_mode=True)


@pytest.fixture
def input_fd(tmp_path):
    fds = []

    def make(data: bytes = b"hello"):
        path = tmp_path / f"in{len(fds)}"
        path.write_bytes(data)
        fd = os.open(path, os.O_RDONLY)
        fds.append(fd)
        return fd

    yield make
    for fd in fds:
        os.close(fd)


async def test_echo_roundtrip(input_fd):
    assert await run_parser(input_fd("안녕".encode()), "_test_echo", LIMITS) == {"text": "안녕"}


async def test_timeout_kills_child(input_fd):
    limits = SandboxLimits(timeout_sec=0.5, test_mode=True)
    with pytest.raises(ParseTimeout):
        await run_parser(input_fd(), "_test_sleep", limits)


async def test_crash_does_not_propagate(input_fd):
    with pytest.raises(ParseCrashed):
        await run_parser(input_fd(), "_test_crash", LIMITS)
    # 본체는 그대로 다음 파싱을 할 수 있다
    assert await run_parser(input_fd(b"ok"), "_test_echo", LIMITS) == {"text": "ok"}


async def test_memory_limit(input_fd):
    limits = SandboxLimits(timeout_sec=20, mem_mb=128, test_mode=True)
    with pytest.raises(ParseMemoryExceeded):
        await run_parser(input_fd(), "_test_alloc", limits)


async def test_output_cap(input_fd):
    with pytest.raises(OutputTooLarge):
        await run_parser(input_fd(), "_test_flood", LIMITS)


async def test_input_cap(input_fd):
    with pytest.raises(InputTooLarge):
        await run_parser(input_fd(b"x" * (1024 * 1024 + 10)), "_test_echo", LIMITS)


async def test_parser_exception_keeps_only_class_name(input_fd):
    with pytest.raises(ParseRejected) as info:
        await run_parser(input_fd(), "_test_raise", LIMITS)
    assert info.value.error == "KeyError"
    assert "secret" not in str(info.value) and "보고서" not in str(info.value)


async def test_child_env_has_no_secrets(input_fd, monkeypatch):
    monkeypatch.setenv("RRA_NTIS_KEY", "SECRET")
    env = (await run_parser(input_fd(), "_test_env", LIMITS))["env"]
    assert not any(k.startswith("RRA_") for k in env)


async def test_test_parsers_disabled_without_test_mode(input_fd):
    with pytest.raises(ParseRejected) as info:
        await run_parser(input_fd(), "_test_echo", SandboxLimits())
    assert info.value.error == "LookupError"


async def test_bad_format_name_rejected_before_spawn(input_fd):
    with pytest.raises(ValueError):
        await run_parser(input_fd(), "../x", LIMITS)


def test_rss_of_self_is_readable():
    rss = rss_bytes(os.getpid())
    assert rss is not None and rss > 1024 * 1024, sys.platform
