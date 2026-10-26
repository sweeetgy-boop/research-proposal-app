"""차별화 과제 추천의 순수 규칙 — LLM 출력 검증·중복 제거·상한·입력 반영 (ADR 0012).

검증(validate_recommendation): compared_with·evidence 는 precheck 알림 + 이번 검색 근거
(하한 통과 청크)의 doc_id 안에서만 — 검색으로 찾은 논문·보고서도 "비교한 기존 과제" 가
될 수 있다. 본문(가제·요약·차별점·이유·이어받을
점·위험)은 제안 입력·유사과제 문서·근거 구간에 있는 수치(numbers)와 고유명(grounding)만 쓰고
한자·가나가 없어야 한다. 하나라도 어긋나면 그 추천은 폐기 사유와 함께 버린다 (보안 A: LLM 출력은
비신뢰 → 구획 태그 무력화·길이 상한).

거의 같은 추천(near_duplicate — 가제+요약+차별점의 토큰 자카드 ≥ DUPLICATE_RATIO)은 하나만, 최대
MAX_RECOMMENDATIONS 개. 자기 중복 검사(추천 글로 precheck → blocking)는 유스케이스가 돌리고 사유만
여기 상수.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from rra.domain.models import ProposalRequest
from rra.domain.models.recommendation import (
    MAX_REASONS,
    MAX_REC_CHARS,
    MAX_RECOMMENDATIONS,
    MAX_TITLE_CHARS,
    ProjectRecommendation,
    RecommendationPreview,
)
from rra.domain.rules.foreign_script import has_foreign_script
from rra.domain.rules.grounding import ungrounded
from rra.domain.rules.keywords import tokens
from rra.domain.rules.llm_output import clean_sentence
from rra.domain.rules.numbers import unsupported_numbers
from rra.domain.rules.trust import escape_untrusted, normalize_evidence_id

DUPLICATE_RATIO = 0.8
DISCARD_EMPTY = "empty_fields"
DISCARD_COMPARED = "compared_with_out_of_range"
DISCARD_EVIDENCE = "evidence_out_of_range"
DISCARD_NUMBER = "unsupported_number"
DISCARD_UNGROUNDED = "ungrounded"
DISCARD_FOREIGN = "foreign_script"
DISCARD_DUPLICATE = "duplicate"
DISCARD_SELF_OVERLAP = "self_overlap"  # 추천 글로 precheck 를 다시 돌려 차단 → 제외
DISCARD_OVER_LIMIT = "over_limit"
EXCLUDED_SUFFIX = "검증에서 제외됨 {n}건"
GOAL_SUPPLEMENT = "(추천 과제 보완) "


def _text(value: Any, limit: int = MAX_REC_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return clean_sentence(escape_untrusted(value))[:limit]


def _ids(value: Any, allowed: Iterable[str]) -> tuple[list[str], bool]:
    """id 목록 정규화 → (목록, 전부 허용 범위 안인가). 문자열 하나도 받는다."""
    if isinstance(value, str):
        value = [value]
    out = [normalize_evidence_id(str(v)) for v in (value or []) if isinstance(v, str)]
    out = list(dict.fromkeys(i for i in out if i))
    allowed_set = set(allowed)
    return out, all(i in allowed_set for i in out)


def validate_recommendation(
    raw: Mapping[str, Any],
    *,
    alert_doc_ids: Iterable[str],
    evidence_doc_ids: Iterable[str],
    allowed_texts: Iterable[str],
) -> tuple[ProjectRecommendation | None, str | None]:
    """LLM 추천 하나 → (검증된 추천, None) 또는 (None, 폐기 사유)."""
    title = _text(raw.get("title"), MAX_TITLE_CHARS)
    summary = _text(raw.get("summary"))
    differentiation = _text(raw.get("differentiation"))
    reasons_raw = raw.get("reasons")
    if isinstance(reasons_raw, str):
        reasons_raw = [reasons_raw]
    reasons = [t for t in (_text(r) for r in (reasons_raw or []) if isinstance(r, str)) if t]
    reasons = list(dict.fromkeys(reasons))[:MAX_REASONS]
    if not (title and summary and differentiation and reasons):
        return None, DISCARD_EMPTY
    build_on = _text(raw.get("build_on"))
    risks = _text(raw.get("risks"))
    alert_ids = list(alert_doc_ids)
    known = [*alert_ids, *evidence_doc_ids]
    compared, ok = _ids(raw.get("compared_with"), known)
    if not ok:
        return None, DISCARD_COMPARED
    evidence, ok = _ids(raw.get("evidence"), known)
    if not ok:
        return None, DISCARD_EVIDENCE
    texts = [title, summary, differentiation, *reasons, build_on, risks]
    if any(has_foreign_script(t) for t in texts):
        return None, DISCARD_FOREIGN
    allowed = [*allowed_texts, *alert_ids, *evidence_doc_ids]  # id 표기(own:1·W1)는 수치가 아니다
    if any(unsupported_numbers(t, allowed) for t in texts):
        return None, DISCARD_NUMBER
    if any(ungrounded(t, allowed) for t in texts):
        return None, DISCARD_UNGROUNDED
    return (
        ProjectRecommendation(
            title=title,
            summary=summary,
            differentiation=differentiation,
            reasons=reasons,
            build_on=build_on,
            risks=risks,
            compared_with=compared,
            evidence=evidence,
        ),
        None,
    )


def _bag(rec: ProjectRecommendation) -> set[str]:
    return set(tokens(rec.self_check_text().lower()))


def near_duplicate(a: ProjectRecommendation, b: ProjectRecommendation) -> bool:
    """가제·요약·차별점 토큰의 자카드 유사도가 DUPLICATE_RATIO 이상이면 같은 추천으로 본다."""
    x, y = _bag(a), _bag(b)
    if not x or not y:
        return a.title == b.title
    return len(x & y) / len(x | y) >= DUPLICATE_RATIO


def select_recommendations(
    items: Iterable[ProjectRecommendation], limit: int = MAX_RECOMMENDATIONS
) -> tuple[list[ProjectRecommendation], list[dict[str, str]]]:
    """거의 같은 추천은 앞의 것만, 상한을 넘는 것은 폐기(사유 기록). 순서 유지."""
    kept: list[ProjectRecommendation] = []
    discarded: list[dict[str, str]] = []
    for rec in items:
        if any(near_duplicate(rec, k) for k in kept):
            discarded.append({"title": rec.title[:80], "reason": DISCARD_DUPLICATE})
        elif len(kept) >= limit:
            discarded.append({"title": rec.title[:80], "reason": DISCARD_OVER_LIMIT})
        else:
            kept.append(rec)
    return kept, discarded


def self_overlaps(original: Iterable[Any], probe: Iterable[Any], margin: float = 0.0) -> bool:
    """추천 글만으로 다시 돌린 precheck(probe)가 원래 아이디어보다 기존 과제에 가깝거나 같으면
    자기 중복.

    multilingual-e5 는 같은 분야의 한국어 글을 모두 own 임계치(0.80) 위로 올리므로 "차단이면
    제외" 를 절대값으로 쓰면 주제 안의 추천이 전부 떨어진다(2026-10-27 골든셋 01·02 실측). 그래서
    상대 기준: probe 의 차단 알림마다 (1) 원래 아이디어가 차단되지 않던 문서면 새 중복 → 자기 중복,
    (2) 같은 문서면 유사도가 원래보다 낮아져야 통과(margin 만큼 더 낮아야 하면 margin > 0). 차단
    알림이 없으면 통과.
    """
    base = {a.doc_id: a.similarity for a in original if a.blocking}
    for a in probe:
        if not a.blocking:
            continue
        if a.doc_id not in base or a.similarity + margin >= base[a.doc_id]:
            return True
    return False


def no_recommendation_text(model_reason: str | None, excluded: int) -> str:
    """추천 0건일 때 보여 줄 사유 — 모델 사유 + 검증 제외 건수."""
    reason = _text(model_reason) or "추천할 만한 차별화 방향이 없음"
    if excluded:
        return f"{reason} · {EXCLUDED_SUFFIX.format(n=excluded)}"
    return reason


def apply_recommendation(
    req: ProposalRequest, rec: ProjectRecommendation, index: int
) -> tuple[ProposalRequest, RecommendationPreview]:
    """추천 하나를 제안자 입력에 채운 '수정 전 미리보기'.

    가제 ← 추천 가제, 목표 ← 원래 목표 + 보완 문구(요약), 차별화 방향 ← 추천 차별점.
    사용자가 이 값을 고쳐 확정한 입력으로 초안을 만든다. 다른 칸은 손대지 않는다.
    """
    goal = req.goal.rstrip()
    if rec.summary and rec.summary not in goal:
        goal = f"{goal}\n{GOAL_SUPPLEMENT}{rec.summary}"
    updates = {"title_hint": rec.title, "goal": goal, "differentiation": rec.differentiation}
    changed = [k for k, v in updates.items() if getattr(req, k) != v]
    new_req = req.model_copy(update=updates)
    preview = RecommendationPreview(
        index=index,
        title_hint=new_req.title_hint,
        goal=new_req.goal,
        differentiation=new_req.differentiation,
        changed=changed,
    )
    return new_req, preview
