"""판독 결과 신뢰도 규칙 — 순수 (P3 ⑤).

- LLM 출력은 JSON 객체 하나만 받는다 (보안 A). 코드블록 울타리는 벗기되 그 밖의 설명문이 섞이면
실패.
  image_type 은 허용 목록 밖이면 "기타". 길이 상한은 모델(VisionReading)이 자른다 →
  초과는 실패가 아니라 절단.
- 수치 대조: Argon 이 적은 수치(본문·요약·structure 안의 숫자)는 OCR 텍스트에도 같은 값이 있을 때만
  확인된 수치. 나머지는 "판독 확인 필요"(unconfirmed) 로 표시하고 수치 근거에서 뺀다.
  비교는 `numbers.py` 와 같은 정규화(단위 환산)로 한다 — "1,234만명" 과 "1234만명" 은 같은 값.
- OCR 이 없으면(OcrUnavailable) 모든 수치가 미확인이다. 본문은 남기되 수치는 전부 unconfirmed.
- 본문 합성: 확인되지 않은 수치가 든 문장에는 "[판독 확인 필요]" 표식을 붙여 적재한다. 생성 단계의
  수치 lint(unsupported_number)는 그대로 — 표식 덕에 담당자가 어디를 봐야 하는지 안다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from rra.domain.models.vision import (
    IMAGE_TYPES,
    MAX_SUMMARY_CHARS,
    MAX_TEXT_CHARS,
    MAX_TITLE_CHARS,
    ImageType,
    OcrResult,
    VisionReading,
)
from rra.domain.rules.numbers import numbers

CHECK_MARK = "[판독 확인 필요]"
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
MAX_STRUCTURE_CHARS = 40_000
_SENTENCE_SPLIT = re.compile(r"(?<=[.。!?])\s+|\n+")


class VisionParseError(ValueError):
    """JSON 이 아니거나 객체가 아님. 메시지에 본문을 담지 않는다."""


def parse_reading(text: str) -> VisionReading:
    """LLM 출력 → VisionReading. 실패는 VisionParseError (호출자가 OCR 대체로 간다)."""
    body = _FENCE.sub("", text or "").strip()
    try:
        data = json.loads(body)
    except ValueError:
        raise VisionParseError("not_json") from None
    if not isinstance(data, dict):
        raise VisionParseError("not_object")
    image_type = _image_type(data.get("image_type"))
    structure = data.get("structure")
    if not isinstance(structure, dict):
        structure = {}
    if len(json.dumps(structure, ensure_ascii=False)) > MAX_STRUCTURE_CHARS:
        structure = {"truncated": True}
    return VisionReading(
        image_type=image_type,
        title=_text(data.get("title"), MAX_TITLE_CHARS),
        text=_text(data.get("text"), MAX_TEXT_CHARS),
        structure=structure,
        summary=_text(data.get("summary"), MAX_SUMMARY_CHARS),
        uncertain=bool(data.get("uncertain", False)),
    )


def _image_type(value: Any) -> ImageType:
    if isinstance(value, str):
        v = value.strip()
        if v in IMAGE_TYPES:
            return v  # type: ignore[return-value]
        aliases = {
            "체계도": "체계도·조직도·흐름도",
            "조직도": "체계도·조직도·흐름도",
            "흐름도": "체계도·조직도·흐름도",
            "diagram": "체계도·조직도·흐름도",
            "table": "표",
            "chart": "그래프",
            "graph": "그래프",
            "text": "글자 이미지",
            "other": "기타",
        }
        if v.lower() in aliases:
            return aliases[v.lower()]  # type: ignore[return-value]
    return "기타"


def _text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s.strip()[:limit]


# ── 수치 대조 ─────────────────────────────────────────────
def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _walk_strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _walk_strings(v)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        yield str(value)


def reading_texts(reading: VisionReading) -> list[str]:
    return [reading.title, reading.text, reading.summary, *_walk_strings(reading.structure)]


def verify_numbers(reading: VisionReading, ocr: OcrResult | None) -> tuple[list[str], list[str]]:
    """(확인된 표기, 미확인 표기). OCR 이 없으면 전부 미확인."""
    shown: dict[str, tuple[str, Any]] = {}
    for text in reading_texts(reading):
        for s, canon in numbers(text):
            shown.setdefault(s, canon)
    if not shown:
        return [], []
    if ocr is None:
        return [], list(shown)
    allowed = set()
    values = set()
    for _, canon in numbers(ocr.text):
        allowed.add(canon)
        values.add(canon[1])
    confirmed, unconfirmed = [], []
    for s, canon in shown.items():
        kind, value = canon
        ok = canon in allowed or ("bare", value) in allowed or (kind == "bare" and value in values)
        (confirmed if ok else unconfirmed).append(s)
    return confirmed, unconfirmed


def mark_unconfirmed(text: str, unconfirmed: Iterable[str]) -> str:
    """미확인 수치가 든 문장 앞에 CHECK_MARK 를 붙인다. 수치 자체는 지우지 않는다 (담당자가
    본다)."""
    marks = [u for u in unconfirmed if u]
    if not marks or not text:
        return text
    out = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence:
            continue
        if any(m in sentence.replace(" ", "") for m in marks) and not sentence.startswith(
            CHECK_MARK
        ):
            sentence = f"{CHECK_MARK} {sentence}"
        out.append(sentence)
    return "\n".join(out)


def evidence_numbers(reading: VisionReading, ocr: OcrResult | None) -> list[str]:
    """수치 근거로 쓸 수 있는 표기 — OCR 에도 있는 것만."""
    confirmed, _ = verify_numbers(reading, ocr)
    return confirmed
