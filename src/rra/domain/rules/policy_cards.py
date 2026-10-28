"""정책적 중요도 작성안 4개 — 순수 규칙 (2026-10-28 레인 B).

정책 근거(policy_basis)가 없으면 2-가-(1) 은 빈칸이었다. 보강 질문 단계에서 수집된 정책 자료의
원문 구간을 방향별로 묶어 최대 4개 안을 보인다.

- 방향(direction): government(정부 계획 — 국토부 계획·정부 R&D 공고) / company(공사 전략 — 공사
  중장기 경영목표·전략) / audit(감사 지적·현안 — 감사원·경영평가 지적) / regional(지역·사회 정책 —
  남은 구간 중 지역·균형발전·교통약자·안전·탄소 등 사회 정책 어휘가 있는 것).
- 근거 겹침 없음: 한 문서는 한 안에만 들어간다(group_passages). 근거가 있는 방향만큼만 안이 나온다.
- 본문 검증(validate_card): 문장마다 그 안의 구간 id 를 인용해야 하고, 정책·계획명·차수·연도
  (grounding)와 수치(numbers)는 인용한 구간(+제안자 입력)에 있어야 한다. 어기면 그 문장을 버린다
  (정책명 규칙 — 지어낸 정책명 금지). 한자·가나 혼입·빈 문장도 버린다.
- 고른 안(PolicyChoice)은 생성 때 저장소에서 원문과 다시 대조한다(verify_sources, 보안 A) — 통과한
  구간만 근거로 남고 2-가-(1) 은 그 문장을 그대로 쓴다(choice_section, origin=proposer_input).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from rra.domain.models import Chunk, Document, ProposalRequest, Section, Sentence
from rra.domain.models.policy import (
    MAX_CARD_SENTENCE_CHARS,
    MAX_CARD_SENTENCES,
    MAX_CHOICE_SENTENCES,
    MAX_POLICY_CARDS,
    MAX_QUOTE,
    PolicyCard,
    PolicyChoice,
    PolicyDirection,
    PolicySentence,
    PolicySource,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

POLICY_SECTION = "policy_importance"
# 작성안 검색 자료원·자료 종류 (live 결과도 DB 에 들어오지만 ScienceON·NTIS·OpenAlex 라 정책 종류가
# 아니다)
CARD_SOURCES: tuple[str, ...] = ("molit", "rnd_notice", "korail_web", "bai", "mofe")
CARD_DOC_TYPES: frozenset[str] = frozenset({"policy", "rnd_notice", "audit"})
DIRECTIONS: tuple[PolicyDirection, ...] = ("government", "company", "audit", "regional")
DIRECTION_LABELS: dict[str, str] = {
    "government": "정부 계획",
    "company": "공사 전략",
    "audit": "감사 지적·현안",
    "regional": "지역·사회 정책",
}
SOURCE_DIRECTION: dict[str, PolicyDirection] = {
    "molit": "government",
    "rnd_notice": "government",
    "korail_web": "company",
    "bai": "audit",
    "mofe": "audit",
}
CARD_SOURCE_LABELS: dict[str, str] = {
    "molit": "국토교통부",
    "rnd_notice": "정부 R&D 공고",
    "korail_web": "한국철도공사",
    "bai": "감사원",
    "mofe": "기획재정부",
}
_REGIONAL = re.compile(
    r"지역|지방|균형\s?발전|소멸|접근성|교통\s?약자|취약|사회적|국민|일자리|상생|ESG|탄소|친환경|기후"
)
PASSAGES_PER_CARD = 2
# 문장 앞 기호 — 화면이 "○" 를 붙이므로 본문에서는 뗀다
_BULLET = re.compile(r"\A\s*(?:[○●◦•·\-–—]|\d+[.)])\s*")

# 작성안 폐기 사유 (화면에는 개수만, 코드는 기록용)
DROP_EVIDENCE = "evidence_out_of_range"
DROP_UNGROUNDED = "ungrounded"
DROP_NUMBER = "unsupported_number"
DROP_FOREIGN = "foreign_script"
DROP_EMPTY = "empty"

# 2-가-(1) 알림 — "정책 근거 확인 필요" (lint 코드 policy_basis_needed, 화면 라벨은 한국어)
POLICY_BASIS_NEEDED = "policy_basis_needed"
POLICY_BASIS_NEEDED_LABEL = "정책 근거 확인 필요"
POLICY_BASIS_NEEDED_MESSAGE = (
    "정책 근거 확인 필요 — 고른 정책 근거가 없어 비워 둠 "
    "(정책적 중요도 작성안에서 고르거나 직접 작성)"
)


def _squash(text: str) -> str:
    return "".join(text.split())


def is_regional(quote: str) -> bool:
    return bool(_REGIONAL.search(quote))


def group_passages(
    passages: Sequence[PolicySource],
    *,
    exclude_docs: Iterable[str] = (),
    per_card: int = PASSAGES_PER_CARD,
) -> dict[PolicyDirection, list[PolicySource]]:
    """관련도 순 구간 → 방향별 묶음. 한 문서는 한 방향에만(근거 겹침 없음), 방향마다 최대 per_card
    구간(서로 다른 문서). exclude_docs: [다른 안 보기] 때 이미 보인 문서."""
    used: set[str] = set(exclude_docs)
    out: dict[PolicyDirection, list[PolicySource]] = {}
    for direction in ("government", "company", "audit"):
        picked: list[PolicySource] = []
        for p in passages:
            if len(picked) >= per_card:
                break
            if p.doc_id in used or SOURCE_DIRECTION.get(p.source) != direction:
                continue
            picked.append(p)
            used.add(p.doc_id)
        if picked:
            out[direction] = picked
    regional: list[PolicySource] = []
    for p in passages:
        if len(regional) >= per_card:
            break
        if p.doc_id in used or not is_regional(p.quote):
            continue
        regional.append(p)
        used.add(p.doc_id)
    if regional:
        out["regional"] = regional
    return out


def card_id(direction: str, sources: Sequence[PolicySource]) -> str:
    import hashlib

    digest = hashlib.sha256("|".join(s.chunk_id for s in sources).encode()).hexdigest()[:8]
    return f"{direction}-{digest}"


def _clean(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    body = clean_sentence(escape_untrusted(_BULLET.sub("", text)))
    return body[:MAX_CARD_SENTENCE_CHARS]


def validate_sentences(
    raw: Any,
    sources: Sequence[PolicySource],
    req: ProposalRequest | None,
    *,
    limit: int = MAX_CARD_SENTENCES,
    extra_allowed: Sequence[str] = (),
    require_evidence: bool = True,
) -> tuple[list[PolicySentence], list[str]]:
    """LLM 문장 목록 → 검증 통과 문장 + 폐기 사유. 허용 텍스트 = 인용 구간 + 제안자 입력
    (+ extra_allowed: [AI로 다듬기] 때 제안자가 고친 글)."""
    by_id = {s.chunk_id: s for s in sources}
    request_texts = (
        [
            v
            for v in req.model_dump(exclude={"budget", "policy_choice"}).values()
            if isinstance(v, str)
        ]
        if req is not None
        else []
    )
    kept: list[PolicySentence] = []
    dropped: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"text": item, "evidence": []}
        if not isinstance(item, dict):
            dropped.append(DROP_EMPTY)
            continue
        text = _clean(item.get("text"))
        if not text:
            dropped.append(DROP_EMPTY)
            continue
        if has_foreign_script(text):
            dropped.append(DROP_FOREIGN)
            continue
        ev_raw = item.get("evidence") or []
        ev_raw = [ev_raw] if isinstance(ev_raw, str) else ev_raw
        evidence: list[str] = []
        for ev in ev_raw if isinstance(ev_raw, list) else []:
            if not isinstance(ev, str):
                continue
            ev = normalize_evidence_id(ev.strip())
            if ev in by_id and ev not in evidence:
                evidence.append(ev)
        if require_evidence and not evidence:
            dropped.append(DROP_EVIDENCE)
            continue
        cited = [by_id[e].quote for e in evidence] or [s.quote for s in sources]
        allowed = [*cited, *request_texts, *extra_allowed]
        if ungrounded(text, allowed):
            dropped.append(DROP_UNGROUNDED)
            continue
        if unsupported_numbers(text, allowed):
            dropped.append(DROP_NUMBER)
            continue
        if any(_squash(k.text) == _squash(text) for k in kept):
            continue
        kept.append(PolicySentence(text=text, evidence=evidence))
        if len(kept) >= limit:
            break
    return kept, dropped


def build_card(
    direction: PolicyDirection, sources: Sequence[PolicySource], sentences: list[PolicySentence]
) -> PolicyCard | None:
    if not sentences:
        return None
    used = {e for s in sentences for e in s.evidence}
    shown = [s for s in sources if s.chunk_id in used] or list(sources)
    return PolicyCard(
        id=card_id(direction, sources),
        direction=direction,
        direction_label=DIRECTION_LABELS[direction],
        sentences=sentences[:MAX_CARD_SENTENCES],
        sources=shown,
    )


def limit_cards(cards: Iterable[PolicyCard | None]) -> list[PolicyCard]:
    out: list[PolicyCard] = []
    seen: set[str] = set()
    for c in cards:
        if c is None:
            continue
        docs = {s.doc_id for s in c.sources}
        if docs & seen:  # 근거 겹침 금지 (방어 — group_passages 가 이미 막는다)
            continue
        seen |= docs
        out.append(c)
        if len(out) >= MAX_POLICY_CARDS:
            break
    return out


# ── 고르기·합치기·직접 작성 ─────────────────────────────────
def choice_from_card(card: PolicyCard) -> PolicyChoice:
    return PolicyChoice(
        mode="card",
        card_ids=[card.id],
        sentences=list(card.sentences),
        sources=list(card.sources),
    )


def merge_cards(a: PolicyCard, b: PolicyCard) -> PolicyChoice:
    """두 안을 하나로 — 문장은 a 다음 b(같은 문장은 한 번), 출처는 합친다."""
    sentences: list[PolicySentence] = []
    for s in [*a.sentences, *b.sentences]:
        if not any(_squash(x.text) == _squash(s.text) for x in sentences):
            sentences.append(s)
    sources = list(a.sources) + [
        s for s in b.sources if s.chunk_id not in {x.chunk_id for x in a.sources}
    ]
    return PolicyChoice(
        mode="merged",
        card_ids=[a.id, b.id],
        sentences=sentences[:MAX_CHOICE_SENTENCES],
        sources=sources[:8],
    )


def split_text(text: str) -> list[str]:
    """제안자가 직접 쓴 글 → 문장(줄 단위, "○" 떼기)."""
    out: list[str] = []
    for line in re.split(r"\n+", text or ""):
        body = _BULLET.sub("", line).strip()
        if body:
            out.append(body[:MAX_CARD_SENTENCE_CHARS])
    return out[:MAX_CHOICE_SENTENCES]


def edited_choice(base: PolicyChoice | None, text: str, *, manual: bool = False) -> PolicyChoice:
    """직접 수정·직접 작성 → 제안자 글. 고친 문장이 원래 문장과 같으면 원래 근거를 이어받는다."""
    prior = {(_squash(s.text)): s for s in (base.sentences if base else [])}
    sentences = [
        prior.get(_squash(t)) or PolicySentence(text=t, evidence=[]) for t in split_text(text)
    ]
    return PolicyChoice(
        mode="manual" if manual or base is None else "edited",
        card_ids=list(base.card_ids) if base else [],
        sentences=sentences,
        sources=list(base.sources) if base else [],
    )


def none_choice() -> PolicyChoice:
    return PolicyChoice(mode="none")


def basis_text(choice: PolicyChoice) -> str:
    """policy_basis 칸에 넣을 요지 — 문장 + 출처(문서명·연도). 다른 섹션 프롬프트가 정책
    맥락을 본다."""
    if choice.mode == "none" or not choice.sentences:
        return ""
    lines = [s.text for s in choice.sentences]
    refs = []
    for s in choice.sources:
        ref = s.title + (f", {s.year}" if s.year else "")
        if ref and ref not in refs:
            refs.append(ref)
    if refs:
        lines.append("(근거: " + "; ".join(refs) + ")")
    return "\n".join(lines)[:2000]


def apply_policy_choice(req: ProposalRequest, choice: PolicyChoice | None) -> ProposalRequest:
    """고른 안을 요청에 — policy_choice 저장, policy_basis 가 비었으면 요지로 채운다
    (입력은 유지)."""
    if choice is None:
        return req
    update: dict[str, Any] = {"policy_choice": choice}
    if not req.policy_basis.strip():
        text = basis_text(choice)
        if text:
            update["policy_basis"] = text
    return req.model_copy(update=update)


def has_choice_text(req: ProposalRequest) -> bool:
    c = req.policy_choice
    return c is not None and c.mode != "none" and any(s.text.strip() for s in c.sentences)


def needs_policy_basis(req: ProposalRequest) -> bool:
    """2-가-(1) 을 쓸 근거가 없다 (입력도, 고른 안도 없음, 또는 "정책 근거 없음" 선택)."""
    if has_choice_text(req):
        return False
    if req.policy_choice is not None and req.policy_choice.mode == "none":
        return True
    return not req.policy_basis.strip()


# ── 생성 때 원문 대조 (보안 A) ──────────────────────────────
def verify_sources(choice: PolicyChoice, docs: Mapping[str, Document | None]) -> list[Chunk]:
    """고른 안의 구간을 저장소 원문과 대조 — 문서가 있고, 정책 종류이고, 인용이 본문에 그대로 있는
    것만 Chunk 로(스냅샷에 고정). 클라이언트가 보낸 인용·id 는 비신뢰다."""
    out: list[Chunk] = []
    for s in choice.sources:
        doc = docs.get(s.doc_id)
        if doc is None or doc.doc_type not in CARD_DOC_TYPES:
            continue
        if not s.chunk_id.startswith(f"{doc.doc_id}#"):
            continue
        quote = _squash(s.quote.rstrip("…"))
        haystack = _squash(
            " ".join(t for t in (doc.title, doc.abstract or "", doc.body or "") if t)
        )
        if not quote or quote not in haystack:
            continue
        try:
            ordinal = int(s.chunk_id.rsplit("#", 1)[1])
        except ValueError:
            ordinal = 0
        out.append(
            Chunk(
                chunk_id=s.chunk_id,
                doc_id=doc.doc_id,
                ordinal=ordinal,
                heading=s.page,
                text=s.quote[:MAX_QUOTE],
                basis=doc.text_basis,
                visibility=doc.visibility,
            )
        )
    return out


def choice_section(choice: PolicyChoice, allowed_ids: set[str]) -> Section:
    """고른 안 → 2-가-(1) 섹션. 문장은 제안자가 확정한 글(origin proposer_input, AI 다시 쓰기에서
    보존), 근거는 원문 대조를 통과한 구간 id 만."""
    sentences = [
        Sentence(
            text=clean_sentence(s.text),
            evidence=[e for e in s.evidence if e in allowed_ids],
            origin="proposer_input",
        )
        for s in choice.sentences
        if clean_sentence(s.text)
    ]
    return Section(key=POLICY_SECTION, sentences=sentences)
