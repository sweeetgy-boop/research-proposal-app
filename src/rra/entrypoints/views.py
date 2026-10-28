"""진입점 공용 직렬화. RunManager.DraftView → 출력용 dict (CLI·MCP 가 같은 모양을 쓴다).

현행 근거 규칙: 근거 필수 섹션 밖에서는 제안자 입력만으로 쓴 문장이 허용된다.
그런 문장은 evidence 가 비어 있고 source="proposer_input" 으로 구분해 보여 준다.
앱이 규칙으로 만든 확정 문장(유사과제 없음 등)은 source="app".

선택형 섹션(과제유형·활용계획·전략)은 choices 에 LLM 제안(proposed)과 사용자 확정(confirmed)을
따로 싣는다. 확정 전이면 confirmed 는 null.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Any

from rra.domain.models import STRATEGY_DRAFT_LABEL
from rra.domain.models.review import ORIGIN_LABEL
from rra.domain.rules.card_overlap import DIFFERENCE_LABELS
from rra.domain.rules.doc_category import CATEGORY_LABELS, RESEARCH_SERVICE
from rra.domain.rules.doc_refs import UNTITLED, source_name, source_of
from rra.domain.rules.draft_failures import reason_label
from rra.domain.rules.local_review import review_view
from rra.domain.rules.overlap import SOURCE_LABELS, STATUS_LABELS, tier_label
from rra.domain.rules.precheck_levels import level_view
from rra.domain.rules.precheck_view import (
    JUDGED_BY_LABELS,
    differentiation_skip_label,
    extraction_label,
    judgment_message,
    recommendation_skip_label,
)
from rra.domain.rules.problem_labels import (
    problem_label,
    review_skip_label,
    severity_label,
    step_label,
)
from rra.domain.rules.recommendation import discard_label
from rra.domain.rules.same_judgment import VERDICT_LABELS
from rra.domain.rules.series import display_title
from rra.domain.rules.writer import local_check_view, local_sections, writers_view
from rra.entrypoints.views_editai import rewrite_reason_label
from rra.entrypoints.views_refs import citation_ref, no_ids, refs_for, titles_from
from rra.entrypoints.views_series import series_payload


def _same(text: str) -> str:
    return text


def _source(sent: Any) -> str:
    if sent.origin == "app":
        return "app"
    return "retrieved" if sent.evidence else "proposer_input"


def _choices(sec: Any, view: Any) -> dict[str, Any] | None:
    options = view.choice_options.get(sec.key)
    if options is None:
        return None
    confirmed = view.confirmation.choices.get(sec.key) if view.confirmation else None

    def labelled(ids: list[str]) -> list[dict[str, str]]:
        return [{"id": i, "label": options.get(i, i)} for i in ids]

    return {
        "proposed": labelled(sec.choices),
        "confirmed": labelled(confirmed) if confirmed is not None else None,
        "options": labelled(list(options)),
    }


def draft_payload(view: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """clean: 비신뢰 텍스트(초안 문장·문서 제목·lint 메시지)에 적용할 정리 함수."""
    state = view.state
    live_ids = set(getattr(state, "live_doc_ids", None) or [])
    titles = titles_from(view.citations)
    return {
        "run_id": state.run_id,
        "status": state.status,
        "template": state.template,
        "legacy": view.legacy,
        "progress": list(state.progress),
        "steps": [
            {
                "name": s.name,
                "status": s.status,
                "error": s.error,
                "sentences": s.sentences,
                "dropped": s.dropped,
                "parse": s.parse,
                "raw_chars": s.raw_chars,
                "retries": s.retries,
            }
            for s in state.steps
        ],
        "sections": [
            {
                "key": sec.key,
                "sentences": [
                    {
                        "sentence_id": f"s:{sec.key}:{i}",  # 편집·검토·근거 API 가 쓰는 id
                        "text": clean(sent.text),
                        "evidence": sent.evidence,
                        "source": _source(sent),
                        "origin": sent.origin,  # 로컬 작성 / Argon 보완 / Argon 추가 / 제안자 수정
                    }
                    for i, sent in enumerate(sec.sentences)
                ],
                "choices": _choices(sec, view),
            }
            for sec in view.sections
        ],
        # 인용 문서 — 화면은 id 대신 title·source_label(한국어)·url(공개 문서만)을 보인다 (ADR
        # 0040).
        # live: [4] 실시간 검색에서 가져온 근거
        "citations": [
            citation_ref(c, clean=clean, live=c.doc_id in live_ids) for c in view.citations
        ],
        "problems": [
            {
                "section": p["section"],
                "code": p["code"],
                "label": problem_label(p["code"]),  # 화면은 코드 대신 이것 (항목 16)
                "severity": p.get("severity", "error"),
                "severity_label": severity_label(p.get("severity", "error")),
                "message": no_ids(clean(p["message"]), titles),
                "sentence": p.get("sentence"),
            }
            for p in state.problems
        ],
        # 검토·버전 요약 (의견 본문은 review_payload 로)
        "version": getattr(view, "version", 1),
        "versions": list(getattr(view, "versions", []) or []),
        "review": review_summary(state, getattr(view, "review", None)),
        "flow": flow_summary(state, getattr(view, "has_working", False)),
        # 빈 초안 금지(ADR 0027): 로컬 작성이 실패해 빈칸으로 둔 섹션 — 화면은 "다시 생성" 버튼
        "failed_sections": failed_sections_payload(state),
        # 대체 작성(ADR 0027): 외부 LLM 이 쓴 섹션 키 — 화면은 "대체 작성" 배지만
        "fallback_sections": fallback_sections_payload(state),
        # [3] Argon 먼저 작성(ADR 0032): 섹션별 작성자 — 화면은 local_sections 에 "로컬 작성" 배지
        "writers": writers_payload(state),
        "local_sections": local_sections_payload(state),
        "local_check": local_check_payload(state, view.sections),
        # [G] 그림 카드 — 보고 있는 버전의 그림 목록
        "figures": figures_payload(getattr(view, "figures", []) or [], state.run_id, clean=clean),
        # 전략체계 목록의 출처 — draft 면 2-가-(3) 선택지가 확인 전 초안이라는 뜻
        "strategy_source": getattr(view, "strategy_status", "confirmed"),
        "strategy_label": STRATEGY_DRAFT_LABEL
        if getattr(view, "strategy_status", "confirmed") == "draft"
        else None,
    }


RESEARCH_SERVICE_LABEL = CATEGORY_LABELS[RESEARCH_SERVICE]
RENDERER_LABEL = {"nano_banana": "Nano Banana Pro", "baseline": "기본 그림"}
FIGURE_NOTICE = "AI 가 그린 그림입니다. 숫자와 글자를 원문과 확인하세요"
# [23] 그림 오류 코드 → 화면 문구 (코드는 내보내지 않는다)
FIGURE_ERROR_LABEL = {
    "budget": "오늘 그림 호출 한도에 이르러 기본 그림으로 넣었습니다.",
    "no_image_llm": "그림 AI 를 쓸 수 없어 기본 그림으로 넣었습니다.",
}
FIGURE_ERROR_DEFAULT = (
    "그림 AI 호출이 실패해 기본 그림으로 넣었습니다. [다시 만들기]로 다시 시도할 수 있습니다."
)


def figure_error_label(code: str | None) -> str | None:
    if not code:
        return None
    return FIGURE_ERROR_LABEL.get(code, FIGURE_ERROR_DEFAULT)


def figure_fit_view(fit: Any) -> dict[str, Any] | None:
    """[23] 본문 폭 맞춤 — 카드가 그림을 이 비율(aspect_css)로 보이고, 한 줄 설명(note)을 붙인다."""
    if fit is None:
        return None
    ratio = str(fit.ratio or "16:9")
    a, _, b = ratio.partition(":")
    parts = [f"본문 폭 {fit.width_mm:g}mm × 높이 {fit.height_mm:g}mm"]
    if fit.min_text_pt is not None:
        parts.append(f"가장 작은 글자 약 {fit.min_text_pt:g}pt")
    note = " · ".join(parts)
    if not fit.fits:
        note += " — 높이가 쪽의 1/3 을 넘습니다"
    elif not fit.text_ok:
        note += " — 글자가 작을 수 있습니다"
    if fit.shortened:
        note += f" (글자 크기를 맞추려고 {fit.shortened}곳을 줄였습니다)"
    return {
        "ratio": ratio,
        "aspect_css": f"{a} / {b}" if a and b else "16 / 9",
        "width_mm": fit.width_mm,
        "height_mm": fit.height_mm,
        "fits": fit.fits,
        "min_text_pt": fit.min_text_pt,
        "text_ok": fit.text_ok,
        "shortened": fit.shortened,
        "note": note,
    }


def figures_payload(
    figures: list[Any], run_id: str, *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """[G] 그림 목록 — 명세 글자(editable_texts)·대체 텍스트·배지·그림 URL. 바이트는 별도 경로."""
    from rra.domain.models.figure import KIND_LABEL, display_name
    from rra.domain.rules.figures import editable_texts

    out = []
    for f in figures:
        fid = f.id
        tech = _technique_view(f, clean)
        out.append(
            {
                "id": fid,
                "kind": f.kind,
                "label": tech["technique_label"] if tech else KIND_LABEL.get(f.kind, f.kind),
                # [23] 화면·버전 목록 이름 (한국어, 영문·코드 없음) — "분석 기법 그림 – SWOT 분석"
                "display_name": display_name(f.kind, tech["technique_label"] if tech else None),
                "section": f.section,
                "caption": clean(f.caption),
                "alt": clean(f.alt),
                "renderer": f.renderer,
                "renderer_label": RENDERER_LABEL.get(f.renderer, f.renderer),
                "model": f.model,
                "calls": f.calls,
                "included": f.included,
                "confirmed": f.confirmed,
                "source_caption": clean(f.source_caption),
                "error": f.error,
                "error_label": figure_error_label(f.error),
                "fit": figure_fit_view(getattr(f, "fit", None)),
                "image_url": f"/v1/runs/{run_id}/figures/{fid}/image",
                "baseline_url": f"/v1/runs/{run_id}/figures/{fid}/image?variant=baseline",
                "texts": [
                    {"path": r["path"], "label": r["label"], "value": clean(r["value"])}
                    for r in editable_texts(f.spec)
                ],
                "edit_requests": len(f.edit_requests),
                "spec_model": getattr(f, "spec_model", None),
                "last_change": _last_change(getattr(f, "last_change", None), clean),
                "updated_at": f.updated_at,
                "notice": FIGURE_NOTICE,
                # [11] 분석 기법 — 없으면 None·빈 목록
                "technique": tech["technique"] if tech else None,
                "family_label": tech["family_label"] if tech else None,
                "prelim_note": tech["note"] if tech else None,
                "provenance": tech["provenance"] if tech else [],
                "recommendation": _recommendation_view(getattr(f, "recommendation", None), clean),
            }
        )
    return out


TECHNIQUE_LABELS: dict[str, str] = {}  # key → 이름 (build_api 가 목록으로 채운다)
RECOMMENDATION_STATUS_LABEL = {
    "pending": "결정 전",
    "accepted": "넣기 확정",
    "dismissed": "필요 없음",
}
TECHNIQUE_OUTCOME_LABEL = {
    "recommended": "추천함",
    "none": "해당 없음",
    "failed": "호출 실패",
    "filtered": "규칙에 걸러짐",
    "off": "건너뜀",
}


def _technique_view(f: Any, clean: Callable[[str], str]) -> dict[str, Any] | None:
    """[11] 기법 그림 — 이름·종류·안내문·항목 출처(문장·입력·근거, 내부 id 대신 사람이 읽는 말)."""
    if getattr(f, "kind", None) != "technique":
        return None
    from rra.domain.models.figure import FAMILY_LABEL
    from rra.domain.rules.techniques import provenance

    spec = f.spec
    family = _TECHNIQUE_FAMILY.get(spec.technique, "")
    rows = []
    for r in provenance(spec):
        src = r["source"]
        parts = src.split(":")
        kind = (
            "sentence"
            if src.startswith("s:")
            else ("input" if src.startswith("input:") else "evidence")
        )
        rows.append(
            {
                "group": clean(r["group"]),
                "text": clean(r["text"]),
                "rating": r["rating"],
                "amount": clean(r["amount"]),
                "source_kind": kind,
                "section": parts[1] if kind == "sentence" and len(parts) == 3 else None,
                "sentence_no": int(parts[2]) + 1
                if kind == "sentence" and len(parts) == 3 and parts[2].isdigit()
                else None,
                "source_label": r["source_label"],
            }
        )
    return {
        "technique": spec.technique,
        "technique_label": TECHNIQUE_LABELS.get(spec.technique) or spec.title,
        "family_label": FAMILY_LABEL.get(family, "연구 절차") if family else None,
        "note": spec.note,
        "provenance": rows,
    }


_TECHNIQUE_FAMILY: dict[str, str] = {}  # key → family (build_api 가 채운다)


def register_techniques(rows: list[dict[str, Any]]) -> None:
    """기법 목록(이름·종류)을 화면 표시용으로 등록 — 앱 시작 때 한 번."""
    for r in rows:
        TECHNIQUE_LABELS[str(r["key"])] = str(r["label"])
        _TECHNIQUE_FAMILY[str(r["key"])] = str(r["family"])


def _recommendation_view(rec: Any, clean: Callable[[str], str]) -> dict[str, Any] | None:
    """[11] 추천 배지 — {technique, technique_label, reason, status, status_label, swapped_from,
    swapped_from_label, model}. reason 은 LLM 출력(비신뢰)."""
    if rec is None:
        return None
    return {
        "technique": rec.technique,
        "technique_label": TECHNIQUE_LABELS.get(rec.technique, rec.technique),
        "reason": clean(rec.reason),
        "status": rec.status,
        "status_label": RECOMMENDATION_STATUS_LABEL.get(rec.status, rec.status),
        "swapped_from": rec.swapped_from,
        "swapped_from_label": TECHNIQUE_LABELS.get(rec.swapped_from or "", rec.swapped_from)
        if rec.swapped_from
        else None,
        "model": rec.model,
    }


def technique_outcome_payload(
    outcome: dict[str, Any] | None, *, clean: Callable[[str], str] = _same
) -> dict[str, Any] | None:
    """[11] 마지막 기법 추천 결과 — 빈 결과도 사유(해당 없음·호출 실패·규칙에 걸러짐) + 다시 시도.
    reason 원문(코드)은 화면에 보이지 않고, 해당 없음의 모델 사유만 message 에 붙는다."""
    if not outcome:
        return None
    status = str(outcome.get("status") or "none")
    picks = [str(k) for k in outcome.get("picks") or []]
    reason = str(outcome.get("reason") or "")
    if status == "recommended":
        message = (
            f"분석 기법 {len(picks)}개를 추천했습니다 — 카드에서 [넣기 확정] 또는 [필요 없음]을 "
            "고르십시오."
        )
    elif status == "none":
        message = "해당 없음 — " + (
            clean(reason) if reason else "이 제안 내용으로 의미 있는 분석이 나오는 기법이 없습니다."
        )
    elif status == "failed":
        message = (
            "호출 실패 — 분석 기법을 고르는 모델이 답하지 않았습니다. [다시 시도]를 누르십시오."
        )
    elif status == "filtered":
        message = (
            "규칙에 걸러짐 — 추천한 기법의 분석이 출처·형식 검사를 통과하지 못했습니다. "
            "[다시 시도]하거나 [다른 그림 추가]에서 기법을 고르십시오."
        )
    else:
        message = "기본 그림으로 자리가 차서 분석 기법 추천을 건너뛰었습니다."
    return {
        "status": status,
        "status_label": TECHNIQUE_OUTCOME_LABEL.get(status, status),
        "message": message,
        "picks": [{"key": k, "label": TECHNIQUE_LABELS.get(k, k)} for k in picks],
        "dropped": [
            {"key": str(k), "label": TECHNIQUE_LABELS.get(str(k), str(k))}
            for k in outcome.get("dropped") or []
            if str(k) in TECHNIQUE_LABELS
        ],
        "model": outcome.get("model"),
        "at": outcome.get("at"),
        "can_retry": True,
    }


def _last_change(change: Any, clean: Callable[[str], str]) -> dict[str, Any] | None:
    """[2] 카드 "바뀐 내용" — {kind: content|style, summary, style, model, at}. 없으면 None."""
    if change is None:
        return None
    return {
        "kind": change.kind,
        "summary": [clean(x) for x in change.summary],
        "style": clean(change.style),
        "model": change.model,
        "at": change.at,
    }


def failed_sections_payload(state: Any) -> list[dict[str, str]]:
    """RunState.failed_sections → [{key, reason, label}] (사유 설명은 앱 문구, 원문 없음)."""
    return [
        {"key": f.key, "reason": f.reason, "label": reason_label(f.reason)}
        for f in getattr(state, "failed_sections", None) or []
    ]


def fallback_sections_payload(state: Any) -> list[dict[str, str]]:
    """RunState.fallback_sections → [{key, provider, model, reason}] (doc_id 는 manifest 에만)."""
    return [
        {
            "key": str(x.get("key", "")),
            "provider": str(x.get("provider", "")),
            "model": str(x.get("model", "")),
            "reason": str(x.get("reason", "")),
        }
        for x in getattr(state, "fallback_sections", None) or []
    ]


def writers_payload(state: Any) -> dict[str, dict[str, Any]]:
    """RunState.writers → {섹션: {provider, model, local_fallback, reason}}
    (doc_id 는 manifest 에만)."""
    return writers_view(getattr(state, "writers", None) or {})


def local_sections_payload(state: Any) -> list[str]:
    """로컬 모델이 대신 쓴 섹션 키 (Argon 실패) — 섹션 순서대로."""
    return local_sections(getattr(state, "writers", None) or {}, state.section_keys)


def local_check_payload(state: Any, sections: Any = None) -> dict[str, Any] | None:
    """local_check 요약 {enabled, mismatches, skipped_sections}. 돌지 않았으면 None. sections(보는
    버전의 본문)를 주면 L2 문장별 판정·Argon 제안·미결정 수도 싣는다 (ADR 0040)."""
    lc = getattr(state, "local_check", None)
    if sections is None:
        return local_check_view(lc)
    return review_view(lc, list(sections))


def flow_summary(state: Any, has_working: bool = False) -> dict[str, Any]:
    """전체 흐름 ③~⑥ 의 현재 위치 — 화면 stepper·배너용."""
    return {
        "status": state.status,
        "draft_review_skipped": getattr(state, "draft_review_skipped", None),
        "draft_review_skipped_label": review_skip_label(
            getattr(state, "draft_review_skipped", None)
        ),
        "final_reviews": getattr(state, "final_reviews", 0),
        "final_reviewed_version": getattr(state, "final_reviewed_version", None),
        "stale_edits": getattr(state, "stale_edits", 0),
        "stale": bool(getattr(state, "stale", False)),
        "has_working": has_working,
    }


def review_summary(state: Any, latest: Any) -> dict[str, Any]:
    return {
        "rounds": state.review_rounds,
        "skipped": state.review_skipped,
        "error": state.review_error,
        "model": state.review_model,
        "latest_round": latest.round if latest else None,
        "latest_kind": getattr(latest, "kind", None) if latest else None,
        "latest_status": latest.status if latest else None,
        "open_comments": len(latest.open_comments) if latest else 0,
        "finalized_at": state.finalized_at,
    }


def review_payload(
    review: Any,
    *,
    clean: Callable[[str], str] = _same,
    citations: Collection[Any] = (),
    section_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """ReviewRound → dict. 의견·수정안은 외부 LLM 출력(비신뢰 텍스트) — clean 을 거친다.

    citations: 초안 인용 문서(RunManager.Citation) — 의견 글에 섞인 내부 번호([own:…]·f:method:t1)를
    제목·"<섹션> 그림 n" 으로 바꾸고(ADR 0040), 의견마다 evidence_refs(제목·자료원 이름)를
    싣는다."""
    titles = titles_from(citations)

    def txt(value: str) -> str:
        return no_ids(clean(value), titles, section_titles)

    return {
        "round": review.round,
        "kind": getattr(review, "kind", "draft"),
        "final_round": getattr(review, "final_round", None),
        "draft_version": review.draft_version,
        "applied_ids": list(getattr(review, "applied_ids", []) or []),
        "applied_version": getattr(review, "applied_version", None),
        "score_delta": dict(getattr(review, "score_delta", {}) or {}),
        # Q7 후보 선택 {섹션: {choice, reason, rejected, rejected_text}} / Q5 필수 요소 충족
        "candidate_choices": {
            k: {kk: txt(str(vv)) for kk, vv in v.items()}
            for k, v in (getattr(review, "candidate_choices", {}) or {}).items()
        },
        "checklist": {k: dict(v) for k, v in (getattr(review, "checklist", {}) or {}).items()},
        "checklist_coverage": getattr(review, "checklist_coverage", None),
        "status": review.status,
        "skipped_reason": review.skipped_reason,
        "created_at": review.created_at,
        "excluded_sentences": list(review.excluded_sentences),
        "resolved_ids": list(review.resolved_ids),
        "scores": [
            {
                "criterion": s.criterion,
                "score": s.score,
                "weak": s.weak,
                "reason": txt(s.reason),
                "sentence_ids": list(s.sentence_ids),
            }
            for s in getattr(review, "scores", []) or []
        ],
        # U1 근거 적합성 — 문장 id → 지지|부분|불일치 (1차 검토만, 값은 허용 목록 안)
        "support": dict(getattr(review, "support", {}) or {}),
        "transfer": {
            "provider": review.transfer.provider,
            "model": review.transfer.model,
            "public_doc_ids": list(review.transfer.public_doc_ids),
            "internal_doc_ids": list(review.transfer.internal_doc_ids),
            "sentences_sent": review.transfer.sentences_sent,
            "sentences_excluded": review.transfer.sentences_excluded,
            "calls": review.transfer.calls,
        },
        "comments": [
            {
                "id": c.id,
                "section": c.section,
                "sentence": c.sentence,
                "sentence_id": f"s:{c.section}:{c.sentence}" if c.sentence is not None else None,
                "kind": getattr(c, "kind", "revision"),  # revision / addition(Q5 추가 문장)
                "after": getattr(c, "after", None),
                "issue_type": c.issue_type,
                "comment": txt(c.comment),
                "revised_text": txt(c.revised_text) if c.revised_text else None,
                "evidence": list(c.evidence),
                "evidence_refs": refs_for(list(c.evidence), citations),
                "status": c.status,
                "usable": c.usable,
                "discard_reason": c.discard_reason,
            }
            for c in review.comments
        ],
    }


def version_payload(
    version: Any, *, clean: Callable[[str], str] = _same, run_id: str = ""
) -> dict[str, Any]:
    return {
        "version": version.version,
        "figures": figures_payload(getattr(version, "figures", []) or [], run_id, clean=clean),
        "origin": version.origin,
        "origin_label": ORIGIN_LABEL.get(version.origin, version.origin),
        "created_at": version.created_at,
        "based_on_review": version.based_on_review,
        "reverted_from": version.reverted_from,
        "note": version.note,
        "changed_sections": list(getattr(version, "changed_sections", []) or []),
        "alerts": getattr(version, "alerts", 0),
        "open_annotations": getattr(version, "open_annotations", 0),
        "annotations": [
            {
                "id": a.id,
                "section": a.section,
                "sentence": a.sentence,
                "sentence_id": f"s:{a.section}:{a.sentence}" if a.sentence is not None else None,
                "kind": a.kind,
                "text": clean(a.text),
                "reason": a.reason,
                "status": a.status,
            }
            for a in getattr(version, "annotations", []) or []
        ],
        # U1 제안자 근거 판단 (문장 id × 근거 id → approve|replace|exclude)
        "evidence_decisions": [
            {"sentence_id": d.sentence_id, "evidence_id": d.evidence_id, "action": d.action}
            for d in getattr(version, "evidence_decisions", []) or []
        ],
        "sections": [
            {
                "key": sec.key,
                "sentences": [
                    {
                        "sentence_id": f"s:{sec.key}:{i}",
                        "text": clean(sent.text),
                        "evidence": list(sent.evidence),
                        "origin": sent.origin,
                        "source": _source(sent),
                    }
                    for i, sent in enumerate(sec.sentences)
                ],
                "choices": list(sec.choices),
            }
            for sec in version.sections
        ],
    }


def versions_payload(versions: list[Any], rows: list[Any] | None = None) -> list[dict[str, Any]]:
    """버전 목록 — 본문 없이 메타만(번호·시각·경로·메모·바뀐 섹션·문장 수·알림 수·남은 메모 수).

    항목 21(ADR 0042): changed_sections 는 이전 버전과의 실제 차이, changed_figures 는 바뀐 그림
    이름,
    marks·confirmations 는 그 버전에 쌓인 확인 기록, status_only 는 예전 run 의 상태만 바뀐
    버전(화면이
    "확인 기록" 으로 접는다), description 은 메모를 한국어로 고친 설명("그림 확인 — 연구 개념도").
    rows 는 RunManager.version_history 의 설명 줄(없으면 버전만으로 계산, 확인 기록·작성자 없음)."""
    from rra.domain.rules.version_history import version_rows

    by_no = {r.version: r for r in (rows if rows is not None else version_rows(versions))}
    out: list[dict[str, Any]] = []
    for v in versions:
        row = by_no.get(v.version)
        item = {
            "version": v.version,
            "origin": v.origin,
            "origin_label": ORIGIN_LABEL.get(v.origin, v.origin),
            "created_at": v.created_at,
            "based_on_review": v.based_on_review,
            "reverted_from": v.reverted_from,
            "note": v.note,
            "changed_sections": list(getattr(v, "changed_sections", []) or []),
            "sentences": sum(len(s.sentences) for s in v.sections),
            "alerts": getattr(v, "alerts", 0),
            "open_annotations": getattr(v, "open_annotations", 0),
            "figures": len(getattr(v, "figures", []) or []),
        }
        if row is not None:
            item.update(row.dump())
            if row.origin_label:
                item["origin_label"] = row.origin_label
        out.append(item)
    return out


def diff_payload(from_v: Any, to_v: Any, diff: list[dict], *, clean: Callable[[str], str] = _same):
    """두 버전의 차이 — 섹션마다 added/removed/moved 문장."""

    def rows(items):
        return [
            {**x, **{k: clean(v) for k, v in x.items() if k in ("text", "from", "to")}}
            for x in items
        ]

    from rra.domain.rules.figures import figure_diff
    from rra.domain.rules.version_history import figure_name

    old_figs = getattr(from_v, "figures", []) or []
    new_figs = getattr(to_v, "figures", []) or []
    names = {f.id: figure_name(f) for f in [*old_figs, *new_figs]}  # 화면은 이름만 (내부 id 없음)
    return {
        "from": from_v.version,
        "to": to_v.version,
        "figures_changed": [
            {**row, "name": names.get(row["figure_id"], "")}
            for row in figure_diff(old_figs, new_figs)
        ],
        "sections": [
            {
                **d,
                "added": rows(d["added"]),
                "removed": rows(d["removed"]),
                "moved": rows(d["moved"]),
            }
            for d in diff
        ],
    }


# 한 줄 칸 slot → 양식 칸 이름 (render_check 출력용). 섹션 키는 rules.yaml titles 로 푼다.
SLOT_LABELS = {
    "title": "1-가 연구과제명",
    "budget.account": "1-나 예산과목",
    "budget.amount_thousand_krw": "1-나 금액",
    "strategy_alignment:task": "2-가-(3) 전략과제",
    "department": "제안부서",
    "proposed_on": "제안일자",
    "proposer.rank": "제안자 직급",
    "proposer.name": "제안자 성명",
    "proposer.phone": "제안자 연락처",
    "head.rank": "부서장 직급",
    "head.name": "부서장 성명",
    "head.phone": "부서장 연락처",
}


def render_check_payload(
    check: Any, *, titles: dict[str, str] | None = None, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """RenderCheck → dict (CLI·UI·REST 공용). 렌더를 막지 않는 알림 목록이다."""
    names = {**SLOT_LABELS, **(titles or {})}
    return {
        "count": check.count,
        "unsupported_numbers": check.unsupported_numbers,
        "unresolved": [
            {
                "section": p.section,
                "code": p.code,
                "label": problem_label(p.code),
                "severity": p.severity,
                "severity_label": severity_label(p.severity),
                "message": no_ids(clean(p.message), None, names),
                "sentence": p.sentence,
            }
            for p in check.unresolved
        ],
        "overflow": [
            {
                "slot": o.slot,
                "label": names.get(o.slot, o.slot),
                "chars": o.chars,
                "limit": o.limit,
                "kind": o.kind,
            }
            for o in check.overflow
        ],
        "notes": list(check.notes),
    }


def render_check_lines(payload: dict[str, Any]) -> list[str]:
    """render_check_payload → 사람이 읽는 줄 (CLI stdout·UI 캡션). 비면 빈 목록."""
    if not payload["count"]:
        return []
    lines = [f"렌더 전 점검: 알림 {payload['count']}건 (렌더는 진행합니다)"]
    if payload.get("unsupported_numbers"):
        lines.append(
            f" ! 근거 없는 수치 알림 {payload['unsupported_numbers']}건 — 입력·근거에 없는 수치는 "
            "양식에서 직접 확인하거나 지우십시오"
        )
    for p in payload["unresolved"]:
        where = p["section"] + (f" 문장 {p['sentence'] + 1}" if p["sentence"] is not None else "")
        lines.append(f" - [{p['severity']}] {where}: {p['message']}")
    for o in payload["overflow"]:
        kind = "한 줄 칸" if o["kind"] == "line" else "본문 상한"
        lines.append(f" - 칸 길이 초과({kind}): {o['label']} {o['chars']}자 > {o['limit']}자")
    lines.extend(f" - {n}" for n in payload["notes"])
    return lines


def policy_suggestions_payload(
    suggestions: list[Any], *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """정책 근거 추천 — 제안자가 고를 목록.

    policy_basis_text 는 고른 뒤 칸에 넣을 문자열(자동 삽입 없음)."""
    from rra.domain.rules.policy_phrases import policy_basis_text

    return [
        {
            "doc_id": s.doc_id,
            "title": clean(s.title),
            # ADR 0040 — 화면은 doc_id 대신 제목·자료원 이름. 인용 아래 "원문" 링크는 url
            "source": source_of(s.doc_id),
            "source_label": source_name(source_of(s.doc_id)),
            "year": s.year,
            "page": clean(s.page) if s.page else None,
            "quote": clean(s.quote),
            "url": s.url,
            "menu_path": clean(s.menu_path) if s.menu_path else None,
            "keywords": list(s.keywords),
            "similarity": s.similarity,
            "policy_basis_text": clean(policy_basis_text(s)),
        }
        for s in suggestions
    ]


def notice_matches_payload(
    matches: list[Any], *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """공고문 대조(#13 선행) — 접수 중인 공고 상위 3건. 제안서에 자동 삽입 없음."""
    return [
        {
            "doc_id": m.doc_id,
            "title": clean(m.title),
            "agency": clean(m.agency) if m.agency else None,
            "program": clean(m.program) if m.program else None,
            "posted": m.posted.isoformat() if m.posted else None,
            "deadline": m.deadline.isoformat() if m.deadline else None,
            "days_left": m.days_left,
            "url": m.url,
            "similarity": m.similarity,
        }
        for m in matches
    ]


def alerts_payload(
    alerts: list[Any],
    *,
    clean: Callable[[str], str] = _same,
    live_ids: Collection[str] = (),
) -> dict[str, Any]:
    """유사과제 경보 목록 → 출력용 dict (MCP·REST 공용). 제목은 수집 문서에서 온 비신뢰 텍스트.
    live_ids: 이번 세션의 실시간 검색 결과 doc_id ([4] — 항목마다 live)."""
    live = set(live_ids)
    return {
        "blocking": any(a.blocking for a in alerts),
        "alerts": [
            {
                "doc_id": a.doc_id,
                "title": clean(display_title(a.title)),  # 공시용 요약문 머리 뗌 (ADR 0043)
                "tier": a.tier,
                "similarity": round(a.similarity, 4),
                "blocking": a.blocking,
                "basis": a.basis,
                "keywords": list(a.keywords),
                "status": a.status,
                "status_label": STATUS_LABELS.get(
                    a.status or "", a.status
                ),  # 용역으로 진행 중/예정 등
                "own_detail": a.own_detail,
                "tier_label": (
                    RESEARCH_SERVICE_LABEL
                    if a.tier == "procurement" and source_of(a.doc_id) == "korail_web"
                    else tier_label(a.tier, a.own_detail)
                ),  # 공사 사전정보공표 연구용역 = "연구용역(사내 발주)" (ADR 0040)
                "live": a.doc_id in live,
                # ② 판정 정확도 (레인 A) — reranker 점수·AI 같음 판정·같은 제목 묶음·제안자 선택
                "rerank_score": getattr(a, "rerank_score", None),
                "rule_blocking": getattr(a, "rule_blocking", None),
                "judgment": getattr(a, "judgment", None),
                "judgment_label": VERDICT_LABELS.get(getattr(a, "judgment", None) or "", None),
                "judgment_reason": clean(getattr(a, "judgment_reason", "") or ""),
                "judged_by": getattr(a, "judged_by", None),
                "judged_by_label": JUDGED_BY_LABELS.get(getattr(a, "judged_by", None) or "", None),
                "merged_ids": list(getattr(a, "merged_ids", []) or []),
                "choice": getattr(a, "choice", None),
                # ② v3 (ADR 0039): 판정 칸(같다→차단·일부 겹침→근접·다르다→관련 낮음, AI 전엔
                # 규칙 기준)·관련도(reranker 높음/보통/낮음)·자료원 이름.
                # 화면은 유사도·내부 번호를 보이지 않는다
                **level_view(a),
                "source_label": source_label_of(a.doc_id),
                # 같은 연작 묶음 (ADR 0043) — "광역철도 수송수요 예측(연작 7건)" + 연도별 목록
                "series": series_payload(getattr(a, "series", None), clean=clean),
            }
            for a in alerts
        ],
    }


def source_label_of(doc_id: str) -> str:
    """doc_id 앞머리(own:·alio:·ntis: …) → 자료원 한국어 이름. 모르면 빈 값."""
    return SOURCE_LABELS.get((doc_id or "").split(":", 1)[0], "")


def judgment_payload(info: Any) -> dict[str, Any]:
    """② AI 같음 판정 요약 → 화면 안내. 실패면 "AI 판정 실패 — 규칙 기준" + retry_available."""
    status = getattr(info, "status", "off")
    judged_by = getattr(info, "judged_by", None)
    return {
        "status": status,
        "judged_by": judged_by,
        "judged_by_label": JUDGED_BY_LABELS.get(judged_by or "", None),
        "message": judgment_message(status, judged_by),
        "retry_available": status == "rule_fallback",
        "candidates": getattr(info, "candidates", 0),
        "provider": getattr(info, "provider", None),
        "model": getattr(info, "model", None),
        "calls": getattr(info, "calls", 0),
    }


def related_research_payload(
    items: list[Any], *, clean: Callable[[str], str] = _same, live_ids: Collection[str] = ()
) -> list[dict[str, Any]]:
    """② 관련 연구(참고) 목록 → 출력용 (REST). 판정이 아니다 — 제목은 비신뢰 텍스트(ADR 0028).

    프론트엔드 영향: ② 유사과제 확인의 "관련 연구" 목록(related_research[], 배지 "참고")."""
    live = set(live_ids)
    return [
        {
            "doc_id": r.doc_id,
            "title": clean(r.title),
            "source": r.source,
            "source_label": SOURCE_LABELS.get(r.source, r.source),
            "doc_type": r.doc_type,
            "year": r.year,
            "similarity": round(r.similarity, 4),
            "url": r.url,
            "live": r.doc_id in live,  # [4] 실시간 검색에서 찾은 자료
        }
        for r in items
    ]


def ntis_insights_payload(insights: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """NtisInsights → dict (REST). 제목·성과는 NTIS API 출력(비신뢰) → clean. 양식 본문 근거로 쓰지
    않는다.

    프론트엔드 영향: ② 과제 카드의 "주요 성과"(projects[].outcomes) 와 "NTIS
    추천"(ntis_recommended)."""
    return {
        "projects": [
            {
                "project_no": p.project_no,
                "doc_id": p.doc_id,
                "title": clean(p.title),
                "tier": p.tier,
                "tier_label": tier_label(p.tier),
                "similarity": round(p.similarity, 4),
                "blocking": p.blocking,
                "cached": p.cached,
                "error": p.error,
                "outcomes": [
                    {
                        "kind": o.kind,
                        "title": clean(o.title),
                        "year": o.year,
                        "venue": clean(o.venue) if o.venue else None,
                        "result_id": o.result_id,
                        "registration_no": o.registration_no,
                    }
                    for o in p.outcomes
                ],
            }
            for p in insights.projects
        ],
        "ntis_recommended": [
            {
                "project_no": r.project_no,
                "title": clean(r.title),
                "url": NTIS_PROJECT_URL.format(project_no=r.project_no),
                "score": r.score,
                "rank": r.rank,
                "source_project_no": r.source_project_no,
            }
            for r in insights.recommended
        ],
        # IP 거부로 조회를 건너뛴 경우의 안내 (레인 I). 평소 None.
        "unavailable": getattr(insights, "unavailable", None),
    }


# NTIS 과제 상세 페이지 — 공개 사이트 경로 (실호출 뒤 확인). 수집 Document 에는 넣지 않는다 (검증 안
# 된 링크)
NTIS_PROJECT_URL = "https://www.ntis.go.kr/project/pjtInfo.do?pjtId={project_no}"


def differentiation_payload(
    proposal: Any, *, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """DifferentiationProposal → dict (CLI·MCP·REST 공용). 항목 본문은 LLM 출력(비신뢰) → clean."""
    return {
        "skipped_reason": proposal.skipped_reason,
        "skipped_label": differentiation_skip_label(proposal.skipped_reason),
        "provider": proposal.provider,
        "model": proposal.model,
        "fallback_local": proposal.fallback_local,
        "transfer": {
            "public_doc_ids": list(proposal.public_doc_ids),
            "internal_doc_ids": list(proposal.internal_doc_ids),
            "excluded_doc_ids": list(proposal.excluded_doc_ids),
            "calls": proposal.calls,
        },
        "items": [
            {
                "doc_id": i.doc_id,
                "title": clean(display_title(i.title)),
                "tier": i.tier,
                "status": i.status,
                "overlap_summary": clean(i.overlap_summary),
                "build_on": clean(i.build_on),
                "differentiation": [clean(d) for d in i.differentiation],
                "evidence": list(i.evidence),
            }
            for i in proposal.items
        ],
        "discarded": [dict(d) for d in proposal.discarded],
    }


OVERLAP_BY_LABELS: dict[str, str] = {
    "argon": "Argon 판정",
    "local": "로컬 모델 판정",
    "rule": "규칙 기준(AI 확인 실패)",
}


def recommendations_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """RecommendationResult → dict (CLI·MCP·REST 공용). 본문은 LLM 출력(비신뢰) → clean."""
    return {
        "skipped_reason": result.skipped_reason,
        "skipped_label": recommendation_skip_label(result.skipped_reason),
        "regenerated": bool(getattr(result, "regenerated", False)),
        "overlap_checked": bool(getattr(result, "overlap_checked", False)),
        "overlap_regenerated": int(getattr(result, "overlap_regenerated", 0) or 0),
        "overlap_found": int(getattr(result, "overlap_found", 0) or 0),
        "similar_doc_ids": list(getattr(result, "similar_doc_ids", []) or []),
        "no_recommendation_reason": (
            clean(result.no_recommendation_reason) if result.no_recommendation_reason else None
        ),
        "provider": result.provider,
        "model": result.model,
        "fallback_local": result.fallback_local,
        "transfer": {
            "public_doc_ids": list(result.public_doc_ids),
            "internal_doc_ids": list(result.internal_doc_ids),
            "excluded_doc_ids": list(result.excluded_doc_ids),
            "calls": result.calls,
        },
        "recommendations": [
            {
                "index": i,
                "title": clean(r.title),
                "summary": clean(r.summary),
                "differentiation": clean(r.differentiation),
                "goal": clean(getattr(r, "goal", "") or ""),
                "method": clean(getattr(r, "method", "") or ""),
                "scope": clean(getattr(r, "scope", "") or ""),
                "reasons": [clean(x) for x in r.reasons],
                "build_on": clean(r.build_on),
                "risks": clean(r.risks),
                "compared_with": list(r.compared_with),
                "evidence": list(r.evidence),
                "overlap_warning": list(r.overlap_warning),
                # ② v3 카드 (ADR 0039) — 근거는 제목·자료원, 겹침은 판정의 제목·한 줄 겹치는 점
                "refs": [
                    {
                        "doc_id": ref.doc_id,
                        "title": clean(display_title(ref.title)),
                        "source_label": SOURCE_LABELS.get(ref.source, "")
                        or source_label_of(ref.doc_id),
                    }
                    for ref in getattr(r, "refs", []) or []
                ],
                "overlap_titles": [
                    clean(display_title(t)) for t in getattr(r, "overlap_titles", []) or []
                ],
                "overlap_reason": clean(getattr(r, "overlap_reason", "") or ""),
                "overlap_by": getattr(r, "overlap_by", None),
                "overlap_by_label": OVERLAP_BY_LABELS.get(
                    getattr(r, "overlap_by", None) or "", None
                ),
                "regenerated": bool(getattr(r, "regenerated", False)),
                "difference": getattr(r, "difference", None),
                "difference_label": DIFFERENCE_LABELS.get(
                    getattr(r, "difference", None) or "", None
                ),
                "added": bool(getattr(r, "added", False)),
            }
            for i, r in enumerate(result.recommendations)
        ],
        "discarded": [
            {
                **{k: clean(str(v)) for k, v in d.items()},
                "reason_label": discard_label(str(d.get("reason", ""))),
            }
            for d in result.discarded
        ],
    }


def recommendation_preview_payload(
    before: Any, after: Any, preview: Any, *, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """추천 적용 미리보기 — 바뀐 칸과 전/후 값. 사용자가 고쳐 확정한 입력으로 초안을 만든다."""
    fields = ("title_hint", "goal", "method", "scope", "differentiation")
    return {
        "index": preview.index,
        "changed": list(preview.changed),
        "before": {k: clean(getattr(before, k)) for k in fields},
        "after": {k: clean(getattr(after, k)) for k in fields},
        "request": {
            k: (clean(v) if isinstance(v, str) else v) for k, v in after.model_dump().items()
        },
    }


# ── U1·U3·U7·U8 ───────────────────────────────────────────
def evidence_items_payload(
    items: list[Any], *, clean: Callable[[str], str] = _same, live_ids: Collection[str] = ()
) -> list[dict[str, Any]]:
    """EvidenceItem → dict. 발췌·제목은 수집 자료(비신뢰). live_ids: run 의 실시간 검색 doc_id
    ([4])."""
    live = set(live_ids)
    return [
        {
            "evidence_id": i.evidence_id,
            "doc_id": i.doc_id,
            "chunk_id": i.chunk_id,
            "text": clean(i.text),
            "title": clean(i.title) if i.title else UNTITLED,  # 화면은 번호를 보이지 않는다
            "source": i.source,
            "source_label": i.source_label,
            "orgs": list(i.orgs),
            "year": i.year,
            "ingested_at": i.ingested_at,
            "basis": i.basis,
            "basis_label": i.basis_label,
            "needs_check": i.needs_check,
            "needs_check_label": "세부 확인 필요" if i.needs_check else None,
            "support": i.support,
            "decision": i.decision,
            "in_snapshot": i.in_snapshot,
            "url": getattr(i, "url", None),  # 원본 링크(이미지 판독은 이미지 URL)
            "live": i.doc_id in live,
            "trust": "untrusted",
        }
        for i in items
    ]


def rewrite_payload(view: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """RewriteView → dict. 후보 문장은 LLM 출력(비신뢰)."""

    def sent(x):
        return None if x is None else {**x, "text": clean(x["text"])}

    return {
        "section": view.section,
        "created_at": view.created_at,
        "dropped": len(view.dropped),
        "rows": [
            {"index": r["index"], "current": sent(r["current"]), "candidate": sent(r["candidate"])}
            for r in view.rows
        ],
        "candidate": [
            {
                "index": i,
                "text": clean(s.text),
                "evidence": list(s.evidence),
                "origin": s.origin,
                "source": _source(s),
            }
            for i, s in enumerate(view.candidate.sentences)
        ],
        "choices": list(view.candidate.choices),
        # 2026-10-28 레인 B: 새 문장 수·사유(0 이면 화면이 사유 + [다시 시도])·새로 쓰기 여부·작성자
        "new_count": sum(1 for s in view.candidate.sentences if s.origin not in _PRESERVED_ORIGINS),
        "reason": getattr(view, "reason", None),
        "reason_label": rewrite_reason_label(getattr(view, "reason", None)),
        "mode": getattr(view, "mode", "rewrite"),
        "writer": _writer_label(getattr(view, "writer", None)),
    }


_PRESERVED_ORIGINS = frozenset({"proposer_edit", "proposer_input", "proposer", "app"})


def _writer_label(writer: dict | None) -> dict[str, Any] | None:
    """작성 기록 → 화면용 {model, label, local_fallback} (본문·doc_id 없음)."""
    if not writer:
        return None
    local = bool(writer.get("local_fallback")) or writer.get("provider") == "mlx"
    return {
        "provider": writer.get("provider"),
        "model": writer.get("model"),
        "local_fallback": bool(writer.get("local_fallback")),
        "label": "로컬 모델" if local else "Argon",
    }


def submit_check_payload(
    check: Any, *, titles: dict[str, str] | None = None, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """SubmitCheck → dict. 항목마다 target(section:<key> | sentence:<sid> | route:<hint>)."""
    names = titles or {}
    slot_names = {**SLOT_LABELS, **names}

    def detail(i: Any) -> str:
        if i.key == "field_limits" and i.extra.get("overflow"):
            return ", ".join(
                f"{slot_names.get(r['slot'], r['slot'])} {r['chars']}자 > {r['limit']}자"
                for r in i.extra["overflow"]
            )
        return i.detail

    return {
        "ok": check.ok,
        "failing": len(check.failing),
        "items": [
            {
                "key": i.key,
                "label": i.label,
                "ok": i.ok,
                "detail": no_ids(clean(detail(i)), None, names),
                "count": i.count,
                "target": i.target,
                "target_label": (
                    names.get(i.target.split(":", 1)[1], i.target.split(":", 1)[1])
                    if i.target and i.target.startswith("section:")
                    else None
                ),
                **{k: v for k, v in i.extra.items()},
            }
            for i in check.items
        ],
    }


def usage_payload(record: Any) -> dict[str, Any] | None:
    """UsageRecord → dict. 개인정보·본문 없음 (한 줄 소감은 길이 제한된 제안자 입력)."""
    if record is None:
        return None
    steps = dict(record.step_seconds)
    return {
        "run_id": record.run_id,
        "step_seconds": steps,
        # 항목 16 — 화면용 줄 목록. 섹션 작성은 실제 경과(벽시계), 합계는 보조 줄
        "steps": [
            {
                "key": k,
                "label": step_label(k),
                "seconds": v,
                "secondary": k == "sections_sum",
            }
            for k, v in steps.items()
        ],
        "total_seconds": record.total_seconds,
        "total_label": "전체 경과(사람 작업 포함)",
        "checklist_coverage": record.checklist_coverage,
        "evidence": {**record.evidence.model_dump(), "ratios": record.evidence.ratios()},
        "rewrites": record.rewrites,
        "hwpx_success": record.hwpx_success,
        "satisfaction": (
            {
                "score": record.satisfaction.score,
                "comment": record.satisfaction.comment,
                "recorded_at": record.satisfaction.recorded_at,
            }
            if record.satisfaction
            else None
        ),
        "updated_at": record.updated_at,
    }


def structure_payload(idea: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """StructuredIdea → dict. 칸 글은 LLM 출력(비신뢰) → clean. 서버는 저장하지 않는다."""
    from rra.domain.models.structure import FIELD_LABELS

    return {
        "fields": {k: clean(v) for k, v in idea.fields.items()},
        "labels": dict(FIELD_LABELS),
        "questions": [
            {
                "field": q.field,
                "label": FIELD_LABELS.get(q.field, q.field),
                "question": q.question,
                "reason": q.reason,
            }
            for q in idea.questions
        ],
        "skip_allowed": idea.skip_allowed,
        "complete": idea.complete,
        "provider": idea.provider,
        "model": idea.model,
        "parse_failed": idea.parse_failed,
    }


def comparison_payload(table: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """ComparisonTable → dict. 기존 과제 칸은 수집 자료(비신뢰) → clean."""

    def col(c):
        return {
            "doc_id": c.doc_id,
            "title": clean(display_title(c.title)),
            "tier": c.tier,
            "similarity": c.similarity,
            "blocking": c.blocking,
            "basis": c.basis,
            "title_only": c.title_only,
            "cells": {k: clean(v) for k, v in c.cells.items()},
        }

    extraction = getattr(table, "extraction", "rule")
    by = getattr(table, "extraction_by", None)
    return {
        "aspects": list(table.aspects),
        "proposal": col(table.proposal),
        "projects": [col(c) for c in table.projects],
        "empty_reason": getattr(table, "empty_reason", None),
        "proposal_source": getattr(table, "proposal_source", "input"),
        "extraction": extraction,
        "extraction_by": by,
        "extraction_label": extraction_label(extraction, by),
    }


def polish_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """② [AI로 다듬기] 결과 — 다듬은 글(LLM 출력, 비신뢰 → clean) 또는 원래 글 + 사유."""
    return {
        "field": result.field,
        "text": clean(result.text),
        "changed": result.changed,
        "by": result.by,
        "by_label": JUDGED_BY_LABELS.get(result.by or "", None),
        "reason": result.reason,
    }


def brief_payload(brief: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """PriorWorkBrief → dict. 요약·공백 후보는 LLM 출력(비신뢰) → clean."""
    return {
        "skipped_reason": brief.skipped_reason,
        "provider": brief.provider,
        "model": brief.model,
        "fallback_local": brief.fallback_local,
        "transfer": {
            "public_doc_ids": list(brief.public_doc_ids),
            "internal_doc_ids": list(brief.internal_doc_ids),
            "excluded_doc_ids": list(brief.excluded_doc_ids),
            "calls": brief.calls,
        },
        "items": [
            {
                "doc_id": i.doc_id,
                "chunk_id": i.chunk_id,
                "title": clean(i.title),
                "source": i.source,
                "doc_type": i.doc_type,
                "year": i.year,
                "basis": i.basis,
                "summary": clean(i.summary),
                "summary_missing": i.summary_missing,
            }
            for i in brief.items
        ],
        "years": dict(brief.years),
        "keywords": list(brief.keywords),
        "gap_label": brief.gap_label,
        "gaps": [{"text": clean(g.text), "evidence": list(g.evidence)} for g in brief.gaps],
        "discarded": [dict(d) for d in brief.discarded],
    }


def run_state_payload(
    state: Any, *, legacy: bool = False, title: str | None = None
) -> dict[str, Any]:
    """RunState → 상태 조회 응답 (초안 본문 없음). title: 연구과제명(항목 2, 비신뢰 문장)."""
    done, total = state.progress
    return {
        "run_id": state.run_id,
        "title": title,
        "status": state.status,
        "progress": [done, total],
        "template": state.template,
        "legacy": legacy,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "steps": [{"name": s.name, "status": s.status, "error": s.error} for s in state.steps],
        "draft_version": state.draft_version,
        "flow": flow_summary(state),
        "failed_sections": failed_sections_payload(state),
        "fallback_sections": fallback_sections_payload(state),
        "writer": getattr(state, "writer", "local"),  # [3] gemini | local
        "local_sections": local_sections_payload(state),
        # [4] 실시간 자료 검색 요약 (없으면 null — 꺼짐·예전 run)
        "live_search": getattr(state, "live_search", None),
    }


LIVE_OFF: dict[str, Any] = {"status": "off", "keywords": {"ko": [], "en": []}, "sources": []}


def live_search_payload(summary: Any | None) -> dict[str, Any]:
    """[4] LiveSearchSummary → REST 모양. None 이면 off. 안내 문구는 짧은 앱 문구(비밀 없음)."""
    if summary is None:
        return {**LIVE_OFF, "keywords": {"ko": [], "en": []}, "sources": []}
    return summary.payload()


def chunks_payload(
    chunks: list[Any], *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """검색 결과 청크 → dict. 전부 비신뢰(trust=untrusted) — 지시가 아니라 자료다."""
    return [
        {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "ordinal": c.ordinal,
            "basis": c.basis,
            "similarity": c.similarity,  # 질의 코사인 (벡터 색인 없으면 None)
            "text": clean(c.text),
            "trust": "untrusted",
        }
        for c in chunks
    ]


def facts_payload(facts: list[Any], *, clean: Callable[[str], str] = _same) -> list[dict[str, Any]]:
    """표 사실(P2-8) → dict. 전부 비신뢰 — 표에서 파싱·판독한 값이지 확인된 사실이 아니다."""
    return [
        {
            "item": clean(f.item),
            "year": f.year,
            "unit": clean(f.unit) if f.unit else None,
            "value": float(f.value),
            "value_text": clean(f.value_text),
            "doc_id": f.doc_id,
            "page": f.page,
            "sheet": clean(f.sheet) if f.sheet else None,
            "basis": f.basis,
            "trust": "untrusted",
        }
        for f in facts
    ]


def fact_line(f: Any, *, clean: Callable[[str], str] = _same) -> str:
    """CLI 한 줄: 항목 · 연도 · 값단위 · 출처."""
    year = f"{f.year}년 " if f.year else ""
    where = (
        f.doc_id + (f" p.{f.page}" if f.page else "") + (f" [{clean(f.sheet)}]" if f.sheet else "")
    )
    basis = " (이미지 판독)" if f.basis == "image_vision" else ""
    return f"{clean(f.item)}: {year}{clean(f.value_text)}{clean(f.unit or '')} — {where}{basis}"


# ── 벤치 보고 (docs/llm-bench-<날짜>.md) ──────────────────
def bench_markdown(results: list[Any], *, date: str, baseline: str | None = None) -> str:
    """BenchResult 목록 → 비교 표 Markdown. 기술적 중요도 문장은 모델별로 3건씩 나란히."""
    rows = [r if isinstance(r, dict) else r.to_dict() for r in results]
    head = ["지표", *[r["label"] for r in rows]]
    lines = [f"# 로컬 작성 모델 비교 — {date}", ""]
    n_ideas = len(rows[0]["ideas"]) if rows else 0
    lines.append(f"골든셋 {n_ideas}건, 12개 섹션 생성, 같은 입력·같은 수집 자료.")
    if baseline:
        lines.append(f"기준 모델: {baseline}.")
    lines.append("")

    def pct(r):
        return f"{r['json_success_rate'] * 100:.1f}% ({r['parse_ok']}/{r['sections_llm']})"

    def strict(r):
        n = r.get("parse_ok_strict", r["parse_ok"])
        rate = r.get("strict_success_rate", r["json_success_rate"])
        return f"{rate * 100:.1f}% ({n}/{r['sections_llm']})"

    metrics = [
        ("모델(served_model)", lambda r: r["model"] or "-"),
        ("프로필", lambda r: r["profile"] or "-"),
        ("JSON (a) 첫 응답이 지시 모양 그대로인 비율", strict),
        ("JSON (b) 관용 처리·재요청·폴백 포함 최종 성공률 — 규칙 ② 기준", pct),
        ("형식 교정 재요청 횟수", lambda r: str(r.get("retries", 0))),
        ("프롬프트 폴백 횟수", lambda r: str(r["fallbacks"])),
        ("근거 대조 폐기 문장 수", lambda r: str(r["totals"]["dropped"])),
        ("수치 알림 수", lambda r: str(r["totals"]["unsupported_numbers"])),
        ("외국 문자 알림 수", lambda r: str(r["totals"]["foreign_script"])),
        ("정책명 규칙 위반(grounding 폐기) 수", lambda r: str(r["totals"]["ungrounded"])),
        ("lint 문제 합계", lambda r: str(r["totals"]["problems"])),
        ("관련도 하한 통과 근거 청크 수", lambda r: str(r["totals"].get("evidence_chunks", "-"))),
        ("관련도 하한 탈락 청크 수", lambda r: str(r["totals"].get("dropped_chunks", "-"))),
        ("인용된 근거 id 수", lambda r: str(r["totals"].get("cited_chunks", "-"))),
        ("근거 없어 빈칸이 된 섹션 수", lambda r: str(r["totals"].get("empty_sections", "-"))),
        ("섹션당 평균 시간(초)", lambda r: f"{r['avg_section_seconds']:.1f}"),
        ("전체 시간(초)", lambda r: f"{r['total_seconds']:.1f}"),
        (
            "최대 메모리(서버 RSS, MB)",
            lambda r: f"{r['max_rss_mb']:.0f}" if r["max_rss_mb"] else "-",
        ),
        ("최대 문맥 길이(토큰)", lambda r: str(r["context_length"] or "-")),
        ("실제 최대 프롬프트 토큰", lambda r: str(r["max_prompt_tokens"] or "-")),
        ("최대 응답 토큰", lambda r: str(r["max_completion_tokens"] or "-")),
        ("LLM 호출 수", lambda r: str(r["llm_calls"])),
    ]
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "---|" * len(head))
    for name, fn in metrics:
        lines.append("| " + " | ".join([name, *[fn(r) for r in rows]]) + " |")
    lines.append("")
    lines.append("## 아이디어별")
    lines.append("")
    for i, idea in enumerate(rows[0]["ideas"] if rows else []):
        lines.append(f"### {idea['name']}")
        lines.append("")
        lines.append(
            "| 모델 | 제목 | 시간(초) | JSON ok | 폐기 | 수치 | 외국 문자 | 유사과제 알림 "
            "| 근거 | 탈락 | 인용 | 빈칸 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            if i < len(r["ideas"]):
                x = r["ideas"][i]
                cells = [
                    r["label"],
                    x["title"][:60],
                    f"{x['seconds']:.1f}",
                    f"{x['parse_ok']}/{x['sections_llm']}",
                    str(x["dropped"]),
                    str(x["unsupported_numbers"]),
                    str(x["foreign_script"]),
                    str(x["overlap_alerts"]),
                    str(x.get("evidence_chunks", "-")),
                    str(x.get("dropped_chunks", "-")),
                    str(x.get("cited_chunks", "-")),
                    ",".join(x.get("empty_sections") or []) or "0",
                ]
                lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("2-가-(2) 기술적 중요도 문장 (모델별 3건):")
        lines.append("")
        for r in rows:
            if i < len(r["ideas"]):
                lines.append(f"- **{r['label']}**")
                for s in r["ideas"][i]["tech_sentences"] or ["(없음)"]:
                    lines.append(f"  - {s}")
        failed = [
            (r["label"], r["ideas"][i]["parse_failed"])
            for r in rows
            if i < len(r["ideas"]) and r["ideas"][i]["parse_failed"]
        ]
        if failed:
            lines.append("")
            lines.append("파싱 실패: " + "; ".join(f"{lbl}: {', '.join(f)}" for lbl, f in failed))
        lines.append("")
    return "\n".join(lines) + "\n"


EVAL_STEP_LABELS = {
    "clarify": "Q1 보강 질문",
    "outline": "Q2 설계도",
    "section_search": "Q3 섹션별 검색",
    "exemplars": "Q4 본보기",
    "additions": "Q5 보완 작성",
    "rule_check": "Q6 규칙 검사",
    "two_candidates": "Q7 두 후보",
    "reranker": "Q8 reranker",
    "draft_review": "Argon 1차 검토",
}


def eval_markdown(results: list[dict[str, Any]], *, date: str) -> str:
    """`rra eval --report` — 구성별 합계 비교표와 아이디어별 표. 결과는 EvalResult.to_dict()."""

    def num(v: Any) -> str:
        if v is None:
            return "-"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    lines = [f"## 초안 품질 강화 비교 ({date})", ""]
    lines.append("### 구성")
    lines.append("")
    lines.append("| 구성 | 켠 단계 | 모델 | 검토 모델 |")
    lines.append("|---|---|---|---|")
    for r in results:
        on = [EVAL_STEP_LABELS.get(k, k) for k, v in (r.get("pipeline") or {}).items() if v is True]
        lines.append(
            f"| {r['label']} | {', '.join(on) or '(없음)'} | {r.get('model') or '-'} | "
            f"{r.get('review_model') or '-'} |"
        )
    lines.append("")
    lines.extend(eval_compare_lines(results))
    lines.append("### 합계 (골든셋 전체)")
    lines.append("")
    cols = [
        ("v1_alerts", "v1 알림"),
        ("v2_alerts", "v2 알림"),
        ("sentences_v1", "문장 v1"),
        ("sentences_v2", "문장 v2"),
        ("style_fixed", "자동 정리"),
        ("style_warnings", "규칙 경고"),
        ("cited_ids", "인용 id"),
        ("paper_citations", "논문 인용"),
        ("irrelevant_citations", "무관 인용"),
        ("applied", "수정안 반영"),
        ("additions_applied", "추가 문장 반영"),
        ("checklist_coverage", "필수 요소 충족률"),
        ("score_sum", "1차 점수합"),
        ("score_avg", "1차 점수 평균"),
        ("precheck_hits", "precheck 적중"),
        ("seconds_avg", "평균 시간(s)"),
        ("gemini_calls", "Gemini 호출"),
        ("invalid", "invalid run"),
        ("failed_sections", "실패 섹션"),
        ("fallback_sections", "대체 작성"),
        ("local_sections", "로컬 대체"),
        ("compose_calls", "Gemini 작성 호출"),
        ("figures_total", "그림"),
        ("figures_nano", "Nano Banana 채택"),
        ("figures_baseline", "기본 그림"),
        ("figures_skipped", "그림 건너뜀"),
        ("figure_calls", "그림 호출"),
        ("figure_seconds_avg", "그림 단계(s)"),
        ("figure_comments", "그림 지적"),
    ]
    lines.append("| 구성 | " + " | ".join(label for _, label in cols) + " | RSS(MB) | reranker |")
    lines.append("|---|" + "---|" * (len(cols) + 2))
    for r in results:
        t = r.get("totals") or {}
        rr = r.get("reranker") or {}
        rr_text = f"{rr.get('calls', 0)}회 {rr.get('seconds', 0):.1f}s" if rr else "-"
        hits = f"{t.get('precheck_hits', 0)}/{t.get('precheck_known', 0)}"
        cells = [hits if key == "precheck_hits" else num(t.get(key)) for key, _ in cols]
        lines.append(
            f"| {r['label']} | "
            + " | ".join(cells)
            + f" | {num(r.get('max_rss_mb'))} | {rr_text} |"
        )
    lines.append("")
    lines.append("### 아이디어별")
    lines.append("")
    lines.append(
        "| 구성 | 아이디어 | 상태 | 실패/대체 섹션 | v1 알림 | v2 알림 | 문장 v1→v2 | 무관 인용 | "
        "점수 | 반영(수정+추가) | 충족률 | 후보 | precheck | 시간(s) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        for i in r.get("ideas") or []:
            scores = " ".join(f"{k[:2]}{v}" for k, v in (i.get("scores") or {}).items()) or "-"
            cands = ",".join(f"{k}:{v}" for k, v in (i.get("candidates") or {}).items()) or "-"
            pre = f"{i.get('precheck_alerts', 0)}건"
            if i.get("precheck_hit") is not None:
                pre += " ✓" if i["precheck_hit"] else " ✗"
            ff = ",".join(i.get("failed_sections") or []) or "-"
            fb = ",".join(i.get("fallback_sections") or []) or "-"
            lines.append(
                f"| {r['label']} | {i['name']} | {i.get('status')} | {ff}/{fb} | "
                f"{i.get('v1_alerts')} | "
                f"{num(i.get('v2_alerts'))} | {i.get('sentences_v1')}→{i.get('sentences_v2')} | "
                f"{i.get('irrelevant_citations')} | {scores} | "
                f"{i.get('applied')}+{i.get('additions_applied')} | "
                f"{num(i.get('checklist_coverage'))} | {cands} | {pre} | {i.get('seconds')} |"
            )
    lines.append("")
    lines.extend(_eval_idea_integrated_lines(results))
    return "\n".join(lines)


def _dash(v: Any, fmt: str = "{}") -> str:
    return "-" if v is None else fmt.format(v)


def _ratio(a: Any, b: Any) -> str:
    """a/b (백분율). 분모가 없거나 0 이면 "-"."""
    if a is None or not b:
        return "-"
    return f"{a / b:.0%} ({a}/{b})"


def _mode_text(r: dict[str, Any]) -> str:
    if r.get("mode") != "concurrent":
        return "순차" if "mode" in r else "-"
    t = r.get("totals") or {}
    return (
        f"동시 {r.get('concurrent')}건 (묶음 생성 {_dash(t.get('batch_draft_seconds_avg'))}s·"
        f"전체 {_dash(t.get('batch_seconds_avg'))}s)"
    )


def _gemini_split(r: dict[str, Any]) -> str:
    """작성·검토·그림 Gemini 호출. 예전 JSON 은 아이디어별 대체 작성(fallback_calls)·검토
    (gemini_calls)에서 맞추고, 그림은 "-"."""
    t = r.get("totals") or {}
    if "gemini_compose" in t:
        return f"{t['gemini_compose']}·{t['gemini_review']}·{t['gemini_figures']}"
    ideas = r.get("ideas") or []
    if not ideas:
        return "-"
    compose = sum(int(i.get("fallback_calls") or 0) for i in ideas)
    review = sum(int(i.get("gemini_calls") or 0) for i in ideas)
    return f"{compose}·{review}·-"


def _sources_text(stats: dict[str, Any] | None) -> str:
    if not stats:
        return "-"
    parts = []
    for name, s in stats.items():
        sec = s.get("seconds_avg")
        rate = s.get("failure_rate")
        parts.append(f"{name} {_dash(sec, '{:.1f}')}s·실패 {_dash(rate, '{:.0%}')}")
    return "<br>".join(parts)


def eval_compare_lines(results: list[dict[str, Any]]) -> list[str]:
    """[5] 통합 비교표 — 결과 JSON 마다 한 줄. 예전 JSON(기준선)에 없는 항목은 "-".

    유효율은 valid 가 없으면 ideas − invalid 로, Gemini 작성·검토는 아이디어별 기록으로 맞춘다."""
    lines = ["### [5] 통합 비교", ""]
    header = [
        "구성",
        "실행",
        "초안 1건: ② 까지(s)",
        "생성 완료까지(s)",
        "전체(s)",
        "유효율",
        "빈 초안",
        "최종 검토 점수",
        "수치 알림",
        "근거 불일치(검토/로컬)",
        "근거 중 실시간",
        "유사과제 적중",
        "자료원별 응답·실패율",
        "그림 성공률",
        "Gemini 작성·검토·그림",
        "HWPX",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for r in results:
        t = r.get("totals") or {}
        n = t.get("ideas")
        valid = t.get("valid")
        if valid is None and n is not None and t.get("invalid") is not None:
            valid = n - t["invalid"]
        known = t.get("precheck_known")
        mismatch = (
            f"{t['review_mismatch']}/{t.get('local_evidence_mismatch', 0)}"
            if "review_mismatch" in t
            else "-"
        )
        hwpx = f"{t.get('hwpx_ok', 0)}/{t['finalize_tried']}" if t.get("finalize_tried") else "-"
        cells = [
            str(r.get("label")),
            _mode_text(r),
            _dash(t.get("precheck_seconds_avg")),
            _dash(t.get("draft_seconds_avg")),
            _dash(t.get("seconds_avg")),
            _ratio(valid, n),
            _dash(t.get("empty_drafts")),
            _dash(t.get("final_score_avg"), "{:.2f}"),
            _dash(t.get("number_alerts")),
            mismatch,
            _ratio(t.get("live_cited"), t.get("cited_docs")),
            f"{t.get('precheck_hits', 0)}/{known}" if known else "-",
            _sources_text(t.get("live_sources")),
            _ratio(t.get("figures_nano"), t.get("figures_planned")),
            _gemini_split(r),
            hwpx,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    crit = [(r["label"], (r.get("totals") or {}).get("final_scores_avg")) for r in results]
    crit = [(label, c) for label, c in crit if c]
    if crit:
        lines.append(
            "최종 검토 기준별 평균: "
            + "; ".join(
                f"{label} " + " ".join(f"{k} {v:.2f}" for k, v in c.items()) for label, c in crit
            )
        )
        lines.append("")
    return lines


def _eval_idea_integrated_lines(results: list[dict[str, Any]]) -> list[str]:
    """[5] 아이디어별 — 새 항목이 하나라도 있는 결과만."""
    rows = [r for r in results if any("draft_seconds" in i for i in r.get("ideas") or [])]
    if not rows:
        return []
    lines = ["### 아이디어별 [5] 통합 측정", ""]
    lines.append(
        "| 구성 | 아이디어 | 묶음 | 상태(끝) | ②(s) | 생성(s) | 최종 검토(s) | 최종 점수 | "
        "빈 초안 | 수치 알림 | 근거 불일치(검토/로컬) | local_check(불일치/건너뜀) | "
        "실시간 인용 | 로컬 작성 | 그림(채택/계획) | HWPX·그림 배치 |"
    )
    lines.append("|" + "---|" * 16)
    for r in rows:
        for i in r.get("ideas") or []:
            scores = " ".join(f"{k[:2]}{v}" for k, v in (i.get("final_scores") or {}).items())
            if not scores and i.get("final_review_status"):
                scores = str(i["final_review_status"])
            if i.get("finalized") is None:
                hwpx = "-"
            elif i.get("finalized"):
                hwpx = f"{'✓' if i.get('hwpx_ok') else '✗'} 배치 {i.get('figure_placements') or 0}"
            else:
                hwpx = f"✗ {i.get('finalize_error') or ''}".strip()
            lc = "-"
            if i.get("local_check_mismatches") is not None:
                lc = f"{i['local_check_mismatches']}/{i.get('local_check_skipped') or 0}"
            cells = [
                str(r.get("label")),
                str(i.get("name")),
                _dash(i.get("batch")),
                f"{i.get('status')}→{i.get('final_status') or '-'}",
                _dash(i.get("precheck_seconds")),
                _dash(i.get("draft_seconds")),
                _dash(i.get("final_review_seconds")),
                scores or "-",
                "예" if i.get("empty_draft") else "-",
                str(i.get("number_alerts", 0)),
                f"{i.get('review_mismatch', 0)}/{i.get('local_evidence_mismatch', 0)}",
                lc,
                f"{i.get('live_cited', 0)}/{i.get('cited_docs', 0)}",
                ",".join(i.get("local_sections") or []) or "-",
                f"{i.get('figures_nano', 0)}/{i.get('figures_planned', 0)}",
                hwpx,
            ]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


_REGEN_REASON = {
    "fence": "응답 형식 오류",
    "json": "응답 형식 오류",
    "schema": "응답 형식 오류",
    "choices_only": "본문 없이 선택값만 옴",
    "empty": "빈 응답",
    "dropped": "근거 검증에서 모두 빠짐",
}


def regenerate_payload(result: Any, *, titles: dict[str, str] | None = None) -> dict[str, Any]:
    """항목 17 다시 쓰기 결과 (본문 없음 — 새 버전은 version_payload 로)."""
    from rra.domain.rules.request_change import change_summary

    names = titles or {}
    return {
        "mode": result.mode,
        "fields": change_summary(result.fields),
        "regenerated": [{"key": k, "title": names.get(k, k)} for k in result.regenerated],
        "failed": [
            {
                "key": f["key"],
                "title": names.get(f["key"], f["key"]),
                "reason_label": _REGEN_REASON.get(f.get("reason", ""), "모델 호출 실패"),
            }
            for f in result.failed
        ],
        "kept": [{"key": k, "title": names.get(k, k)} for k in result.kept],
        "saved_only": bool(result.saved_only),
    }


def content_disposition(filename: str, fallback: str) -> str:
    """내려받기 헤더 — RFC 6266/5987: ASCII 대체 이름 + UTF-8 퍼센트 인코딩 이름(한글 제목)."""
    from urllib.parse import quote

    ascii_name = "".join(ch for ch in fallback if 32 < ord(ch) < 127 and ch not in '"\\;')
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
