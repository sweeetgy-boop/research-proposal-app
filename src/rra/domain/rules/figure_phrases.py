"""그림 칸 글자 — 잘라 줄이지 않고 뜻이 완결된 짧은 구절로 (순수 함수, 2026-10-29, ADR 0044).

소유자 지시(시범 의견 3차): "글자를 잘라 줄이지 말고, 명세를 만들 때 칸마다 글자 수 상한을 주고 그
안에서
뜻이 완결된 짧은 구절로 쓰게 한다. 9pt 미달로 다시 그릴 때도 같은 방식으로 다시 쓴다." 예전에는
글자가
작으면 띄어쓰기 자리에서 잘랐다(22 → 16자) — "신설역 수요를 별도 가정으로" 처럼 끊긴 구절이 그림에
남았다.

- 칸 글자 수 상한(`FIELD_LIMITS`): 밑그림(adapters/figures/render) 배치에서 본문 글자(37단위 ≈
10pt)로
  1~2줄에 들어가는 길이를 기준으로, 시범 측정(2026-10-28 pilot2 37장)에서 Nano Banana 그림 글자가
  9pt 밑으로
  떨어진 길이(SWOT 항목 24~29자 → 5.6~7.1pt, As-Is/To-Be 칸 30자 → 8.4~8.8pt) 밑으로 잡았다. 다시
  그릴 때는
  `TIGHTEN`(0.75)을 곱한 상한으로 다시 쓴다.
- 완결성(`phrase_problem`): 상한을 넘거나(too_long),
조사·연결어미("…으로"·"…를"·"…및"·"…의"·"…하여")로
  끝나거나, 말줄임("…")·끊긴 괄호·쉼표로 끝나거나, 낱말 중간에서 끊긴(근거 글자에 그 낱말이 더 긴
  꼴로만
  있다) 구절은 미완(incomplete). 고정 글자("정보 없음"·"목표치 확인 필요"·"산출 필요")는 검사하지
  않는다.
- 명세 검사(`problems`)는 모델 답(정리한 dict)과 명세(model_dump) 모두에 쓴다. 경로는 [글자
고치기]와 같은
  model_dump 경로("as_is.0.text", "groups.1.items.0.text", "proposal.cells.연구목표").
- 교정 재요청 뒤에도 남으면 `salvage`: 그 칸 글자 안의 **온전한 낱말 묶음**(연속한 낱말, 끝 낱말의
조사·
  연결어미만 덜 수 있다) 중 완결되고 상한 안이며 출처에 있는 가장 긴 것으로 바꾼다 — 낱말을 자르지
  않는다. 끝 낱말(한국어 구의 머리)을 지키는 묶음을 먼저 고른다. 그런 묶음이 없으면 빼도 되는
  칸(설명 줄·
  산출물·기법 항목·4번째 As-Is 칸)은 빼고, 아니면 None(명세를 받지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from rra.domain.models.figure import MAX_BOX, MAX_LABEL, MAX_LINE, NEED_CALC
from rra.domain.rules.schedule import TARGET_UNKNOWN

PHRASE_INCOMPLETE = "figure_phrase_incomplete"
PHRASE_TOO_LONG = "figure_phrase_too_long"
PHRASE_CODES: frozenset[str] = frozenset({PHRASE_INCOMPLETE, PHRASE_TOO_LONG})
TIGHTEN = 0.75  # 9pt 미달로 다시 그릴 때 상한 배율
MIN_LIMIT = 6
EXEMPT: frozenset[str] = frozenset({"정보 없음", TARGET_UNKNOWN, NEED_CALC})

# 종류 → 칸(일반 경로, 목록 자리는 []) → 글자 수 상한(띄어쓰기 포함)
FIELD_LIMITS: dict[str, dict[str, int]] = {
    "as_is_to_be": {"as_is[].text": 20, "to_be[].text": 20, "solution": 14},
    "technique": {"groups[].items[].text": 16, "rows[].name": 16},
    "concept": {"boxes[].lines[]": 20},
    "process": {"stages[].name": 12, "stages[].outputs[]": 16},
    "schedule": {"stages[].name": 14},
    "roadmap": {
        "metrics[].name": 12,
        "metrics[].target": 16,
        "stages[].name": 12,
        "stages[].desc": 18,
    },
    "comparison": {"projects[].cells.*": 18, "proposal.cells.*": 18},
    "stat_chart": {},  # 이름·값은 검증 수치(table_facts) 표기 그대로
}
FIELD_LABELS: dict[str, str] = {
    "as_is[].text": "As-Is 칸 글자(as_is 의 text)",
    "to_be[].text": "To-Be 칸 글자(to_be 의 text)",
    "solution": "가운데 핵심 해결 방안(solution)",
    "groups[].items[].text": "묶음 항목 글자(items 의 text)",
    "rows[].name": "평가 기준 이름(rows 의 name)",
    "boxes[].lines[]": "상자 설명 줄(lines)",
    "stages[].name": "단계 이름(stages 의 name)",
    "stages[].outputs[]": "산출물(outputs)",
    "metrics[].name": "성과지표 이름(metrics 의 name)",
    "metrics[].target": "목표치(metrics 의 target)",
    "stages[].desc": "활용 단계 설명(stages 의 desc)",
    "projects[].cells.*": "기존 과제 칸 글자(cells)",
    "proposal.cells.*": "제안 과제 칸 글자(cells)",
}
# 스키마 상한 (모델 답이 이것을 넘으면 형식 오류 — 자르지 않고 교정 재요청)
_LABEL_KEYS = frozenset({"label", "name", "title", "tag"})
_BOX_KEYS = frozenset({"text", "solution", "target", "desc", "amount"})
_BOX_LISTS = frozenset({"lines", "outputs"})

RULES_PROMPT = (
    "[칸 글자 규칙] 칸마다 아래 글자 수(띄어쓰기 포함) 안에서 **뜻이 완결된 짧은 "
    "구절**로 쓴다 — 명사형으로 끝내거나(…산정·…구축·…부족) 완결된 구로. 초안 문장을 "
    "앞에서부터 잘라 옮기지 말고 핵심 낱말을 골라 다시 묶는다. 조사·연결어미"
    "(…으로·…를·…을·…의·…및·…하여·…하고·…위한)로 끝내지 않고, 말줄임(…)을 쓰지 "
    "않는다. 낱말은 초안·입력·근거에 있는 말 그대로 쓴다 — 조사는 빼도 되고 동사는 "
    "'…함·…됨' 명사형으로 바꿔도 되지만, 다른 낱말로 바꿔 쓰지 않는다('남아 있음' → "
    "'잔존', '추적하지 못함' → '미추적' 같은 한자어 바꿔 쓰기 금지). 글자 수는 띄어쓰기를 "
    "넣어 세고, 넘으면 꾸밈말을 뺀다. "
    "예: '신설역 수요를 별도 가정으로'(×, 끊김) → '신설역 수요 별도 가정'(○)."
)

_TOKEN_STRIP = "()[]「」『』\"'“”‘’.!?:;"  # noqa: S105 — 낱말 앞뒤 기호
_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
_HANGUL = re.compile(r"[가-힣]")
# 끝에 오면 끊긴 구절인 낱말 (홀로 선 낱말)
_DANGLING_WORDS: frozenset[str] = frozenset(
    {
        "및",
        "또는",
        "그리고",
        "혹은",
        "또한",
        "하지만",
        "등을",
        "등의",
        "등과",
        "등으로",
        "위해",
        "위한",
        "통해",
        "통한",
        "대한",
        "대해",
        "따라",
        "따른",
        "관한",
        "의한",
        "인한",
        "같은",
        "있는",
        "없는",
        "하는",
        "되는",
        "할",
        "될",
    }
)
# 앞에 오면 끊긴 구절인 낱말
_DANGLING_START: frozenset[str] = frozenset(
    {"및", "또는", "그리고", "혹은", "또한", "하지만", "등", "등의", "등을", "위한", "통한", "대한"}
)
# 끝 낱말이 이것으로 끝나면 조사·연결어미 — 길이 순(긴 것 먼저)
_SUFFIXES: tuple[str, ...] = tuple(
    sorted(
        {
            # 조사
            "으로의",
            "에서의",
            "으로써",
            "으로서",
            "으로는",
            "으로",
            "에서",
            "에게",
            "에는",
            "에도",
            "와의",
            "과의",
            "로의",
            "로써",
            "로서",
            "부터",
            "까지",
            "보다",
            "처럼",
            "마다",
            "를",
            "는",
            "을",
            "은",
            "에",
            "와",
            "며",
            # 연결어미·관형형
            "해",
            "하여",
            "하여서",
            "해서",
            "하고",
            "하고자",
            "고자",
            "하며",
            "하면",
            "하는",
            "하기",
            "하도록",
            "하거나",
            "하지만",
            "하면서",
            "되어",
            "되고",
            "되며",
            "되는",
            "되기",
            "되도록",
            "이며",
            "이고",
            "이나",
            "거나",
            "지만",
            "면서",
            "도록",
            "려고",
            "위해",
            "위한",
            "통해",
            "통한",
            "대한",
            "대해",
            "따라",
            "따른",
            "관한",
            "의한",
            "인한",
            "있는",
            "없는",
            "같은",
            "될",
        },
        key=len,
        reverse=True,
    )
)
# 앞 낱말이 이것으로 끝나면 앞 구절이 잘린 것 ("예측해 수송계획에 쓴다")
_CONNECTIVES: frozenset[str] = frozenset(
    {"해", "하여", "해서", "하여서", "하고", "하며", "되어", "되고", "되며", "통해", "위해", "따라"}
)
# 받침 뒤 조사일 수도, 낱말 끝일 수도 있는 글자 — 낱말이면 두지 않는다
_AMBIGUOUS: tuple[str, ...] = ("의", "과", "로", "이", "가", "도", "만")
_NOUNS_ENDING = {
    "의": (
        "회의",
        "논의",
        "정의",
        "협의",
        "합의",
        "건의",
        "의의",
        "주의",
        "강의",
        "심의",
        "토의",
        "모의",
        "문의",
        "결의",
        "동의",
        "창의",
        "편의",
        "유의",
        "민의",
        "이의",
    ),
    "과": (
        "효과",
        "결과",
        "성과",
        "통과",
        "초과",
        "경과",
        "부과",
        "학과",
        "교과",
        "투과",
        "간과",
        "일과",
    ),
    "로": (
        "선로",
        "경로",
        "철로",
        "통로",
        "항로",
        "도로",
        "진로",
        "회로",
        "수로",
        "노로",
        "활로",
        "판로",
        "미로",
        "공로",
        "기로",
        "과로",
        "궤로",
        "차로",
        "선로로",
    ),
    "을": ("마을",),
    "해": (
        "피해",
        "이해",
        "재해",
        "손해",
        "방해",
        "장해",
        "침해",
        "견해",
        "분해",
        "오해",
        "저해",
        "훼해",
        "올해",
        "새해",
        "지난해",
        "한해",
    ),
    "에": (),
    "와": (),
    "며": (),
}
# 낱말 중간 끊김 판정 — 근거 낱말에서 이것으로 시작하는 나머지는 조사·어미(끊김이 아니다)
_ENDING_STARTS: tuple[str, ...] = (
    "하",
    "되",
    "한",
    "할",
    "함",
    "해",
    "했",
    "된",
    "될",
    "됨",
    "이",
    "가",
    "을",
    "를",
    "은",
    "는",
    "의",
    "에",
    "로",
    "으로",
    "와",
    "과",
    "도",
    "만",
    "까지",
    "부터",
    "보다",
    "처럼",
    "적",
    "화",
    "성",
    "별",
    "용",
    "상",
    "률",
    "율",
    "들",
    "등",
    "임",
    "였",
    "입",
    "인",
    "일",
    "형",
    "간",
    "내",
    "외",
    "중",
    "시",
    "및",
    "다",
)
# 조사인지 볼 때 쓰는 나머지 (같은 낱말 줄기가 다른 조사로도 쓰였는가)
_NOMINAL_PARTICLES: frozenset[str] = frozenset(
    {
        "이",
        "가",
        "을",
        "를",
        "은",
        "는",
        "의",
        "에",
        "로",
        "으로",
        "와",
        "과",
        "도",
        "만",
        "에서",
        "에게",
        "에는",
        "와의",
        "과의",
        "으로의",
        "까지",
        "부터",
        "보다",
        "처럼",
        "이다",
        "이며",
        "이고",
        "이나",
    }
)


@dataclass(frozen=True)
class Slot:
    """명세의 칸 하나 — path 는 model_dump 경로, field 는 일반 경로(FIELD_LIMITS 키)."""

    path: str
    field: str
    text: str
    limit: int


@dataclass(frozen=True)
class Problem:
    slot: Slot
    code: str
    reason: str | None = None  # 미완 사유 (한국어 짧은 말)


# ── 칸·상한 ─────────────────────────────────────────────
def limits_for(kind: str, factor: float = 1.0) -> dict[str, int]:
    """칸별 글자 수 상한 — 다시 그릴 때는 factor(TIGHTEN)를 곱한다(최소 MIN_LIMIT)."""
    return {
        k: max(MIN_LIMIT, int(round(v * float(factor))))
        for k, v in FIELD_LIMITS.get(kind, {}).items()
    }


def _walk(node: Any, path: str, generic: str) -> Iterator[tuple[str, str, Any]]:
    if isinstance(node, Mapping):
        for k, v in node.items():
            key = str(k)
            p = f"{path}.{key}" if path else key
            if generic.endswith(".cells") or generic == "cells":
                g = f"{generic}.*"
            else:
                g = f"{generic}.{key}" if generic else key
            yield from _walk(v, p, g)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}.{i}", f"{generic}[]")
    else:
        yield path, generic, node


def slots(kind: str, data: Mapping[str, Any] | None, *, factor: float = 1.0) -> list[Slot]:
    """명세(dict)의 글자 칸 — 상한이 있는 칸만, 고정 글자는 뺀다."""
    limits = limits_for(kind, factor)
    out: list[Slot] = []
    for path, generic, value in _walk(data or {}, "", ""):
        limit = limits.get(generic)
        if limit is None or not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if not text or text in EXEMPT:
            continue
        out.append(Slot(path, generic, text, limit))
    return out


def schema_overlong(data: Mapping[str, Any] | None) -> list[str]:
    """스키마 상한(이름 40·칸 30·줄 60자)을 넘는 글자 — 자르지 않고 교정 재요청에 알린다."""
    out: list[str] = []
    for path, _generic, value in _walk(data or {}, "", ""):
        if not isinstance(value, str):
            continue
        parts = path.split(".")
        key = next((p for p in reversed(parts) if not p.isdigit()), "")
        if key == "source":
            continue
        limit = (
            MAX_LABEL
            if key in _LABEL_KEYS
            else MAX_BOX
            if key in _BOX_KEYS or key in _BOX_LISTS
            else MAX_LINE
        )
        if len(" ".join(value.split())) > limit:
            out.append(" ".join(value.split()))
    return out


# ── 완결성 ──────────────────────────────────────────────
def _tokens(text: str) -> list[str]:
    return " ".join(str(text).split()).split(" ") if str(text).strip() else []


def _bare(token: str) -> str:
    return token.strip(_TOKEN_STRIP)


def _is_noun_ending(token: str, ending: str) -> bool:
    return any(token.endswith(n) for n in _NOUNS_ENDING.get(ending, ()))


def _stem_known(stem: str, ending: str, pool: Any) -> bool:
    """줄기(stem)가 근거 글자에서 다른 조사와도 쓰였는가 — 그러면 끝 글자(ending)는 조사다."""
    if pool is None or len(stem) < 2:
        return False
    words = getattr(pool, "words", frozenset())
    if stem in words:
        return True
    for w in words:
        if w.startswith(stem) and len(w) > len(stem):
            rem = w[len(stem) :]
            if rem != ending and rem in _NOMINAL_PARTICLES:
                return True
    return False


def dangling_suffix(token: str, pool: Any = None) -> str | None:
    """끝 낱말의 조사·연결어미 → 그 글자(없으면 None). 받침 뒤 '의·과·로' 처럼 낱말 끝일 수도 있는
    글자는
    낱말 목록(회의·효과·선로…)이면 두지 않고, 근거에서 같은 줄기가 다른 조사로도 쓰였을 때만 조사로
    본다."""
    t = _bare(token)
    if not t or not _HANGUL.search(t):
        return None
    if t in _DANGLING_WORDS:
        return t
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) > len(suf):
            if _is_noun_ending(t, suf):
                return None
            return suf
    for amb in _AMBIGUOUS:
        if t.endswith(amb) and len(t) > len(amb):
            if _is_noun_ending(t, amb):
                return None
            if _stem_known(t[: -len(amb)], amb, pool):
                return amb
    return None


def _final_rieul(token: str) -> bool:
    """마지막 글자 받침이 ㄹ (할·될·늦어질 — '…ㄹ 수' 의 관형형)."""
    t = _bare(token)
    if not t or not ("가" <= t[-1] <= "힣"):
        return False
    return (ord(t[-1]) - 0xAC00) % 28 == 8


def _mid_word(token: str, pool: Any) -> bool:
    """근거 글자에 이 낱말이 그대로(또는 조사·어미를 붙인 꼴로) 없고, 더 긴 낱말의
    앞부분으로만 있다."""
    if pool is None:
        return False
    t = _bare(token)
    if not t or not _WORD.fullmatch(t):
        return False
    words = getattr(pool, "words", frozenset())
    key = t.casefold()
    if key in words:
        return False
    longer = [w for w in words if w.startswith(key) and len(w) > len(key)]
    if not longer:
        return False
    return not any(w[len(key) :].startswith(_ENDING_STARTS) for w in longer)


def is_complete(text: str, pool: Any = None) -> bool:
    return incomplete_reason(text, pool) is None


def incomplete_reason(text: str, pool: Any = None) -> str | None:
    """미완 사유(짧은 한국어) — 없으면 None."""
    value = " ".join(str(text).split())
    if not value or value in EXEMPT:
        return None
    if "…" in value or "..." in value:
        return "말줄임"
    if value[-1] in ",·/-~(+&":
        return "끊긴 기호"
    if value.count("(") != value.count(")"):
        return "닫히지 않은 괄호"
    toks = _tokens(value)
    if not toks:
        return None
    first = _bare(toks[0])
    if len(toks) > 1 and (first in _DANGLING_START or dangling_suffix(first, pool) in _CONNECTIVES):
        return "접속어로 시작"
    last = toks[-1]
    if len(toks) > 1 and _bare(last) == "수" and _final_rieul(toks[-2]):
        return "조사·연결어미로 끝남"  # "…늦어질 수"
    if dangling_suffix(last, pool):
        return "조사·연결어미로 끝남"
    if _mid_word(last, pool):
        return "낱말 중간에서 끊김"
    return None


def phrase_problem(text: str, limit: int, pool: Any = None) -> str | None:
    """칸 글자 하나 → 위반 코드(PHRASE_TOO_LONG | PHRASE_INCOMPLETE) 또는 None."""
    value = " ".join(str(text).split())
    if value in EXEMPT:
        return None
    if incomplete_reason(value, pool):
        return PHRASE_INCOMPLETE
    if len(value) > int(limit):
        return PHRASE_TOO_LONG
    return None


def problems(
    kind: str,
    data: Mapping[str, Any] | None,
    pool: Any = None,
    *,
    factor: float = 1.0,
    exempt: Iterable[str] = (),
) -> list[Problem]:
    """명세(dict)의 칸 글자 위반 — exempt 글자(제안자가 요청에 적은 글자)는 검사하지 않는다."""
    skip = {" ".join(str(x).split()) for x in exempt if x}
    out: list[Problem] = []
    for s in slots(kind, data, factor=factor):
        if s.text in skip or any(s.text in x for x in skip):
            continue
        code = phrase_problem(s.text, s.limit, pool)
        if code:
            out.append(Problem(s, code, incomplete_reason(s.text, pool)))
    return out


# ── 프롬프트 ─────────────────────────────────────────────
def limits_prompt(kind: str, factor: float = 1.0) -> str:
    """[칸 글자 수 상한] 구획 — 칸마다 상한과 완결 규칙. 상한이 없는 종류(수치 그래프)는
    빈 문자열."""
    limits = limits_for(kind, factor)
    if not limits:
        return ""
    lines = [f"- {FIELD_LABELS.get(k, k)}: {v}자 안" for k, v in limits.items()]
    return "[칸 글자 수 상한]\n" + "\n".join(lines) + "\n" + RULES_PROMPT


def correction_hint(bad: Iterable[Problem], *, limit: int = 6) -> str:
    """교정 재요청에 붙일 한 단락 — 어느 칸이 왜 걸렸는지(글자·상한)."""
    rows = []
    for p in list(bad)[:limit]:
        why = (
            f"{p.slot.limit}자 넘음({len(p.slot.text)}자)"
            if p.code == PHRASE_TOO_LONG
            else f"끝맺지 않은 구절({p.reason or '끊김'})"
        )
        rows.append(f"'{p.slot.text}' — {why}")
    if not rows:
        return ""
    return (
        "다음 칸 글자는 받을 수 없다 — 상한 안에서 뜻이 완결된 짧은 구절로 다시 쓴다"
        "(잘라 쓰지 않는다): " + "; ".join(rows)
    )


# ── 대체: 온전한 낱말 묶음 ───────────────────────────────
def strip_ending(token: str, pool: Any = None) -> str | None:
    """끝 낱말에서 조사·연결어미만 던 줄기 — 덜 것이 없거나 줄기가 비면 None. 낱말
    자체는 자르지 않는다."""
    t = _bare(token)
    suf = dangling_suffix(t, pool)
    if not suf or suf == t or t in _DANGLING_WORDS:
        return None
    stem = t[: -len(suf)]
    if not stem or dangling_suffix(stem, pool):
        return None
    return stem


def complete_window(text: str, limit: int, pool: Any = None) -> str | None:
    """text 안의 연속한 온전한 낱말 묶음(끝 낱말은 조사·어미만 덜 수 있다) 중 완결되고 limit 안이며
    출처(pool.has_text)에 있는 것 — 끝 낱말을 지키는 묶음 → 긴 것 → 앞쪽 순. 없으면 None."""
    toks = _tokens(text)
    n = len(toks)
    best: tuple[tuple[bool, int, int], str] | None = None
    for i in range(n):
        for j in range(n, i, -1):
            window = toks[i:j]
            variants = [window]
            stem = strip_ending(window[-1], pool)
            if stem:
                variants.append([*window[:-1], stem])
            for v in variants:
                if n >= 2 and len(v) < 2:
                    continue
                s = " ".join(v)
                if len(s) > limit or phrase_problem(s, limit, pool):
                    continue
                if pool is not None and hasattr(pool, "has_text") and not pool.has_text(s):
                    continue
                score = (j == n, len(s), -i)
                if best is None or score > best[0]:
                    best = (score, s)
    return best[1] if best else None


# 빼도 되는 칸 — (목록 이름, 남겨야 할 최소 개수)
_DROPPABLE: dict[str, int] = {"lines": 1, "outputs": 0, "items": 1, "as_is": 3, "to_be": 3}


def _get(node: Any, parts: list[str]) -> Any:
    for p in parts:
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node


def _set(node: Any, parts: list[str], value: Any) -> None:
    parent = _get(node, parts[:-1])
    key: Any = int(parts[-1]) if isinstance(parent, list) else parts[-1]
    parent[key] = value


def _drop_target(parts: list[str]) -> tuple[list[str], int] | None:
    """칸 경로 → (빼면 되는 목록의 경로, 그 목록에서의 자리). 빼도 되는 칸이 아니면 None."""
    for k in range(len(parts) - 1, 0, -1):
        if parts[k].isdigit() and parts[k - 1] in _DROPPABLE:
            return parts[: k - 1 + 1], int(parts[k])
    return None


def salvage(
    kind: str,
    data: Mapping[str, Any],
    pool: Any = None,
    *,
    factor: float = 1.0,
    exempt: Iterable[str] = (),
    also: Iterable[str] = (),
) -> dict[str, Any] | None:
    """교정 재요청 뒤에도 남은 칸 글자 위반을 규칙으로 고친 새 dict — 칸마다 `complete_window`,
    없으면 빼도 되는 칸은 빼고, 둘 다 안 되면 None(명세를 받지 않는다). 낱말을 자르지 않는다.
    also: 출처 검사(validate_spec)에 걸린 칸 글자 — 같은 방법으로(출처에 있는 낱말 묶음) 바꾼다."""
    import copy

    out: dict[str, Any] = copy.deepcopy(dict(data))
    bad = problems(kind, out, pool, factor=factor, exempt=exempt)
    extra = {" ".join(str(t).split()) for t in also if t}
    seen = {p.slot.path for p in bad}
    bad += [
        Problem(s, PHRASE_INCOMPLETE, "출처 밖 낱말")
        for s in slots(kind, out, factor=factor)
        if s.text in extra and s.path not in seen
    ]
    drops: list[tuple[list[str], int]] = []
    for p in bad:
        parts = p.slot.path.split(".")
        window = complete_window(p.slot.text, p.slot.limit, pool)
        if window is not None:
            _set(out, parts, window)
            continue
        target = _drop_target(parts)
        if target is None:
            return None
        drops.append(target)
    # 뒤 자리부터 뺀다 (앞 자리 번호가 바뀌지 않게)
    for list_path, idx in sorted(drops, key=lambda t: (t[0], t[1]), reverse=True):
        seq = _get(out, list_path)
        if not isinstance(seq, list) or idx >= len(seq):
            return None
        if len(seq) - 1 < _DROPPABLE[list_path[-1]]:
            return None
        del seq[idx]
    if problems(kind, out, pool, factor=factor, exempt=exempt):
        return None
    return out
