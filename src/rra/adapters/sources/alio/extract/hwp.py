"""HWP 5.0(OLE 복합문서) 본문 텍스트 추출. 샌드박스 자식 프로세스에서만 import 된다.

구조: `FileHeader` 스트림(서명·버전·속성 플래그) + `BodyText/Section<n>` 스트림(레코드 열).
레코드 머리 4바이트 = tag(10bit) | level(10bit) | size(12bit, 0xFFF 이면 다음 4바이트가 크기).
본문 글자는 HWPTAG_PARA_TEXT(67) 레코드의 UTF-16LE 열이고, 0~31 은 제어 문자다
(1~23 은 8 유닛짜리 컨트롤, 10·13 은 줄·문단 끝, 24~31 은 1 유닛).

거부: 서명 불일치, 암호화 문서, 배포용 문서(ViewText 암호화). 섹션은 zlib(raw deflate)
압축이라 해제 크기를 상한(max_input_mb)으로 막는다. 표·각주 안 문단도 같은 레코드라 함께 나온다.
"""

from __future__ import annotations

import io
import struct
import zlib
from collections.abc import Iterator
from typing import Any

SIGNATURE = b"HWP Document File"
TAG_PARA_TEXT = 0x10 + 51  # HWPTAG_BEGIN + 51
FLAG_COMPRESSED = 0x1
FLAG_ENCRYPTED = 0x2
FLAG_DISTRIBUTION = 0x4
MAX_SECTIONS = 500
_PARA_BREAK = {10, 13}
_ONE_UNIT = {0, 24, 25, 26, 27, 28, 29}
_SPACES = {30, 31}


class NotHwp(ValueError):
    pass


class EncryptedDocument(ValueError):
    pass


class DistributionDocument(ValueError):
    pass


class SectionTooLarge(ValueError):
    pass


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    try:
        return _extract(data, limits)
    except (NotHwp, EncryptedDocument, DistributionDocument, SectionTooLarge):
        raise
    except (OSError, ValueError, struct.error, KeyError, zlib.error) as exc:
        raise NotHwp("structure") from exc  # 깨진 OLE 디렉터리·스트림·레코드


def _extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    import olefile

    cap = int(float(limits["max_input_mb"]) * 1024 * 1024)
    max_chars = int(limits["max_text_chars"])
    if not olefile.isOleFile(data):
        raise NotHwp("ole")
    lines: list[str] = []
    total = 0
    truncated = False
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        compressed = _check_header(ole)
        sections = _section_entries(ole)
        if not sections:
            raise NotHwp("no sections")
        for entry in sections[:MAX_SECTIONS]:
            with ole.openstream(entry) as stream:
                raw = stream.read(cap + 1)
            if len(raw) > cap:
                raise SectionTooLarge("stream")
            body = inflate(raw, cap) if compressed else raw
            for line in section_lines(body):
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


def _check_header(ole: Any) -> bool:
    """서명·플래그 검사. 반환: 본문 압축 여부."""
    if not ole.exists("FileHeader"):
        raise NotHwp("header")
    with ole.openstream("FileHeader") as stream:
        header = stream.read(256)
    if len(header) < 40 or not header.startswith(SIGNATURE):
        raise NotHwp("signature")
    (flags,) = struct.unpack_from("<I", header, 36)
    if flags & FLAG_ENCRYPTED:
        raise EncryptedDocument("encrypted")
    if flags & FLAG_DISTRIBUTION:
        raise DistributionDocument("distribution")
    return bool(flags & FLAG_COMPRESSED)


def _section_entries(ole: Any) -> list[list[str]]:
    found: list[tuple[int, list[str]]] = []
    for entry in ole.listdir(streams=True, storages=False):
        if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section"):
            suffix = entry[1][len("Section") :]
            if suffix.isdigit():
                found.append((int(suffix), entry))
    return [e for _, e in sorted(found)]


def inflate(raw: bytes, cap: int) -> bytes:
    """raw deflate 해제. 해제 결과가 cap 을 넘으면 거부 (압축 폭탄)."""
    d = zlib.decompressobj(-15)
    out = d.decompress(raw, cap + 1)
    if len(out) > cap or d.unconsumed_tail:
        raise SectionTooLarge("inflate")
    return out


def records(data: bytes) -> Iterator[tuple[int, int, bytes]]:
    """(tag, level, payload) 열. 깨진 꼬리는 조용히 끝낸다 (자료는 비신뢰)."""
    i, n = 0, len(data)
    while i + 4 <= n:
        (head,) = struct.unpack_from("<I", data, i)
        i += 4
        tag, level, size = head & 0x3FF, (head >> 10) & 0x3FF, (head >> 20) & 0xFFF
        if size == 0xFFF:
            if i + 4 > n:
                return
            (size,) = struct.unpack_from("<I", data, i)
            i += 4
        if i + size > n:
            return
        yield tag, level, data[i : i + size]
        i += size


def paragraph_text(payload: bytes) -> str:
    """PARA_TEXT 레코드 → 글자. 컨트롤 문자는 건너뛰고 줄·문단 끝은 개행으로."""
    count = len(payload) // 2
    units = struct.unpack(f"<{count}H", payload[: count * 2])
    out: list[str] = []
    i = 0
    while i < count:
        c = units[i]
        if c in _PARA_BREAK:
            out.append("\n")
            i += 1
        elif c in _ONE_UNIT:
            i += 1
        elif c in _SPACES:
            out.append(" ")
            i += 1
        elif c < 32:
            i += 8  # 확장·인라인 컨트롤: 코드 1 유닛 + 14 바이트
        elif 0xD800 <= c <= 0xDBFF:  # 서로게이트 쌍 (BMP 밖 글자) → 한 글자로
            if i + 1 < count and 0xDC00 <= units[i + 1] <= 0xDFFF:
                out.append(chr(0x10000 + ((c - 0xD800) << 10) + (units[i + 1] - 0xDC00)))
                i += 2
            else:
                i += 1  # 짝 없는 서로게이트는 버린다 (JSON 으로 내보낼 수 없다)
        elif 0xDC00 <= c <= 0xDFFF:
            i += 1
        else:
            out.append(chr(c))
            i += 1
    return "".join(out)


def section_lines(body: bytes) -> list[str]:
    lines: list[str] = []
    for tag, _level, payload in records(body):
        if tag != TAG_PARA_TEXT:
            continue
        for line in paragraph_text(payload).split("\n"):
            if text := " ".join(line.split()):
                lines.append(text)
    return lines
