"""문제 정의 카드 — AI 출력(JSON) 검증·근거 판정·수정 반영 (ADR 0065, 계약 problem-card.md 2·3절).

순수 함수. AI 가 보낸 값은 비신뢰다:
- JSON 객체만 받는다. 글 칸은 길이·태그를 정리한 뒤, 한자·가나가 섞였거나 제안 입력에 없는
  숫자·기관명·법령명이 들면 **그 칸을 비운다**(지어낸 내용을 카드에 남기지 않는다).
- 영문 기능 문장에 한글이 있으면 비운다. 발명 원리는 번호만 받고 이름은 `triz` 표로 바꿔 쓴다.
- '근거 있음/추정'은 AI 의 자기 신고가 아니라 규칙으로 정한다 — 항목 글의 핵심 낱말이 제안 입력
  (가제·현황·원인·한계·목표)에 있으면 '근거 있음'.
- 문제어에서 장소어(`facets.place` 의 낱말, novelty.yaml 의 장소 말)·일반어·추상화 단의 말을 뺀다.
- 제안자의 원인 칸과 AI 근본 원인이 낱말로 겹치지 않으면 '확인 필요'(`cause_mismatch`).
- 사용자가 고친 항목(origin=user)은 다시 진단해도 그대로 둔다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, get_args

from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import (
    BASIS_GUESSED,
    BASIS_STATED,
    CARD_DEPENDENTS,
    CARD_FIELDS,
    LADDER_LEVELS,
    MAX_CAUSES,
    MAX_CODE,
    MAX_IPC,
    MAX_SCIENCE_CLASS,
    SIGNALS,
    CardBasis,
    CardField,
    CardText,
    ClassCode,
    CodeKind,
    Contradiction,
    Facets,
    LadderStep,
    Nature,
    ProblemCard,
    ProblemNature,
    ProblemTerms,
    ProjectMode,
    Rerun,
)
from rra.domain.rules import triz
from rra.domain.rules.card_edits import strip_contacts
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.keywords import KeywordRule, query_keywords, stem, tokens
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.novel_recommendation import unsupported_names
from rra.domain.rules.novelty import ProblemAxisRule, is_place_ko
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted

METHOD_CORE = "core"
CHECK_CAUSE_MISMATCH = "cause_mismatch"
# 항목 글의 핵심 낱말 중 이 비율 이상이 제안 입력에 있으면 '근거 있음'
BASIS_MIN_RATIO = 0.6

# 칸을 비운 사유 (기록·보고용 열거값 — 화면에 내보내지 않는다)
CLEARED_FOREIGN = "foreign_script"
CLEARED_NUMBER = "unsupported_number"
CLEARED_NAME = "unsupported_name"
CLEARED_HANGUL = "hangul_in_english"
CLEARED_FORMAT = "bad_format"
CLEARED_PLACE = "place_term"

FACET_NAMES = ("phenomenon", "target", "place", "cause", "harm", "desired")
SIGNAL_LABELS: dict[str, str] = {
    "broad_scope": "범위가 넓음",
    "unclear_cause": "원인이 뚜렷하지 않거나 여러 가지",
    "safety_failure": "안전·고장과 이어진 문제",
    "policy_service": "정책·서비스·이용자 문제",
    "few_analogies": "다른 분야 사례가 적음",
}
FIELD_LABELS: dict[str, str] = {
    "function_ko": "기능 문장",
    "function_en": "영문 기능 문장",
    "ladder": "추상화 사다리",
    "terms": "문제어",
    "cause": "근본 원인",
    "contradiction": "모순",
    "ipc": "특허 분류",
    "science_class": "과학기술 분류",
    "facets": "항목 나누기",
    "nature": "문제 성격",
}
_LADDER_KEYS = {
    "구체": ("concrete", "구체"),
    "일반화": ("general", "일반화"),
    "추상화": ("abstract", "추상화"),
}
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
_EN_TOKEN = re.compile(r"[a-z][a-z0-9-]*")
# IPC: 섹션(A~H) + 클래스 2자리 + 서브클래스 1자 [+ 메인그룹[/서브그룹]]
# — "A01M 29/00"·"A01M-029/00"
_IPC = re.compile(r"\A([A-H]\d{2}[A-Z])(?:[\s\-]*(\d{1,4})(?:\s*/\s*(\d{1,6}))?)?\Z")
# 저장 자료의 표기 — 뒤에 판 표시 등이 붙는다("G06Q-050/00B0"). 앞부분만 읽는다
_IPC_STORED = re.compile(r"\A([A-H]\d{2}[A-Z])[\s\-]*(\d{1,4})\s*/\s*(\d{2,6})")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def request_texts(req: ProposalRequest) -> list[str]:
    """제안 입력 — 근거 판정·수치 대조의 기준(가제·현황·원인·한계·목표)."""
    return [
        t
        for t in (req.title_hint, req.current_state, req.root_cause, req.limitation, req.goal)
        if t
    ]


# ── 글 칸 검사 ─────────────────────────────────────────────
def _plain(value: object) -> str:
    if isinstance(value, Mapping):
        value = value.get("value") or value.get("text") or ""
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value)).strip()


def checked_text(value: object, allowed: Sequence[str]) -> tuple[str, str | None]:
    """AI 글 한 칸 → (글, 비운 사유). 어긋나면 ("", 사유)."""
    text = _plain(value)
    if not text:
        return "", None
    if has_foreign_script(text):
        return "", CLEARED_FOREIGN
    if unsupported_numbers(text, allowed):
        return "", CLEARED_NUMBER
    if unsupported_names(text, allowed):
        return "", CLEARED_NAME
    return text, None


def basis_of(text: str, req_texts: Sequence[str], rule: KeywordRule) -> CardBasis:
    """항목 글의 핵심 낱말(일반어·숫자·한 글자 제외)이 제안 입력에 있는가 — 규칙 판정.
    낱말은 조사를 뗀 어간으로, 한쪽이 다른 쪽의 앞부분이면 같은 말로 본다(침입 ↔ 침입해)."""
    words = query_keywords(text or "", rule)
    if not words:
        return BASIS_GUESSED
    have = query_keywords(" ".join(req_texts), rule)
    hits = sum(1 for w in words if any(h.startswith(w) or w.startswith(h) for h in have))
    return BASIS_STATED if hits / len(words) >= BASIS_MIN_RATIO else BASIS_GUESSED


def shares_words(a: str, b: str, rule: KeywordRule) -> bool:
    """두 글이 핵심 낱말을 하나라도 함께 쓰는가."""
    left, right = query_keywords(a or "", rule), query_keywords(b or "", rule)
    return any(x.startswith(y) or y.startswith(x) for x in left for y in right)


# ── 분류 코드 ──────────────────────────────────────────────
def normalize_ipc(code: object, *, stored: bool = False) -> str | None:
    """IPC 표기를 한 가지로 — "A01M-029/00"·"a01m29/00" → "A01M 29/00". 형식이 아니면 None.
    메인그룹만 있으면 서브그룹 "00", 서브클래스만 있으면 "A01M".
    stored: 저장 자료의 코드 — 뒤에 붙은 꼬리("…/00B0")는 무시하고 앞부분만 읽는다. AI·사용자가
    보낸 코드에는 쓰지 않는다(형식이 어긋나면 받지 않는다)."""
    if not isinstance(code, str):
        return None
    text = " ".join(code.upper().split())
    m = _IPC.match(text) or (_IPC_STORED.match(text) if stored else None)
    if m is None:
        return None
    sub, main, group = m.groups()
    if main is None:
        return sub
    return f"{sub} {int(main)}/{(group or '00').zfill(2)}"


def ipc_group_prefix(code: str) -> str | None:
    """저장 자료 대조용 앞부분 — 메인그룹까지("A01M 29/"). 서브클래스뿐이면 그대로."""
    norm = normalize_ipc(code)
    if norm is None:
        return None
    return norm.split("/", 1)[0] + "/" if "/" in norm else norm


def _code_items(raw: object) -> list[str]:
    out: list[str] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if isinstance(item, Mapping):
            item = item.get("code") or item.get("name") or item.get("label")
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _ipc_codes(raw: object) -> list[ClassCode]:
    out: list[ClassCode] = []
    for item in _code_items(raw):
        code = normalize_ipc(item)
        if code is None or any(c.code == code for c in out):
            continue
        out.append(ClassCode(code=code))  # 이름(label)은 AI 것을 쓰지 않는다 — 확인 결과로만
    return out[:MAX_IPC]


def _science_codes(raw: object) -> list[ClassCode]:
    """국가과학기술표준분류 후보 — 분류 이름(예: 철도교통기술)을 code 칸에 둔다."""
    out: list[ClassCode] = []
    for item in _code_items(raw):
        name = _plain(item)[:MAX_CODE].strip()
        if not name or has_foreign_script(name) or any(c.code == name.upper() for c in out):
            continue
        out.append(ClassCode(code=name))
    return out[:MAX_SCIENCE_CLASS]


# ── 문제어 ─────────────────────────────────────────────────
def _term_words(raw: object) -> list[str]:
    """문제어 낱말 — 조사를 떼지 않는다(AI 가 낸 명사 그대로: "주행로" 를 줄이지 않는다)."""
    out: list[str] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if isinstance(item, str):
            out.extend(w.lower() for w in _WORD.findall(item))
    return out


def clean_terms(
    raw: object,
    *,
    place: str = "",
    concrete: str = "",
    general: str = "",
    abstract: str = "",
    axis: ProblemAxisRule | None = None,
    rule: KeywordRule | None = None,
    subject: str = "",
) -> tuple[ProblemTerms, int]:
    """AI 문제어 → 낱말 단위로 정리한 문제어와 뺀 낱말 수.

    뺀다: 장소어(`facets.place` 의 낱말·axis 의 장소 말)·일반어·한 글자·한자/가나·추상화 단에만
    나오는 대상어. 국문 칸에는 한글 낱말만, 영문 칸에는 영문 낱말만 둔다.

    subject: 국문·영문 기능 문장(대상 + 작용, 장소어를 넣지 않는 칸). 여기 나온 말은
      axis 의 장소 말 목록에 있어도 **대상어로 남긴다** — "궤도 틀림"처럼 철도 시설 자체가 문제의
      대상인 과제에서 핵심 대상어(궤도·track)가 사라지지 않게(2026-11-10 실제 카드에서 확인).
      `facets.place` 에 적힌 말은 그래도 뺀다."""
    rule = rule or KeywordRule()
    data = raw if isinstance(raw, Mapping) else {}
    place_words = set(tokens(place))
    subject_ko = {t for t in tokens(subject) if _HANGUL.search(t)}
    subject_en = set(_EN_TOKEN.findall(subject.lower()))

    def is_subject(w: str, base: str) -> bool:
        return any(t == w or t.startswith(base) for t in subject_ko)

    near = set(tokens(f"{concrete} {general}"))
    far = set(tokens(abstract)) - near
    place_en = {p.lower() for p in axis.place_en} if axis is not None else set()
    dropped = 0

    def ko(key: str, *, objects: bool) -> list[str]:
        nonlocal dropped
        out: list[str] = []
        for w in _term_words(data.get(key)):
            base = stem(w)  # 견줄 때만 어간으로
            bad = (
                len(w) < 2
                or not _HANGUL.search(w)
                or has_foreign_script(w)
                or bool({w, base} & rule.generic_terms)
                or bool({w, base} & place_words)
                or (
                    axis is not None
                    and (is_place_ko(w, axis) or w in axis.place_ko)
                    and not (objects and is_subject(w, base))
                )
                or (objects and bool({w, base} & far))
            )
            if bad:
                dropped += 1
            elif w not in out:
                out.append(w)
        return out

    def en(key: str, *, objects: bool = False) -> list[str]:
        nonlocal dropped
        out: list[str] = []
        for item in data.get(key) if isinstance(data.get(key), (list, tuple)) else []:
            if not isinstance(item, str) or _HANGUL.search(item) or has_foreign_script(item):
                dropped += 1
                continue
            for w in _EN_TOKEN.findall(item.lower()):
                if len(w) < 2 or (w in place_en and not (objects and w in subject_en)):
                    dropped += 1
                elif w not in out:
                    out.append(w)
        return out

    terms = ProblemTerms(
        objects_ko=ko("objects_ko", objects=True),
        actions_ko=ko("actions_ko", objects=False),
        objects_en=en("objects_en", objects=True),
        actions_en=en("actions_en"),
    )
    return terms, dropped


# ── 파싱 ───────────────────────────────────────────────────
@dataclass
class ParsedCard:
    """검증 결과. card 가 None 이면 진단 실패(기능 문장 없음·객체 아님)."""

    card: ProblemCard | None = None
    cleared: list[tuple[str, str]] = field(default_factory=list)  # (칸, 비운 사유)
    changed: list[str] = field(default_factory=list)  # 바꿔 쓴 칸(원리 이름·문제어·코드 표기)


def _ladder(raw: object, allowed: Sequence[str], out: ParsedCard) -> list[LadderStep]:
    by_level: dict[str, object] = {}
    if isinstance(raw, Mapping):
        for level, keys in _LADDER_KEYS.items():
            by_level[level] = next((raw[k] for k in keys if k in raw), "")
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, Mapping) and item.get("level") in LADDER_LEVELS:
                by_level[str(item["level"])] = item.get("text") or ""
    steps: list[LadderStep] = []
    for level in LADDER_LEVELS:
        text, why = checked_text(by_level.get(level, ""), allowed)
        if why:
            out.cleared.append((f"ladder.{level}", why))
        if text:
            steps.append(LadderStep(level=level, text=text))
    return steps


def _enum(value: object, choices: Iterable[str]) -> Any:
    return value if isinstance(value, str) and value in tuple(choices) else None


def parse_card(
    data: object,
    req: ProposalRequest,
    *,
    axis: ProblemAxisRule | None = None,
    rule: KeywordRule | None = None,
    function_ko: str | None = None,
    place: str = "",
) -> ParsedCard:
    """AI JSON → 카드. 기능 문장이 비면 card=None(계약 2절 — 카드 없이 진행).

    function_ko: 사용자가 고친 기능 문장(다시 만들기 때) — AI 값 대신 쓰고 대조 기준에 넣는다.
    place: 이미 아는 장소 글(다시 만들기 때 카드의 `facets.place`) — AI 가 장소 칸을 비웠을 때.
    """
    out = ParsedCard()
    if not isinstance(data, Mapping):
        return out
    rule = rule or KeywordRule()
    texts = request_texts(req)
    allowed = [*texts, function_ko] if function_ko else texts

    def text_of(name: str, raw: object) -> CardText:
        value, why = checked_text(raw, allowed)
        if why:
            out.cleared.append((name, why))
        return CardText(value=value, basis=basis_of(value, texts, rule))

    raw_facets = data.get("facets") if isinstance(data.get("facets"), Mapping) else {}
    facets = Facets(**{n: text_of(f"facets.{n}", raw_facets.get(n)) for n in FACET_NAMES})

    if function_ko:
        fn_ko = CardText(value=function_ko, origin="user", basis=BASIS_STATED)
    else:
        fn_ko = text_of("function_ko", data.get("function_ko"))
    if not fn_ko.value:
        return out

    en_value, why = checked_text(data.get("function_en"), allowed)
    if en_value and _HANGUL.search(en_value):
        en_value, why = "", CLEARED_HANGUL
    if why:
        out.cleared.append(("function_en", why))
    fn_en = CardText(value=en_value, basis=fn_ko.basis)  # 번역 — 국문 기능 문장의 근거를 따른다

    ladder = _ladder(data.get("ladder"), allowed, out)
    step = {s.level: s.text for s in ladder}
    terms, dropped = clean_terms(
        data.get("terms"),
        place=facets.place.value or place,
        concrete=step.get("구체", ""),
        general=step.get("일반화", ""),
        abstract=step.get("추상화", ""),
        axis=axis,
        rule=rule,
        subject=" ".join(p for p in (fn_ko.value, en_value) if p),
    )
    if dropped:
        out.changed.append("terms")

    raw_con = data.get("contradiction") if isinstance(data.get("contradiction"), Mapping) else {}
    improve, why_i = checked_text(raw_con.get("improve"), allowed)
    worsen, why_w = checked_text(raw_con.get("worsen"), allowed)
    for name, why in (("contradiction.improve", why_i), ("contradiction.worsen", why_w)):
        if why:
            out.cleared.append((name, why))
    raw_principles = raw_con.get("principles")
    principles = triz.principles(raw_principles) if improve and worsen else []
    if isinstance(raw_principles, (list, tuple)) and raw_principles:
        out.changed.append("contradiction.principles")  # 이름은 늘 고정 목록으로 바꿔 쓴다
    contradiction = Contradiction(
        improve=improve,
        worsen=worsen,
        principles=principles,
        basis=basis_of(f"{improve} {worsen}", texts, rule),
    )

    causes: list[CardText] = []
    raw_causes = data.get("causes")
    for i, raw in enumerate(raw_causes if isinstance(raw_causes, (list, tuple)) else []):
        item = text_of(f"causes.{i}", raw)
        if item.value:
            causes.append(item)
    causes = causes[:MAX_CAUSES]

    ipc = _ipc_codes(data.get("ipc"))
    if [c.code for c in ipc] != _code_items(data.get("ipc"))[: len(ipc)]:
        out.changed.append("ipc")
    raw_nature = data.get("nature") if isinstance(data.get("nature"), Mapping) else {}
    raw_signals = data.get("signals") if isinstance(data.get("signals"), (list, tuple)) else []
    card = ProblemCard(
        facets=facets,
        function_ko=fn_ko,
        function_en=fn_en,
        ladder=ladder,
        terms=terms,
        contradiction=contradiction,
        causes=causes,
        ipc=ipc,
        science_class=_science_codes(data.get("science_class")),
        nature=Nature(
            kind=_enum(raw_nature.get("kind"), get_args(ProblemNature)),
            mode=_enum(raw_nature.get("mode"), get_args(ProjectMode)),
        ),
        signals=[s for s in raw_signals if isinstance(s, str) and s in SIGNALS],
        methods=[METHOD_CORE],
    )
    out.card = recheck_cause(card, req, rule)
    return out


# ── '확인 필요' ────────────────────────────────────────────
def recheck_cause(card: ProblemCard, req: ProposalRequest, rule: KeywordRule) -> ProblemCard:
    """제안자의 원인 칸과 AI 근본 원인(첫 칸)이 낱말로 겹치지 않으면 '확인 필요'.
    사용자가 고친 원인은 제안자 본인의 말이므로 확인 필요가 아니다."""
    checks = [c for c in card.checks if c != CHECK_CAUSE_MISMATCH]
    causes = [c.model_copy() for c in card.causes]
    if causes:
        first = causes[0]
        mismatch = (
            first.origin == "ai"
            and bool(first.value)
            and not shares_words(req.root_cause, first.value, rule)
        )
        causes[0] = first.model_copy(update={"needs_check": mismatch})
        if mismatch:
            checks.append(CHECK_CAUSE_MISMATCH)
    return card.model_copy(update={"causes": causes, "checks": checks})


# ── 사용자 항목 보존 ───────────────────────────────────────
def _merge_codes(new: list[ClassCode], old: list[ClassCode], limit: int) -> list[ClassCode]:
    kept = [c for c in old if c.origin == "user"]
    if not kept:
        return new
    for c in new:
        if all(c.code != k.code for k in kept):
            kept.append(c)
    return kept[:limit]


def keep_user_items(card: ProblemCard, previous: ProblemCard | None) -> ProblemCard:
    """다시 진단한 카드에 이전 카드의 사용자 항목(origin=user)을 그대로 얹는다."""
    if previous is None:
        return card
    update: dict[str, Any] = {}
    for name in ("function_ko", "function_en"):
        if getattr(previous, name).origin == "user":
            update[name] = getattr(previous, name)
    if previous.ladder_origin == "user":
        update["ladder"], update["ladder_origin"] = list(previous.ladder), "user"
    if previous.terms.origin == "user":
        update["terms"] = previous.terms
    if previous.contradiction.origin == "user":
        update["contradiction"] = previous.contradiction
    if previous.nature.origin == "user":
        update["nature"] = previous.nature
    causes = list(card.causes)
    for i, old in enumerate(previous.causes):
        if old.origin != "user":
            continue
        if i < len(causes):
            causes[i] = old
        else:
            causes.append(old)
    update["causes"] = causes[:MAX_CAUSES]
    facets = {
        n: getattr(previous.facets, n)
        for n in FACET_NAMES
        if getattr(previous.facets, n).origin == "user"
    }
    if facets:
        update["facets"] = card.facets.model_copy(update=facets)
    update["ipc"] = _merge_codes(card.ipc, previous.ipc, MAX_IPC)
    update["science_class"] = _merge_codes(
        card.science_class, previous.science_class, MAX_SCIENCE_CLASS
    )
    return card.model_copy(update=update)


def user_items_view(card: ProblemCard | None) -> dict[str, str]:
    """프롬프트에 알릴 사용자 항목(이름 → 글) — AI 가 이에 맞춰 나머지를 채운다."""
    if card is None:
        return {}
    return {FIELD_LABELS[f]: field_text(card, f) for f in card.user_fields() if field_text(card, f)}


# ── 수정 반영 ──────────────────────────────────────────────
def field_text(card: ProblemCard, name: str) -> str:
    """항목의 글 표현 — 수정 짝 기록·본인 예시·변경 여부 비교에 쓴다."""
    if name == "function_ko":
        return card.function_ko.value
    if name == "function_en":
        return card.function_en.value
    if name == "ladder":
        return " > ".join(s.text for s in card.ladder)
    if name == "terms":
        t = card.terms
        return ", ".join([*t.objects_ko, *t.actions_ko, *t.objects_en, *t.actions_en])
    if name == "cause":
        return " / ".join(c.value for c in card.causes if c.value)
    if name == "contradiction":
        c = card.contradiction
        return f"{c.improve} ↔ {c.worsen}" if c.improve or c.worsen else ""
    if name == "ipc":
        return ", ".join(c.code for c in card.ipc)
    if name == "science_class":
        return ", ".join(c.code for c in card.science_class)
    if name == "facets":
        return " / ".join(getattr(card.facets, n).value for n in FACET_NAMES if n != "cause").strip(
            " /"
        )
    if name == "nature":
        return " · ".join(p for p in (card.nature.kind, card.nature.mode) if p)
    return ""


def _user_text(new: CardText, old: CardText | None) -> CardText:
    """사용자가 쓴 글 한 칸 — 개인정보를 지우고, 고치기 전 AI 값을 남긴다."""
    value = strip_contacts(new.value)
    if old is None:
        ai_value = ""
    else:
        ai_value = old.value if old.origin == "ai" else old.ai_value
    return CardText(value=value, origin="user", basis=BASIS_STATED, ai_value=ai_value)


def _user_codes(
    new: list[ClassCode], old: list[ClassCode], kind: CodeKind, limit: int
) -> list[ClassCode]:
    out: list[ClassCode] = []
    by_code = {c.code: c for c in old}
    for c in new:
        code = normalize_ipc(c.code) if kind == "ipc" else c.code
        if code is None or any(code == o.code for o in out):
            continue  # IPC 형식이 아닌 코드는 받지 않는다
        same = by_code.get(code)
        out.append(same if same is not None else ClassCode(code=code, origin="user"))
    if out and all(c.origin != "user" for c in out):  # 지우기만 한 수정 — 남은 것도 사용자 확정
        out = [c.model_copy(update={"origin": "user"}) for c in out]
    return out[:limit]


def apply_edits(
    before: ProblemCard, after: ProblemCard, fields: Sequence[str]
) -> tuple[ProblemCard, list[Rerun]]:
    """사용자 수정 반영 — `fields` 에 든 항목만 `after` 에서 가져와 origin=user 로(AI 값은 보존),
    나머지는 `before` 그대로. reruns = `CARD_DEPENDENTS` 의 합집합(순서 유지)."""
    update: dict[str, Any] = {}
    names: list[CardField] = [f for f in CARD_FIELDS if f in fields]
    for name in names:
        if name in ("function_ko", "function_en"):
            update[name] = _user_text(getattr(after, name), getattr(before, name))
        elif name == "ladder":
            update["ladder"] = [
                s.model_copy(update={"text": strip_contacts(s.text)}) for s in after.ladder
            ]
            update["ladder_origin"] = "user"
        elif name == "terms":
            update["terms"] = after.terms.model_copy(update={"origin": "user"})
        elif name == "cause":
            causes: list[CardText] = []
            for i, new in enumerate(after.causes[:MAX_CAUSES]):
                old = before.causes[i] if i < len(before.causes) else None
                if old is not None and old.value == new.value and (i > 0 or old.origin == "user"):
                    causes.append(old)
                else:  # 고친 칸 — 고치지 않았어도 첫 칸은 사용자가 확인한 것으로 본다
                    causes.append(_user_text(new, old))
            update["causes"] = [c for c in causes if c.value]
            if before.facets.cause.value != after.facets.cause.value:
                update["facets"] = before.facets.model_copy(
                    update={"cause": _user_text(after.facets.cause, before.facets.cause)}
                )
        elif name == "contradiction":
            old_c, new_c = before.contradiction, after.contradiction
            ai = old_c.origin == "ai"
            update["contradiction"] = Contradiction(
                improve=strip_contacts(new_c.improve),
                worsen=strip_contacts(new_c.worsen),
                principles=triz.principles(new_c.principles),  # 원리 재검증(번호·이름)
                origin="user",
                basis=BASIS_STATED,
                ai_improve=old_c.improve if ai else old_c.ai_improve,
                ai_worsen=old_c.worsen if ai else old_c.ai_worsen,
            )
        elif name == "ipc":
            update["ipc"] = _user_codes(after.ipc, before.ipc, "ipc", MAX_IPC)
        elif name == "science_class":
            update["science_class"] = _user_codes(
                after.science_class, before.science_class, "science_class", MAX_SCIENCE_CLASS
            )
        elif name == "facets":
            base: Facets = update.get("facets", before.facets)
            changed = {
                n: _user_text(getattr(after.facets, n), getattr(before.facets, n))
                for n in FACET_NAMES
                if n != "cause" and getattr(after.facets, n).value != getattr(base, n).value
            }
            update["facets"] = base.model_copy(update=changed)
        elif name == "nature":
            update["nature"] = after.nature.model_copy(update={"origin": "user"})
    reruns: list[Rerun] = []
    for name in names:
        for r in CARD_DEPENDENTS[name]:
            if r not in reruns:
                reruns.append(r)
    return before.model_copy(update=update), reruns


def apply_derived(card: ProblemCard, derived: ProblemCard) -> ProblemCard:
    """기능 문장을 고친 뒤 다시 만든 것(영문·사다리·문제어) 중 사용자 항목이 아닌 것만 바꾼다.
    다시 만든 값이 비어 있으면 그 칸은 그대로 둔다."""
    update: dict[str, Any] = {}
    if card.function_en.origin != "user" and derived.function_en.value:
        update["function_en"] = derived.function_en
    if card.ladder_origin != "user" and derived.ladder:
        update["ladder"] = list(derived.ladder)
    t = derived.terms
    if card.terms.origin != "user" and (t.objects_ko or t.objects_en):
        update["terms"] = t
    return card.model_copy(update=update)


def with_code_checks(
    card: ProblemCard, checks: Mapping[tuple[str, str], tuple[str, int | None, str]]
) -> ProblemCard:
    """분류 코드 확인 결과((종류, 코드) → (verified, count, label))를 카드에 적는다.
    결과가 없는 코드는 그대로 둔다."""

    def fill(kind: str, codes: list[ClassCode]) -> list[ClassCode]:
        out = []
        for c in codes:
            found = checks.get((kind, c.code))
            if found is not None:
                verified, count, label = found
                c = c.model_copy(update={"verified": verified, "count": count, "label": label})
            out.append(c)
        return out

    return card.model_copy(
        update={
            "ipc": fill("ipc", card.ipc),
            "science_class": fill("science_class", card.science_class),
        }
    )


# ── 화면 ───────────────────────────────────────────────────
def card_lines(card: ProblemCard) -> dict[str, str]:
    """화면 '핵심 문제' 4줄 — 기능 문장·원인·모순·분류."""
    c = card.contradiction
    return {
        "function": card.function_ko.value,
        "cause": card.causes[0].value if card.causes else "",
        "contradiction": f"{c.improve} ↔ {c.worsen}" if c.filled else "",
        "codes": " · ".join(x.code for x in [*card.ipc, *card.science_class]),
    }


def signal_labels(card: ProblemCard) -> list[dict[str, str]]:
    return [{"signal": s, "label": SIGNAL_LABELS[s]} for s in card.signals]


def basis_counts(card: ProblemCard) -> dict[str, int]:
    """근거 있음/추정 분포(값이 있는 글 칸만) — 기록·보고용."""
    items = [getattr(card.facets, n) for n in FACET_NAMES]
    items += [card.function_ko, card.function_en, *card.causes]
    out = {BASIS_STATED: 0, BASIS_GUESSED: 0}
    for item in items:
        if item.value:
            out[item.basis] += 1
    if card.contradiction.filled:
        out[card.contradiction.basis] += 1
    return out
