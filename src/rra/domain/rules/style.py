"""Q6 규칙 검사·자동 정리 (Argon 전) — 순수 규칙.

자동으로 고칠 수 있는 것은 고친다: 어미를 개조식(~함·~임·~됨·~있음)으로 통일, 같은 섹션 안의
완전 중복 문장 제거. 나머지는 알림으로 넘긴다: 지나치게 긴 문장(max_chars 초과), 문체 혼용(고칠 수
없는 종결), 기간·연차 표현과 제약의 불일치("2차년도" 인데 제약이 "1년 이내"). 알림은 lint 문제
(severity=warning)로 저장되고 1차 검토에 "앱이 찾은 문제" 로 함께 보낸다. 수집 문서·LLM 출력은
비신뢰 텍스트 — 여기서는 문장 끝만 바꾸고 의미는 건드리지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from rra.domain.models import Section, Sentence

LONG_SENTENCE = "long_sentence"
MIXED_STYLE = "mixed_style"
PERIOD_MISMATCH = "period_mismatch"
DUPLICATE_SENTENCE = "duplicate_sentence"
SECTION_TRIMMED = "section_trimmed"  # 칸 길이 상한을 넘은 섹션의 뒤 문장을 잘라냄 (경고)
DEFAULT_MAX_SENTENCE_CHARS = 180

# 서술형 종결 → 개조식 (보수적으로 흔한 꼴만)
_ENDINGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:한다|합니다)\.?$"), "함."),
    (re.compile(r"(?:된다|됩니다)\.?$"), "됨."),
    (re.compile(r"(?:있다|있습니다)\.?$"), "있음."),
    (re.compile(r"(?:없다|없습니다)\.?$"), "없음."),
    (re.compile(r"(?:이다|입니다)\.?$"), "임."),
    (re.compile(r"(?:않는다|않습니다)\.?$"), "않음."),
    (re.compile(r"(?:필요하다|필요합니다)\.?$"), "필요함."),
    (re.compile(r"(?:기대된다|기대됩니다)\.?$"), "기대됨."),
    (re.compile(r"(?:예상된다|예상됩니다)\.?$"), "예상됨."),
    (re.compile(r"(?:수행한다|수행합니다)\.?$"), "수행함."),
    (re.compile(r"(?:활용한다|활용합니다)\.?$"), "활용함."),
    (re.compile(r"(?:개발한다|개발합니다)\.?$"), "개발함."),
    (re.compile(r"(?:검증한다|검증합니다)\.?$"), "검증함."),
    (re.compile(r"(?:분석한다|분석합니다)\.?$"), "분석함."),
    (re.compile(r"(?:제시한다|제시합니다)\.?$"), "제시함."),
    (re.compile(r"(?:목표로 한다|목표로 합니다)\.?$"), "목표로 함."),
]
_REPORT_END = re.compile(r"(?:함|임|됨|음|않음|필요함|기대됨|예상됨)\.?$")
_PROSE_END = re.compile(r"(?:다|요)\.?$")
_YEAR_PHASE = re.compile(r"(\d)\s*차\s*년도")
_WITHIN_ONE_YEAR = re.compile(
    r"(?:1\s*년\s*(?:이내|내|안)|12\s*개월\s*(?:이내|내|안)|단년도|1개년)"
)
_WITHIN_N_YEARS = re.compile(r"(\d)\s*년\s*(?:이내|내|안)")


@dataclass
class StyleFinding:
    section: str
    code: str
    message: str
    sentence: int | None = None


@dataclass
class StyleResult:
    sections: list[Section]
    fixed: list[str] = field(default_factory=list)  # 자동 정리 기록 ("section:index 어미 통일" 등)
    findings: list[StyleFinding] = field(default_factory=list)  # 알림 (고치지 않음)


def unify_ending(text: str) -> str:
    """서술형 종결(~한다/~입니다)을 개조식(~함/~임)으로. 이미 개조식이거나 모르는 꼴이면 그대로."""
    stripped = text.rstrip()
    if not stripped or _REPORT_END.search(stripped):
        return text
    for pattern, repl in _ENDINGS:
        if pattern.search(stripped):
            return pattern.sub(repl, stripped)
    return text


def is_prose(text: str) -> bool:
    """개조식으로 고치지 못한 서술형 종결(문체 혼용 알림 대상)."""
    stripped = text.rstrip()
    return bool(_PROSE_END.search(stripped)) and not _REPORT_END.search(stripped)


def _norm(text: str) -> str:
    return re.sub(r"[\s.。]+", "", text)


def allowed_years(constraints: str) -> int | None:
    """제약 문구의 허용 연차 — "1년 이내"·"12개월 이내"·"단년도" = 1, "N년 이내" = N."""
    if not constraints:
        return None
    if _WITHIN_ONE_YEAR.search(constraints):
        return 1
    m = _WITHIN_N_YEARS.search(constraints)
    return int(m.group(1)) if m else None


def check_sections(
    sections: list[Section],
    *,
    constraints: str = "",
    max_chars: int = DEFAULT_MAX_SENTENCE_CHARS,
    skip: frozenset[str] = frozenset({"title", "task_type", "strategy_alignment", "utilization"}),
    fix: bool = True,
) -> StyleResult:
    """자동 정리(어미 통일·완전 중복 제거) + 알림(긴 문장·문체 혼용·연차 불일치).

    선택형·제목·앱 확정 문장은 건드리지 않는다.
    """
    years = allowed_years(constraints)
    out: list[Section] = []
    fixed: list[str] = []
    findings: list[StyleFinding] = []
    for sec in sections:
        if sec.key in skip:
            out.append(sec)
            continue
        seen: set[str] = set()
        kept: list[Sentence] = []
        for i, s in enumerate(sec.sentences):
            text = s.text
            if s.origin == "app":
                kept.append(s)
                continue
            if fix:
                unified = unify_ending(text)
                if unified != text:
                    fixed.append(f"{sec.key}:{i} 어미 통일")
                    text = unified
                key = _norm(text)
                if key in seen:
                    fixed.append(f"{sec.key}:{i} 완전 중복 제거")
                    continue
                seen.add(key)
            idx = len(kept)
            if len(text) > max_chars:
                findings.append(
                    StyleFinding(
                        sec.key, LONG_SENTENCE, f"문장이 {len(text)}자 — {max_chars}자 이내로", idx
                    )
                )
            if is_prose(text):
                findings.append(
                    StyleFinding(
                        sec.key, MIXED_STYLE, "개조식(~함·~임)으로 통일하지 못한 서술형 종결", idx
                    )
                )
            if years is not None:
                phases = [int(m) for m in _YEAR_PHASE.findall(text)]
                if any(p > years for p in phases):
                    findings.append(
                        StyleFinding(
                            sec.key,
                            PERIOD_MISMATCH,
                            f"{max(phases)}차년도 계획이 제약(연구기간 {years}년 이내)과 맞지 않음",
                            idx,
                        )
                    )
            kept.append(s.model_copy(update={"text": text}) if text != s.text else s)
        out.append(sec.model_copy(update={"sentences": kept}))
    return StyleResult(sections=out, fixed=fixed, findings=findings)


def trim_sections(
    sections: list[Section], max_chars: Mapping[str, int]
) -> tuple[list[Section], list[StyleFinding]]:
    """칸 길이 상한(rules.yaml max_chars)을 넘는 섹션은 뒤 문장부터 잘라 상한 안으로 — 전체 run 이
    invalid 가 되는 것보다 뒤 문장을 버리는 쪽이 되돌리기 쉽다(버린 수는 경고로). 앱 확정 문장은
    자르지 않는다. 첫 문장 하나만으로 상한을 넘으면 그대로 둔다(lint 가 too_long 으로 알린다)."""
    out: list[Section] = []
    findings: list[StyleFinding] = []
    for sec in sections:
        limit = max_chars.get(sec.key)
        kept = list(sec.sentences)
        removed = 0
        while limit and len(" ".join(s.text for s in kept)) > limit and len(kept) > 1:
            if kept[-1].origin == "app":
                break
            kept.pop()
            removed += 1
        if removed:
            findings.append(
                StyleFinding(
                    sec.key, SECTION_TRIMMED, f"칸 상한 {limit}자를 넘어 뒤 문장 {removed}개를 뺌"
                )
            )
            out.append(sec.model_copy(update={"sentences": kept}))
        else:
            out.append(sec)
    return out, findings
