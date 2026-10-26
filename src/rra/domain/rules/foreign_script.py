"""외국 문자 혼입 검사 — 한국어 본문에 한자(CJK 통합 한자)·가나 등이 섞인 문장을 찾는다.

7B 모델이 한국어 문장에 中文·日本語 글자를 섞는 경우가 있다(예: "文档ID"). 문장은 버리지 않고
lint 경고(foreign_script)만 붙인다. 로마자·숫자·기호·한글(자모 포함)은 외국 문자로 보지 않는다.
"""

from __future__ import annotations

import re

# CJK 부수·강희 부수·통합 한자(확장 A·B 포함)·호환 한자·가나·반각 가나·일본어 반복 기호
_FOREIGN = re.compile(
    "[⺀-⿟"  # CJK 부수 보충·강희 부수
    "々-〇"  # 々 〆 〇
    "぀-ヿ"  # 히라가나·가타카나
    "ㇰ-ㇿ"  # 가타카나 음성 확장
    "㐀-䶿"  # CJK 확장 A
    "一-鿿"  # CJK 통합 한자
    "豈-﫿"  # CJK 호환 한자
    "ｦ-ﾟ"  # 반각 가타카나
    "\U00020000-\U0002ebef"  # CJK 확장 B~F
    "]"
)


def foreign_script_chars(text: str) -> list[str]:
    """문장에 섞인 외국 문자(중복 제거, 등장 순서)."""
    return list(dict.fromkeys(_FOREIGN.findall(text or "")))


def has_foreign_script(text: str) -> bool:
    return _FOREIGN.search(text or "") is not None
