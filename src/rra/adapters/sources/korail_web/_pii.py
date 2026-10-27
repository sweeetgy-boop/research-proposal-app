"""수집 텍스트의 개인정보 제거 (순수). 직원 이름·전화·이메일을 저장 전에 지운다.

- 전화번호: 02·0XX 지역번호·휴대전화·내선 표기 → "[연락처 삭제]"
- 이메일 → "[이메일 삭제]"
- 이름: "담당자 홍길동", "문의: 홍길동 차장", "홍길동 과장(…)" 처럼 라벨·직급과 붙은 2~4자
  한글 이름만 지운다
  (라벨·직급은 남긴다). 본문 일반 문장의 이름은 식별할 수 없어 건드리지 않는다.
"""

from __future__ import annotations

import re

PHONE = re.compile(
    r"(?<!\d)(?:\+82[-\s]?)?0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}(?!\d)|(?<!\d)1\d{3}[-.]\d{4}(?!\d)"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RANKS = (
    "과장|차장|부장|대리|주임|사원|팀장|처장|실장|소장|원장|본부장|센터장|단장|부원장|이사|감사|"
    "사무관|주무관|연구원|선임|책임|수석|역장|부역장|소속장"
)
_LABELS = "담당자|담당|문의처|문의|작성자|연락처|책임자|문의 및 신청|기자|취재"
_LABELED = re.compile(
    rf"({_LABELS})\s*[:：]?\s*([가-힣]{{2,4}})(?=\s*(?:{RANKS})?\s*(?:[(\[(]|$|\n|,|/|\s))"
)
_NAME_RANK = re.compile(rf"(?<![가-힣])([가-힣]{{2,4}})\s+({RANKS})(?![가-힣])")
_RANK_NAME = re.compile(rf"(?<![가-힣])({RANKS})\s+([가-힣]{{2,4}})(?=\s*(?:[(\[(]|$|\n|,|·|/))")
_DEPT_SUFFIX = (
    "처",
    "실",
    "단",
    "부",
    "팀",
    "과",
    "원",
    "센터",
    "본부",
    "연구소",
    "사업소",
    "역",
    "공사",
)
_NOT_NAMES = frozenset(
    {"부서", "부서명", "연락처", "전화", "이메일", "성명", "직급", "직위", "소속", "정보", "안내"}
)
NAME_MASK = "[이름 삭제]"


def _is_dept(word: str) -> bool:
    return word in _NOT_NAMES or word.endswith(_DEPT_SUFFIX)


def strip_pii(text: str) -> str:
    out = EMAIL.sub("[이메일 삭제]", text)
    out = PHONE.sub("[연락처 삭제]", out)
    out = _LABELED.sub(
        lambda m: m.group(0) if _is_dept(m.group(2)) else f"{m.group(1)} {NAME_MASK}", out
    )
    out = _NAME_RANK.sub(
        lambda m: m.group(0) if _is_dept(m.group(1)) else f"{NAME_MASK} {m.group(2)}", out
    )
    out = _RANK_NAME.sub(
        lambda m: m.group(0) if _is_dept(m.group(2)) else f"{m.group(1)} {NAME_MASK}", out
    )
    return out


def has_pii(text: str) -> bool:
    return bool(EMAIL.search(text) or PHONE.search(text))
