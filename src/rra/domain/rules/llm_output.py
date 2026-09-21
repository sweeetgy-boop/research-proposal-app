"""A. LLM 출력 파싱 — JSON 배열 [{"text", "evidence"}] 만 받는다. 실패 사유를 구분해 돌려준다.

선택형 섹션(과제유형·활용계획·전략 정합성)은 객체
{"choices": [id…], "sentences": [...]} 하나만 받는다.
choices 는 허용 목록과 대조해 없는 값을 버리고, 개수가 범위를 벗어나면 비운다 (문장은 남긴다).

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
from collections.abc import Collection
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
    choices: list[str] = field(default_factory=list)

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


def _load(raw: str) -> tuple[ParseStatus, object]:
    body = _unwrap((raw or "").strip())
    if body is None:
        return "fence", None
    try:
        return "ok", json.loads(body)
    except ValueError:
        return "json", None


def _sentences(data: object) -> list[Sentence] | None:
    """LLM 문장 목록. origin 은 모델이 뭐라 하든 llm 으로 고정한다 (app 사칭 차단)."""
    if not isinstance(data, list):
        return None
    try:
        parsed = [Sentence.model_validate(x) for x in data]
    except ValidationError:
        return None
    return [Sentence(text=s.text, evidence=s.evidence) for s in parsed]


def parse_sentences(raw: str) -> ParseResult:
    n = len(raw or "")
    status, data = _load(raw)
    if status != "ok":
        return ParseResult(status, n)
    sentences = _sentences(data)
    if sentences is None:
        return ParseResult("schema", n)
    return ParseResult("ok", n, sentences)


def parse_choice_section(
    raw: str, allowed: Collection[str], *, min_n: int = 1, max_n: int = 1
) -> ParseResult:
    n = len(raw or "")
    status, data = _load(raw)
    if status != "ok":
        return ParseResult(status, n)
    if not isinstance(data, dict):
        return ParseResult("schema", n)
    picked = data.get("choices", [])
    sentences = _sentences(data.get("sentences", []))
    if sentences is None or not isinstance(picked, list):
        return ParseResult("schema", n)
    choices: list[str] = []
    for c in picked:
        if isinstance(c, str) and c in allowed and c not in choices:
            choices.append(c)
    if not min_n <= len(choices) <= max_n:
        choices = []
    return ParseResult("ok", n, sentences, choices)
