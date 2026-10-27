"""U1 근거 원문 바로보기·적합성·제안자 판단의 순수 규칙.

- basis 라벨: 원문 / 공개 요약 / 초록 / 제목 / 이미지 판독. summary·title·image_vision 은
  "세부 확인 필요"(needs_check).
- 제안자 판단(approve·replace·exclude)은 문장×근거 id 단위. replace 는 이번 run 검색 집합 안의 id
  로만 바꾸고, exclude 는 문장의 근거를 지우지 않고 판단만 남긴다 (근거 필수 섹션의 모든 근거가
  제외되면 경고 evidence_all_excluded).
- Argon 판정 불일치(support=불일치)는 경고 evidence_mismatch 로 문장에 붙는다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from rra.domain.models import Section, Sentence
from rra.domain.models.review import (
    SUPPORT_MISMATCH,
    SUPPORT_VALUES,
    EvidenceDecision,
    parse_sentence_id,
    sentence_id,
)
from rra.domain.rules.lint import LintProblem

BASIS_LABELS: dict[str, str] = {
    "full_text": "원문",
    "summary": "공개 요약",
    "abstract": "초록",
    "title": "제목",
    "image_vision": "이미지 판독",
}
NEEDS_CHECK_BASES: frozenset[str] = frozenset({"summary", "title", "image_vision"})
NEEDS_CHECK_LABEL = "세부 확인 필요"
EVIDENCE_MISMATCH = "evidence_mismatch"  # Argon 판정: 근거가 문장을 뒷받침하지 않음 (경고)
EVIDENCE_ALL_EXCLUDED = "evidence_all_excluded"  # 근거 필수 섹션 문장의 근거가 전부 제외됨 (경고)
MAX_EXCERPT_CHARS = 1200


class DecisionRejected(ValueError):
    """판단 요청이 규칙(문장 id·근거 id·교체 id 범위)에 맞지 않는다."""


def basis_label(basis: str | None) -> str:
    return BASIS_LABELS.get(basis or "", basis or "미상")


def needs_check(basis: str | None) -> bool:
    return (basis or "") in NEEDS_CHECK_BASES


def doc_of(evidence_id: str) -> str:
    return evidence_id.split("#", 1)[0]


def parse_support(raw: object, sent_ids: set[str]) -> dict[str, str]:
    """LLM 의 support 배열 → {문장 id: 지지|부분|불일치}. 보낸 문장·허용 값만, 첫 값만."""
    out: dict[str, str] = {}
    if not isinstance(raw, list):
        return out
    for item in raw[:1000]:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("sentence_id", ""))
        value = str(item.get("support", "")).strip()
        if sid in sent_ids and value in SUPPORT_VALUES and sid not in out:
            out[sid] = value
    return out


def support_problems(sections: Iterable[Section], support: Mapping[str, str]) -> list[LintProblem]:
    """support=불일치 문장 → 경고 (문장은 그대로)."""
    by_key = {s.key: s for s in sections}
    out: list[LintProblem] = []
    for sid, value in support.items():
        if value != SUPPORT_MISMATCH:
            continue
        parsed = parse_sentence_id(sid)
        if parsed is None:
            continue
        key, idx = parsed
        sec = by_key.get(key)
        if sec is None or idx >= len(sec.sentences):
            continue
        out.append(
            LintProblem(
                section=key,
                code=EVIDENCE_MISMATCH,
                message="검토 판정: 근거가 문장을 뒷받침하지 않음 — "
                + sec.sentences[idx].text[:30],
                severity="warning",
                sentence=idx,
            )
        )
    return out


def apply_decisions(
    sections: list[Section],
    previous: Iterable[EvidenceDecision],
    decisions: Iterable[EvidenceDecision],
    allowed_ids: set[str],
) -> tuple[list[Section], list[EvidenceDecision]]:
    """판단을 문장에 적용한 새 섹션 목록과 누적 판단 목록.

    - approve/exclude: 문장 근거는 그대로, 판단만 기록 (같은 문장×근거의 이전 판단을 덮는다).
    - replace: replacement 가 검색 집합(allowed_ids) 안에 있어야 하며, 문장의 그 근거 id 를 새 id
      로 바꾼다. 누적 판단은 새 id 기준 approve 로 남긴다 (이력은 버전 파일에 있다).
    문장 id·근거 id 가 현재 문장에 없으면 DecisionRejected.
    """
    by_key = {s.key: s for s in sections}
    merged: dict[tuple[str, str], EvidenceDecision] = {d.key: d for d in previous}
    for d in decisions:
        parsed = parse_sentence_id(d.sentence_id)
        if parsed is None:
            raise DecisionRejected(f"문장 id 형식이 올바르지 않습니다: {d.sentence_id}")
        key, idx = parsed
        sec = by_key.get(key)
        if sec is None or idx >= len(sec.sentences):
            raise DecisionRejected(f"그런 문장이 없습니다: {d.sentence_id}")
        sentence = sec.sentences[idx]
        if d.evidence_id not in sentence.evidence:
            raise DecisionRejected(f"{d.sentence_id}: 그 문장의 근거가 아닙니다: {d.evidence_id}")
        if d.action == "replace":
            new_id = (d.replacement or "").strip()
            if not new_id or (new_id not in allowed_ids and doc_of(new_id) not in allowed_ids):
                raise DecisionRejected(
                    f"{d.sentence_id}: 교체 근거는 이번 run 검색 집합 안의 id 여야 합니다."
                )
            evidence = [new_id if e == d.evidence_id else e for e in sentence.evidence]
            evidence = list(dict.fromkeys(evidence))
            sentences = list(sec.sentences)
            sentences[idx] = Sentence(text=sentence.text, evidence=evidence, origin=sentence.origin)
            by_key[key] = sec.model_copy(update={"sentences": sentences})
            merged.pop((d.sentence_id, d.evidence_id), None)
            merged[(d.sentence_id, new_id)] = EvidenceDecision(
                sentence_id=d.sentence_id, evidence_id=new_id, action="approve"
            )
        else:
            merged[d.key] = d.model_copy(update={"replacement": None})
    return [by_key[s.key] for s in sections], list(merged.values())


def decisions_for_sections(
    sections: Iterable[Section], decisions: Iterable[EvidenceDecision]
) -> list[EvidenceDecision]:
    """현재 문장에 아직 들어맞는 판단만 (편집으로 문장·근거가 바뀌면 그 판단은 떨어진다)."""
    by_key = {s.key: s for s in sections}
    out: list[EvidenceDecision] = []
    for d in decisions:
        parsed = parse_sentence_id(d.sentence_id)
        if parsed is None:
            continue
        key, idx = parsed
        sec = by_key.get(key)
        if sec is None or idx >= len(sec.sentences):
            continue
        if d.evidence_id in sec.sentences[idx].evidence:
            out.append(d)
    return out


def exclusion_problems(
    sections: Iterable[Section],
    decisions: Iterable[EvidenceDecision],
    evidence_required: Iterable[str],
) -> list[LintProblem]:
    """근거 필수 섹션에서 문장의 근거가 전부 exclude 되었으면 경고."""
    required = set(evidence_required)
    excluded: set[tuple[str, str]] = {d.key for d in decisions if d.action == "exclude"}
    out: list[LintProblem] = []
    for sec in sections:
        if sec.key not in required:
            continue
        for i, s in enumerate(sec.sentences):
            if not s.evidence or s.origin == "app":
                continue
            sid = sentence_id(sec.key, i)
            if all((sid, e) in excluded for e in s.evidence):
                out.append(
                    LintProblem(
                        section=sec.key,
                        code=EVIDENCE_ALL_EXCLUDED,
                        message="근거가 전부 제외됨 — 다른 근거를 고르거나 문장을 고칠 것: "
                        + s.text[:30],
                        severity="warning",
                        sentence=i,
                    )
                )
    return out


def evidence_counts(
    sections: Iterable[Section], decisions: Iterable[EvidenceDecision]
) -> dict[str, int]:
    """판단 비율 집계용 — approve/replace/exclude 수와 판단 대상 근거 참조 수.
    replace 는 적용 뒤 approve 로 남으므로 여기서는 버전 간 누적이 아니라 현재 상태만 센다."""
    total = sum(len(s.evidence) for sec in sections for s in sec.sentences if s.origin != "app")
    counts = {"approve": 0, "replace": 0, "exclude": 0}
    for d in decisions:
        if d.action in counts:
            counts[d.action] += 1
    return {**counts, "total": total}


def excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"
