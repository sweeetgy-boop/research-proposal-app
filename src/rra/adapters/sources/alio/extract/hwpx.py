"""HWPX(OWPML, zip) 본문 추출. 샌드박스 자식 프로세스에서만 import 된다.

압축 해제 전 검사: 엔트리 수, 경로(zip slip: `..`·절대경로·역슬래시·드라이브), 선언 크기 합계,
엔트리별 압축비. 실제 읽기도 엔트리별 상한까지만 스트리밍한다(헤더의 크기는 믿지 않는다).
XML 은 defusedxml 만 쓴다 (DTD 금지 → XXE·billion laughs 차단).
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any

MIMETYPE = b"application/hwp+zip"
_SECTION = re.compile(r"^Contents/section(\d+)\.xml$")


class UnsafeArchive(ValueError):
    pass


class ArchiveTooLarge(ValueError):
    pass


class NotHwpx(ValueError):
    pass


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    cap = int(float(limits["max_input_mb"]) * 1024 * 1024)
    max_chars = int(limits["max_text_chars"])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        check_archive(
            zf,
            cap=cap,
            ratio=int(limits["max_zip_ratio"]),
            max_entries=int(limits["max_zip_entries"]),
        )
        if _read(zf, "mimetype", 64).strip() != MIMETYPE:
            raise NotHwpx("mimetype")
        sections = sorted(
            ((int(m.group(1)), n) for n in zf.namelist() if (m := _SECTION.match(n))),
        )
        if not sections:
            raise NotHwpx("no sections")
        lines: list[str] = []
        total = 0
        truncated = False
        for _, name in sections:
            for line in section_lines(_read(zf, name, cap)):
                if total + len(line) > max_chars:
                    truncated = True
                    break
                lines.append(line)
                total += len(line) + 1
            if truncated:
                break
    return {
        "text": "\n".join(lines),
        "toc": [],
        "pages": None,
        "meta_title": None,
        "truncated": truncated,
    }


def check_archive(zf: zipfile.ZipFile, *, cap: int, ratio: int, max_entries: int) -> None:
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise ArchiveTooLarge("entries")
    total = 0
    for info in infos:
        _check_name(info.filename)
        total += info.file_size
        if total > cap:
            raise ArchiveTooLarge("size")
        if info.file_size and (
            info.compress_size == 0 or info.file_size / info.compress_size > ratio
        ):
            raise ArchiveTooLarge("ratio")


def _check_name(name: str) -> None:
    if not name or "\\" in name or "\x00" in name or name.startswith("/"):
        raise UnsafeArchive("path")
    if re.match(r"^[A-Za-z]:", name) or ".." in PurePosixPath(name).parts:
        raise UnsafeArchive("path")


def _read(zf: zipfile.ZipFile, name: str, cap: int) -> bytes:
    try:
        f = zf.open(name)
    except KeyError:
        raise NotHwpx("missing entry") from None
    with f:
        data = f.read(cap + 1)
    if len(data) > cap:
        raise ArchiveTooLarge("entry")
    return data


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def section_lines(xml: bytes) -> list[str]:
    """section*.xml → 문단별 텍스트. `hp:p` 마다 줄을 나누고 `hp:t` 텍스트만 모은다."""
    from defusedxml.ElementTree import fromstring

    root = fromstring(xml, forbid_dtd=True)
    lines: list[str] = []
    current: list[str] = []
    stack: list[tuple[Any, bool]] = [(root, False)]
    while stack:  # 재귀 대신 명시적 스택 (깊은 중첩으로 인한 RecursionError 방지)
        el, closing = stack.pop()
        tag = _local(el.tag)
        if closing:
            if tag == "p":
                if text := "".join(current).strip():
                    lines.append(text)
                current = []
            continue
        if tag == "t":
            current.append(el.text or "")
            for child in el:
                current.append("\t" if _local(child.tag) == "tab" else " ")
                current.append(child.tail or "")
            continue
        if tag == "p":
            if text := "".join(current).strip():  # 바깥 문단의 앞부분 (표 안 문단 등)
                lines.append(text)
            current = []
            stack.append((el, True))
        stack.extend((child, False) for child in reversed(list(el)))
    if text := "".join(current).strip():
        lines.append(text)
    return lines
