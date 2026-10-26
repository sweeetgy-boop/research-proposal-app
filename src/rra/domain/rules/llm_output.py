"""A. LLM 출력 파싱 — JSON 배열 [{"text", "evidence"}] 만 받는다. 실패 사유를 구분해 돌려준다.

선택형 섹션(과제유형·활용계획·전략 정합성)은 객체
{"choices": [id…], "sentences": [...]} 하나만 받는다.
choices 는 허용 목록과 대조해 없는 값을 버리고, 개수가 범위를 벗어나면 비운다 (문장은 남긴다).
sentences 가 스키마에 맞지 않아도 choices 가 유효하면 choices 만 살린다 (choices_only).

허용하는 감싸기는 딱 하나: 전체가 코드펜스 한 개(``` 또는 ```json)로 둘러싸인 경우.
그 밖의 형태(다른 언어 태그, 펜스 밖 설명문, 펜스 여러 개)는 fence 실패로 거부한다.
파서를 넓히면 잘못된 출력이 조용히 통과하므로 일부러 좁게 둔다.

사유:
- ok      파싱 성공 (빈 배열 포함)
- fence   코드펜스 형태가 허용 범위 밖
- json    JSON 문법 오류 (응답이 잘려 닫는 펜스가 없는 경우 포함)
- schema  JSON 이지만 배열이 아니거나 항목이 Sentence 스키마에 맞지 않음
- choices_only  (선택형) choices 는 목록 안의 유효한 값이라 살렸지만 sentences 가 스키마에 맞지 않아
  문장은 버렸다. 경고로 기록되고, 선택지는 확정 단계의 제안으로 남는다.

파싱 직전 보정은 하나뿐: 모델이 `text` 안에 자료 구획 태그 조각(`<doc id="…" basis="…">`,
`(basis="…" id="…")`, `</doc>`)을 그대로 베껴 넣은 것을 지운다 (Qwen2.5-7B 가 이렇게 쓰면서
안의 따옴표가 이스케이프되지 않아 JSON 이 깨진다 — tests/fixtures/llm). 정확히 그 형태만 지우고
다른 태그·속성 표기는 건드리지 않는다. 지운 개수는 ParseResult.stripped 에 남긴다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from rra.domain.models import Sentence

ParseStatus = Literal["ok", "fence", "json", "schema", "choices_only"]

FENCE = "```"
_OPEN = re.compile(r"\A```(json)?[ \t]*\n", re.IGNORECASE)

# 자료 구획 태그 조각 — trust.wrap_untrusted 가 만드는 형태(와 그 속성을 괄호에 옮긴 형태)만.
_BASIS = r"(?:full_text|summary|abstract)"
_FRAG_ID = r"[^\"<>()\\\s]+"
_TAG_FRAGMENT = re.compile(
    rf'\s?\(?\\?<doc id="{_FRAG_ID}"(?: basis="{_BASIS}")?>\)?'  # <doc id="…" basis="…">
    rf'|\s?\(basis="{_BASIS}" id="{_FRAG_ID}"\)'  # (basis="…" id="…")
    rf'|\s?\(id="{_FRAG_ID}" basis="{_BASIS}"\)'  # (id="…" basis="…")
    # (文档ID: alio:sum-…#1) / (doc_id: openalex:W…#0) / (출처: ntis:…) — 7B 가 본문에 섞는 조각
    rf"|\s?\((?:文档ID|doc_?id|문서\s?ID|출처|근거|id)\s*[:：]\s*[A-Za-z]+:{_FRAG_ID}"
    rf"(?:\s*,\s*[A-Za-z]+:{_FRAG_ID})*\s*\)"
    rf"|\s?\\?</doc>"
)


def strip_doc_fragments(body: str) -> tuple[str, int]:
    """자료 구획 태그 조각을 지운 본문과 지운 개수. 정확히 그 형태만."""
    return _TAG_FRAGMENT.subn("", body)


_SPACES = re.compile(r"[ \t]{2,}")


def clean_sentence(text: str) -> str:
    """저장·조회·렌더 공용 문장 정리: 자료 태그·(文档ID: …) 출처 조각 제거 + 겹친 공백 정리.

    문장 자체는 자르지 않는다. 섹션 저장 때(parse) 적용하고, 예전 run 을 읽을 때(get_draft)도
    같은 정리를 거쳐 화면·검토 입력에 조각이 가지 않게 한다.
    """
    cleaned, _ = strip_doc_fragments(text or "")
    return _SPACES.sub(" ", cleaned).strip()


@dataclass(frozen=True)
class ParseResult:
    status: ParseStatus
    raw_chars: int
    sentences: list[Sentence] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    stripped: int = 0  # 파싱 전 지운 자료 구획 태그 조각 수

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


def _load(raw: str) -> tuple[ParseStatus, object, int]:
    body = _unwrap((raw or "").strip())
    if body is None:
        return "fence", None, 0
    body, stripped = strip_doc_fragments(body)
    try:
        return "ok", json.loads(body), stripped
    except ValueError:
        return "json", None, stripped


def _sentences(data: object) -> list[Sentence] | None:
    """LLM 문장 목록. origin 은 모델이 뭐라 하든 llm 으로 고정한다 (app 사칭 차단)."""
    if not isinstance(data, list):
        return None
    try:
        parsed = [Sentence.model_validate(x) for x in data]
    except ValidationError:
        return None
    return [Sentence(text=clean_sentence(s.text), evidence=s.evidence) for s in parsed]


def parse_sentences(raw: str) -> ParseResult:
    n = len(raw or "")
    status, data, stripped = _load(raw)
    if status != "ok":
        return ParseResult(status, n, stripped=stripped)
    sentences = _sentences(data)
    if sentences is None:
        return ParseResult("schema", n, stripped=stripped)
    return ParseResult("ok", n, sentences, stripped=stripped)


def parse_object(raw: str) -> dict[str, Any] | None:
    """JSON 객체 하나만 수용 (검토 응답). 펜스 하나는 벗긴다. 그 외는 None — 폐기."""
    status, data, _ = _load(raw)
    return data if status == "ok" and isinstance(data, dict) else None


def parse_choice_section(
    raw: str, allowed: Collection[str], *, min_n: int = 1, max_n: int = 1
) -> ParseResult:
    n = len(raw or "")
    status, data, stripped = _load(raw)
    if status != "ok":
        return ParseResult(status, n, stripped=stripped)
    if not isinstance(data, dict):
        return ParseResult("schema", n, stripped=stripped)
    picked = data.get("choices", [])
    if not isinstance(picked, list):
        return ParseResult("schema", n, stripped=stripped)
    choices: list[str] = []
    for c in picked:
        if isinstance(c, str) and c in allowed and c not in choices:
            choices.append(c)
    if not min_n <= len(choices) <= max_n:
        choices = []
    sentences = _sentences(data.get("sentences", []))
    if sentences is None:
        # 문장 스키마 오류 → 유효한 선택지만 살린다 (약한 모델이 문장 형식을 자주 틀린다)
        if choices:
            return ParseResult("choices_only", n, [], choices, stripped=stripped)
        return ParseResult("schema", n, stripped=stripped)
    return ParseResult("ok", n, sentences, choices, stripped=stripped)
