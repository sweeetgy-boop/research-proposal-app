"""개인정보 제거 — 순수 규칙. 이미지 판독·OCR 텍스트를 적재하기 전에 거친다.

지우는 것: 전화번호(국번·휴대전화·내선 표기), 이메일, 주민·여권·계좌 비슷한 긴 숫자열,
"담당자/담당/문의/작성자/연락처 + 이름" 꼴의 이름. 부서명은 남긴다 (own/_names.strip_person 과 같은
규칙).
지운 자리는 종류별 표식(`[전화]`·`[이메일]`·`[이름]`·`[번호]`)으로 바꿔 문맥이 깨지지 않게 한다.
한계: 단독으로 나온 이름(문맥 없이 "홍길동")은 일반 명사와 구분할 수 없어 지우지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PHONE = re.compile(
    r"(?<!\d)(?:\+82[\s-]?)?0?(?:1[016789]|2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|80)"
    r"[\s\-.)]?\d{3,4}[\s\-.]?\d{4}(?!\d)"
)
_EXT = re.compile(r"(?:내선|ext\.?)\s*:?\s*\d{2,5}", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_ID = re.compile(r"(?<!\d)\d{6}[\s-]?\d{7}(?!\d)")  # 주민등록번호 꼴
_ACCOUNT = re.compile(r"(?<!\d)\d{3,6}[\s-]\d{2,6}[\s-]\d{4,8}(?:[\s-]\d{2,6})?(?!\d)")
_NAMED = re.compile(
    r"(담당자|담당|문의처|문의|작성자|작성|연락처|책임자|팀장|처장|부장|과장|대리|주임|사원|연구원)"
    r"\s*[:：]?\s*([가-힣]+(?:처|실|단|부|팀|과|원|센터|본부|연구소|사업소)\s+)?([가-힣]{2,4})"
    r"(?=[\s(,)\]/]|$)"
)
_DEPT_PERSON = re.compile(
    r"(\S+(?:처|실|단|부|팀|과|원|센터|본부|연구소|사업소))\s+([가-힣]{2,4})(?=\s*(?:\(|$|,|/))"
)
_KEEP_AFTER_TITLE = {"없음", "미정", "해당", "별도", "참조", "문의", "담당", "연락"}


@dataclass(frozen=True)
class PrivacyReport:
    text: str
    removed: dict[str, int]


def strip_personal(text: str) -> PrivacyReport:
    if not text:
        return PrivacyReport(text, {})
    removed: dict[str, int] = {}

    def sub(pattern: re.Pattern[str], repl: str, kind: str, value: str) -> str:
        value, n = pattern.subn(repl, value)
        if n:
            removed[kind] = removed.get(kind, 0) + n
        return value

    out = sub(_EMAIL, "[이메일]", "email", text)
    out = sub(_LONG_ID, "[번호]", "id_number", out)
    out = sub(_PHONE, "[전화]", "phone", out)
    out = sub(_EXT, "[전화]", "phone", out)
    out = sub(_ACCOUNT, "[번호]", "account", out)

    def named(m: re.Match[str]) -> str:
        name = m.group(3)
        if name in _KEEP_AFTER_TITLE:
            return m.group(0)
        removed["name"] = removed.get("name", 0) + 1
        dept = m.group(2) or ""
        return f"{m.group(1)} {dept}[이름]"

    out = _NAMED.sub(named, out)

    def dept(m: re.Match[str]) -> str:
        removed["name"] = removed.get("name", 0) + 1
        return m.group(1)

    out = _DEPT_PERSON.sub(dept, out)
    return PrivacyReport(out, removed)
