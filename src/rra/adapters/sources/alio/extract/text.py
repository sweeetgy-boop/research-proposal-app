"""평문 텍스트(알리오 상세 페이지 복사본) → 줄 목록. 샌드박스 자식 프로세스에서만 import 된다.

인코딩은 utf-8-sig → cp949 순서로 시도한다. 탭·줄바꿈 외 제어문자는 공백으로 바꾼다.
라벨 해석은 본체의 순수 함수 `alio.summary.parse_labeled` 가 한다.
입력 크기는 filecheck 의 max_bytes 가 이미 제한한다.
"""

from __future__ import annotations

import re
from typing import Any

from rra.adapters.sources.alio.extract.csv_catalog import decode

MAX_LINES = 5_000
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class TooManyLines(ValueError):
    pass


def extract(data: bytes, limits: dict[str, Any]) -> dict[str, Any]:
    text = decode(data).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_CONTROL.sub(" ", line).rstrip() for line in text.split("\n")]
    if len(lines) > MAX_LINES:
        raise TooManyLines("lines")
    return {"lines": lines}
