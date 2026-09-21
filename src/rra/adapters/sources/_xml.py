"""XML API 응답 공통 파싱 (ScienceON·NTIS).

- defusedxml 만 쓴다 (DTD 금지 → XXE·billion laughs 차단). 크기 상한은 GuardedClient 가 이미 건다.
- API 응답은 "외부 파일"(PDF·HWPX)이 아니므로 샌드박스 대신 본체에서 파싱한다
  (OpenAlex JSON 과 같은 급).
- 여기서는 XML → 평평한 dict 까지만. 필드 해석은 각 소스의 순수 normalize 가 한다.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from defusedxml.ElementTree import fromstring

_SPACES = re.compile(r"\s+")
MAX_FIELD_CHARS = 20_000


class XmlResponseError(ValueError):
    """XML 이 아니거나 기대한 구조가 없다. 메시지에 본문을 넣지 않는다."""


def parse(body: bytes) -> Any:
    try:
        return fromstring(body, forbid_dtd=True)
    except Exception as exc:  # ParseError·DTDForbidden 등
        raise XmlResponseError(f"XML 파싱 실패 ({type(exc).__name__})") from None


def local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def text(el: Any) -> str:
    """요소 안의 모든 텍스트(CDATA 포함)를 공백 정리해 합친다."""
    if el is None:
        return ""
    return _SPACES.sub(" ", "".join(el.itertext())).strip()[:MAX_FIELD_CHARS]


def flatten(el: Any) -> dict[str, str]:
    """레코드 요소 → {태그경로: 텍스트}. 같은 경로가 여러 번 나오면 ' | ' 로 잇는다.

    `<item metaCode="Title">` 처럼 metaCode 속성이 있으면 그 값을 키로 쓴다 (ScienceON 형식).
    """
    out: dict[str, str] = {}

    def put(key: str, value: str) -> None:
        if not value:
            return
        out[key] = f"{out[key]} | {value}" if key in out else value

    def walk(node: Any, prefix: str) -> None:
        for child in node:
            name = child.get("metaCode") or local(child.tag)
            key = f"{prefix}/{name}" if prefix else name
            if len(child):
                walk(child, key)
            else:
                put(key, text(child))

    walk(el, "")
    return out


def find_records(root: Any, record_tag: str | None = None) -> list[Any]:
    """레코드 요소 목록.

    record_tag 가 없으면 '자식을 가진 같은 태그 형제가 가장 많은 묶음'을 고른다.
    레코드가 1건뿐인 응답에서는 감싸는 요소를 고를 수 있다 → 수집에는 쓰지 말고,
    녹화 도구가 태그 후보를 제안할 때만 쓴다.
    """
    if record_tag:
        return [e for e in root.iter() if local(e.tag) == record_tag]
    best: list[Any] = []
    for parent in root.iter():
        groups = Counter(local(c.tag) for c in parent if len(c))
        if not groups:
            continue
        tag, count = groups.most_common(1)[0]
        if count > len(best):
            best = [c for c in parent if local(c.tag) == tag and len(c)]
    return best


def first_text(root: Any, *names: str) -> str:
    """이름(대소문자 무시) 중 처음 발견되는 요소의 텍스트. 결과 코드·총건수 찾기용."""
    wanted = {n.lower() for n in names}
    for el in root.iter():
        if local(el.tag).lower() in wanted:
            return text(el)
    return ""
