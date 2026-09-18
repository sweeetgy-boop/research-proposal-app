"""B. 파서 진입 전 파일 검증 (본체 프로세스, 파싱 없음).

확장자 허용목록 → O_NOFOLLOW 로 열기 → fstat(일반 파일·크기) → 매직바이트 ↔ 확장자 일치 → sha256.
검증을 통과한 **같은 fd** 를 샌드박스에 넘긴다 (검사 후 파일이 바뀌어도 영향 없음).
예외 메시지에는 경로·파일명을 넣지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

MAGIC: dict[str, bytes] = {
    "pdf": b"%PDF-",
    "hwpx": b"PK\x03\x04",
    "hwp": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # OLE2 Compound File (HWP 5.0)
}
PARSEABLE = frozenset({"pdf", "hwpx", "csv"})  # hwp 는 식별만 (Step 5b)
_BINARY_MAGICS = tuple(MAGIC.values())
_CSV_SNIFF = 64 * 1024


class FileRejected(Exception):
    """검증 실패. 하위 클래스 이름이 곧 로그에 남는 사유다."""


class BadExtension(FileRejected):
    pass


class NotRegularFile(FileRejected):
    pass


class EmptyFile(FileRejected):
    pass


class TooLarge(FileRejected):
    pass


class MagicMismatch(FileRejected):
    pass


class UnsupportedFormat(FileRejected):
    pass


@dataclass
class ValidatedFile:
    fd: int
    fmt: str
    sha256: str
    size: int

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> ValidatedFile:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def extension_of(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def open_validated(path: Path, *, max_bytes: int, allowed: frozenset[str]) -> ValidatedFile:
    ext = extension_of(path)
    if ext not in allowed or ext not in (*MAGIC, "csv"):
        raise BadExtension("extension")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:  # 심볼릭 링크(ELOOP), 권한, 사라진 파일
        raise NotRegularFile("open") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise NotRegularFile("type")
        if st.st_size == 0:
            raise EmptyFile("empty")
        if st.st_size > max_bytes:
            raise TooLarge("size")
        head = os.pread(fd, _CSV_SNIFF if ext == "csv" else 8, 0)
        check_magic(ext, head)
        if ext == "hwp":
            raise UnsupportedFormat("hwp")
        digest = _sha256(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        return ValidatedFile(fd=fd, fmt=ext, sha256=digest, size=st.st_size)
    except BaseException:
        os.close(fd)
        raise


def check_magic(ext: str, head: bytes) -> None:
    if ext == "csv":
        # 텍스트여야 한다: 바이너리 서명(엑셀 xlsx=zip, xls=OLE 등)·NUL 바이트 거부
        if head.startswith(_BINARY_MAGICS) or b"\x00" in head:
            raise MagicMismatch("magic")
        return
    if not head.startswith(MAGIC[ext]):
        raise MagicMismatch("magic")


def _sha256(fd: int) -> str:
    h = hashlib.sha256()
    offset = 0
    while chunk := os.pread(fd, 1024 * 1024, offset):
        h.update(chunk)
        offset += len(chunk)
    return h.hexdigest()
