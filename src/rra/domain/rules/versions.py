"""④ 직접 수정·보완의 순수 규칙 — 문장 편집·섹션 편집·버전 비교·메타 (ADR 0011).

- 문장 단위: 수정(manual → origin=proposer_edit, 원래 근거 유지) · 추가(insert_after →
  proposer_input, 근거 없음) · 삭제 · 순서 변경(order). 버리지 않고 lint 는 알림만 (유스케이스).
- 섹션 전체: 문장 목록(texts) 또는 통문(text → split_sentences)으로 바꾼다. 같은 문장(정리 뒤
  같은 글)은 근거·출처를 이어받고, 새 문장은 proposer_input.
- 비교(diff): 두 버전의 섹션·문장 단위 차이(added·removed·moved). 같은 내용 저장은 새 버전을
  만들지 않는다(same_content).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rra.domain.models import Section, Sentence
from rra.domain.models.draft import SentenceOrigin
from rra.domain.models.review import DraftVersion, sentence_id
from rra.domain.rules.llm_output import clean_sentence

_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=[함임됨음])\.\s*|\n+")
_END = re.compile(r"[.!?。]$")


def split_sentences(text: str) -> list[str]:
    """통문 → 문장 목록. 마침표·개조식 어미(~함./~임.)·줄바꿈에서 나눈다. 빈 조각은 버린다."""
    parts: list[str] = []
    for raw in _SPLIT.split(text or ""):
        piece = clean_sentence(raw or "")
        if not piece:
            continue
        if not _END.search(piece) and re.search(r"[함임됨음]$", piece):
            piece += "."
        parts.append(piece)
    return parts


def _match_key(text: str) -> str:
    return re.sub(r"\s+", " ", clean_sentence(text)).strip().rstrip(".")


def section_from_texts(
    section: Section, texts: Iterable[str], *, new_origin: SentenceOrigin = "proposer_input"
) -> Section:
    """섹션 전체 편집. 같은 문장은 근거·출처를 이어받고(한 번씩), 새 문장은 new_origin·근거 없음."""
    pool: dict[str, list[Sentence]] = {}
    for s in section.sentences:
        pool.setdefault(_match_key(s.text), []).append(s)
    out: list[Sentence] = []
    for raw in texts:
        text = clean_sentence(raw)
        if not text:
            continue
        key = _match_key(text)
        old = pool.get(key)
        if old:
            prev = old.pop(0)
            out.append(prev.model_copy(update={"text": text}))
        else:
            out.append(Sentence(text=text, evidence=[], origin=new_origin))
    return section.model_copy(update={"sentences": out})


def reorder(section: Section, order: list[str]) -> Section:
    """문장 id 목록 순서로 재배열. 빠진 문장은 뒤에 원래 순서로 붙인다. 모르는 id 는 ValueError."""
    ids = [sentence_id(section.key, i) for i in range(len(section.sentences))]
    by_id = dict(zip(ids, section.sentences, strict=True))
    picked: list[Sentence] = []
    for sid in order:
        if sid not in by_id:
            raise ValueError(f"그런 문장이 없습니다: {sid}")
        if by_id[sid] not in picked:
            picked.append(by_id[sid])
    rest = [s for s in section.sentences if s not in picked]
    return section.model_copy(update={"sentences": picked + rest})


def same_content(a: list[Section], b: list[Section]) -> bool:
    """문장 텍스트·순서·선택값이 같으면 같은 내용 (근거·출처 차이는 무시하지 않는다 — 모두 비교)."""
    return [s.model_dump() for s in a] == [s.model_dump() for s in b]


def changed_sections(old: list[Section], new: list[Section]) -> list[str]:
    before = {s.key: s for s in old}
    out: list[str] = []
    for sec in new:
        prev = before.get(sec.key)
        if prev is None or prev.model_dump() != sec.model_dump():
            out.append(sec.key)
    out.extend(k for k in before if k not in {s.key for s in new})
    return out


def diff_versions(old: DraftVersion, new: DraftVersion) -> list[dict]:
    """섹션·문장 단위 차이 — 섹션마다 {section, added[], removed[], changed[]}. 바뀐 섹션만."""
    before = {s.key: s for s in old.sections}
    after = {s.key: s for s in new.sections}
    out: list[dict] = []
    for key in list(dict.fromkeys([*before, *after])):
        a = before.get(key)
        b = after.get(key)
        if a is not None and b is not None and a.model_dump() == b.model_dump():
            continue
        a_texts = [s.text for s in (a.sentences if a else [])]
        b_texts = [s.text for s in (b.sentences if b else [])]
        a_keys = [_match_key(t) for t in a_texts]
        b_keys = [_match_key(t) for t in b_texts]
        removed = [
            {"sentence_id": sentence_id(key, i), "text": t}
            for i, (t, k) in enumerate(zip(a_texts, a_keys, strict=True))
            if k not in b_keys
        ]
        added = [
            {"sentence_id": sentence_id(key, i), "text": t}
            for i, (t, k) in enumerate(zip(b_texts, b_keys, strict=True))
            if k not in a_keys
        ]
        changed: list[dict] = []
        for i, (t, k) in enumerate(zip(b_texts, b_keys, strict=True)):
            if i < len(a_keys) and a_keys[i] != k and k in a_keys:
                changed.append(
                    {"sentence_id": sentence_id(key, i), "from": a_texts[a_keys.index(k)], "to": t}
                )
        choices_changed = (a.choices if a else []) != (b.choices if b else [])
        out.append(
            {
                "section": key,
                "added": added,
                "removed": removed,
                "moved": changed,
                "choices_changed": choices_changed,
                "sentences": [len(a_texts), len(b_texts)],
            }
        )
    return out


def count_changed_sentences(old: list[Section], new: list[Section]) -> int:
    """최종 검토 이후 바뀐 문장 수(stale) — 추가·삭제·수정 합."""
    before = {s.key: [_match_key(x.text) for x in s.sentences] for s in old}
    total = 0
    for sec in new:
        prev = before.get(sec.key, [])
        now = [_match_key(x.text) for x in sec.sentences]
        total += sum(1 for k in now if k not in prev) + sum(1 for k in prev if k not in now)
    return total
