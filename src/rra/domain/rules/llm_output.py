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
    lenient: bool = False  # 지시한 모양이 아니라 관용 처리(포장 풀기)로 받아들였다

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def strict_ok(self) -> bool:
        """지시한 모양 그대로 응답했고 파싱도 됐다 (관용 처리 없음)."""
        return self.status == "ok" and not self.lenient


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


SALVAGE_PREFIX_CHARS = 200  # 이 길이 안에서 JSON 이 시작하고
SALVAGE_SUFFIX_CHARS = 20  # JSON 뒤에 이 길이 이하의 찌꺼기만 있으면 살린다 ("]}" 같은 꼬리)


def _salvage(body: str) -> object | None:
    """JSON 앞뒤에 짧은 찌꺼기가 붙은 응답에서 첫 JSON 값 하나를 건진다 (관용 처리, lenient).

    7B 가 배열 뒤에 '}' 를 하나 더 붙이거나 짧은 머리말을 다는 일이 잦다(2026-10-27 측정에서
    섹션 JSON 실패의 주된 꼴). 긴 설명문 속에 JSON 이 묻힌 것은 살리지 않는다(지시 불이행)."""
    starts = [i for i in (body.find("["), body.find("{")) if i >= 0]
    if not starts:
        return None
    start = min(starts)
    if start > SALVAGE_PREFIX_CHARS:
        return None
    try:
        value, end = json.JSONDecoder().raw_decode(body, start)
    except ValueError:
        return None
    if len(body[end:].strip()) > SALVAGE_SUFFIX_CHARS:
        return None
    return value


def _load(raw: str) -> tuple[ParseStatus, object, int, bool]:
    """→ (상태, 값, 지운 태그 조각 수, 관용 처리 여부)."""
    body = _unwrap((raw or "").strip())
    if body is None:
        return "fence", None, 0, False
    body, stripped = strip_doc_fragments(body)
    try:
        return "ok", json.loads(body), stripped, False
    except ValueError:
        value = _salvage(body)
        if value is not None:
            return "ok", value, stripped, True
        return "json", None, stripped, False


def _sentences(data: object, *, unwrap: bool = False) -> tuple[list[Sentence] | None, bool]:
    """LLM 문장 목록과 관용 처리 여부. origin 은 모델이 뭐라 하든 llm 으로 고정한다 (app 사칭 차단).

    unwrap=True(비선택 섹션)면 선택형 모양 `{"sentences": [...]}` 포장을 풀어 문장 목록만 받고
    lenient=True 로 표시한다. 문장 객체 하나(배열 아님)는 여전히 schema 오류다. 키·값 검증은
    그대로 pydantic 이 한다.
    """
    lenient = False
    if unwrap and isinstance(data, dict) and isinstance(data.get("sentences"), list):
        data, lenient = data["sentences"], True
    if not isinstance(data, list):
        return None, lenient
    try:
        parsed = [Sentence.model_validate(x) for x in data]
    except ValidationError:
        return None, lenient
    return [Sentence(text=clean_sentence(s.text), evidence=s.evidence) for s in parsed], lenient


def parse_sentences(raw: str) -> ParseResult:
    n = len(raw or "")
    status, data, stripped, salvaged = _load(raw)
    if status != "ok":
        return ParseResult(status, n, stripped=stripped)
    sentences, lenient = _sentences(data, unwrap=True)
    lenient = lenient or salvaged
    if sentences is None:
        return ParseResult("schema", n, stripped=stripped, lenient=lenient)
    return ParseResult("ok", n, sentences, stripped=stripped, lenient=lenient)


def correction_hint(result: ParseResult, *, choice_section: bool) -> str:
    """스키마·JSON 오류 1회 재요청에 붙이는 짧은 교정 문구 (오류 내용 요약, 모델 공통)."""
    if result.status == "fence":
        return "코드블록(```)·설명·머리말 없이 JSON 하나만 출력할 것."
    if result.status == "json":
        return "JSON 문법 오류였음. 완결된 JSON 하나만, 따옴표·쉼표·괄호를 닫아 출력할 것."
    if choice_section:
        return (
            '출력은 객체 하나: {"choices": ["선택지 id"], '
            '"sentences": [{"text": "문장", "evidence": []}]}. '
            "sentences 는 text(문자열)·evidence(문자열 배열)를 가진 객체 배열이어야 함. "
            "choices 는 [선택지] 의 id 문자열 배열이어야 함."
        )
    return (
        '출력은 객체 배열: [{"text": "문장", "evidence": ["구획 id"]}]. '
        '객체 하나나 {"choices": …} 포장이 아니라 배열이어야 하고, 각 원소는 text(문자열)·'
        "evidence(문자열 배열)만 가진다."
    )


def parse_object(raw: str) -> dict[str, Any] | None:
    """JSON 객체 하나만 수용 (검토 응답). 펜스 하나는 벗긴다. 그 외는 None — 폐기."""
    status, data, _, _ = _load(raw)
    return data if status == "ok" and isinstance(data, dict) else None


def parse_choice_section(
    raw: str, allowed: Collection[str], *, min_n: int = 1, max_n: int = 1
) -> ParseResult:
    n = len(raw or "")
    status, data, stripped, salvaged = _load(raw)
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
    sentences, _ = _sentences(data.get("sentences", []))
    if sentences is None:
        # 문장 스키마 오류 → 유효한 선택지만 살린다 (약한 모델이 문장 형식을 자주 틀린다)
        if choices:
            return ParseResult("choices_only", n, [], choices, stripped=stripped)
        return ParseResult("schema", n, stripped=stripped)
    return ParseResult("ok", n, sentences, choices, stripped=stripped, lenient=salvaged)
