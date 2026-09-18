"""B. 파서 진입 전 검증 — 확장자·종류·크기·매직바이트."""

import os

import pytest

from rra.adapters.sources.alio.filecheck import (
    BadExtension,
    EmptyFile,
    MagicMismatch,
    NotRegularFile,
    TooLarge,
    UnsupportedFormat,
    open_validated,
)

from .conftest import make_hwpx

ALL = frozenset({"pdf", "hwpx", "hwp", "csv"})
MB = 1024 * 1024


def check(path, max_bytes=MB, allowed=ALL):
    return open_validated(path, max_bytes=max_bytes, allowed=allowed)


def test_valid_pdf_returns_fd_at_start_and_hash(tmp_path):
    p = tmp_path / "r.PDF"
    p.write_bytes(b"%PDF-1.7\n...")
    with check(p) as vf:
        assert vf.fmt == "pdf" and vf.size == 12 and len(vf.sha256) == 64
        assert os.read(vf.fd, 5) == b"%PDF-"  # 해시 계산 후 위치가 0 으로 돌아와 있다
    assert vf.fd == -1


def test_hwpx_ok(tmp_path):
    p = tmp_path / "r.hwpx"
    p.write_bytes(make_hwpx())
    with check(p) as vf:
        assert vf.fmt == "hwpx"


@pytest.mark.parametrize(
    ("name", "body", "error"),
    [
        ("r.exe", b"MZ", BadExtension),
        ("r", b"%PDF-", BadExtension),
        ("r.pdf", b"PK\x03\x04rest", MagicMismatch),  # 확장자 위장 (zip 인데 .pdf)
        ("r.hwpx", b"%PDF-1.4", MagicMismatch),
        ("r.pdf", b"", EmptyFile),
        ("r.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", UnsupportedFormat),
        ("r.hwp", b"%PDF-", MagicMismatch),
        ("c.csv", b"PK\x03\x04", MagicMismatch),  # xlsx 를 csv 로 위장
        ("c.csv", b"a,b\x00c", MagicMismatch),
    ],
)
def test_rejections(tmp_path, name, body, error):
    p = tmp_path / name
    p.write_bytes(body)
    with pytest.raises(error):
        check(p)


def test_too_large(tmp_path):
    p = tmp_path / "r.pdf"
    p.write_bytes(b"%PDF-" + b"0" * 100)
    with pytest.raises(TooLarge):
        check(p, max_bytes=50)


def test_symlink_is_not_followed(tmp_path):
    target = tmp_path / "real.pdf"
    target.write_bytes(b"%PDF-1.7")
    link = tmp_path / "link.pdf"
    link.symlink_to(target)
    with pytest.raises(NotRegularFile):
        check(link)


def test_directory_and_fifo_rejected(tmp_path):
    (tmp_path / "d.pdf").mkdir()
    with pytest.raises(NotRegularFile):
        check(tmp_path / "d.pdf")
    fifo = tmp_path / "f.pdf"
    os.mkfifo(fifo)
    with pytest.raises(NotRegularFile):  # O_NONBLOCK 이라 열기에서 멈추지 않는다
        check(fifo)


def test_extension_outside_allowed_set(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("a,b\n")
    with pytest.raises(BadExtension):
        check(p, allowed=frozenset({"pdf"}))


def test_error_messages_do_not_contain_path(tmp_path):
    p = tmp_path / "비밀_보고서.pdf"
    p.write_bytes(b"PK\x03\x04")
    with pytest.raises(MagicMismatch) as info:
        check(p)
    assert "비밀" not in str(info.value) and str(tmp_path) not in str(info.value)
