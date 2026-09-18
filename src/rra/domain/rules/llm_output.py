"""A. LLM 출력 파싱 — JSON 배열 [{"text", "evidence"}] 만 받는다. 실패 사유를 구분해 돌려준다.

허용하는 감싸기는 딱 하나: 전체가 코드펜스 한 개(``` 또는 ```json)로 둘러싸인 경우.
그 밖의 형태(다른 언어 태그, 펜스 밖 설명문, 펜스 여러 개)는 fence 실패로 거부한다.
파서를 넓히면 잘못된 출력이 조용히 통과하므로 일부러 좁게 둔다.

사유:
- ok      파싱 성공 (빈 배열 포함)
- fence   코드펜스 형태가 허용 범위 밖
- json    JSON 문법 오류 (응답이 잘려 닫는 펜스가 없는 경우 포함)
- schema  JSON 이지만 배열이 아니거나 항목이 Sentence 스키마에 맞지 않음
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from rra.domain.models import Sentence

ParseStatus = Literal["ok", "fence", "json", "schema"]

FENCE = "```"
_OPEN = re.compile(r"\A```(json)?[ \t]*\n", re.IGNORECASE)


@dataclass(frozen=True)
class ParseResult:
    status: ParseStatus
    raw_chars: int
    sentences: list[Sentence] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _unwrap(text: str) -> str | None:
    """허용된 펜스 한 개를 벗긴 본문. 허용 범위 밖이면 None."""
    if FENCE not in text:
        return text
    opened = _OPEN.match(text)
    if opened is None:
        return None  # 펜스 앞에 설명문, 또는 ```python 같은 다른 태그
    body = text[opened.end() :]
    if FENCE not in body:
        return body  # 닫는 펜스가 없다 = 응답이 잘림 → JSON 단계에서 판정
    inner, _, rest = body.rpartition(FENCE)
    if rest.strip() or FENCE in inner:
        return None  # 펜스 뒤에 설명문, 또는 펜스가 여러 개
    return inner


def parse_sentences(raw: str) -> ParseResult:
    text = (raw or "").strip()
    n = len(raw or "")
    body = _unwrap(text)
    if body is None:
        return ParseResult("fence", n)
    try:
        data = json.loads(body)
    except ValueError:
        return ParseResult("json", n)
    if not isinstance(data, list):
        return ParseResult("schema", n)
    try:
        return ParseResult("ok", n, [Sentence.model_validate(x) for x in data])
    except ValidationError:
        return ParseResult("schema", n)
