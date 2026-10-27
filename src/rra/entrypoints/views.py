"""진입점 공용 직렬화. RunManager.DraftView → 출력용 dict (CLI·MCP 가 같은 모양을 쓴다).

현행 근거 규칙: 근거 필수 섹션 밖에서는 제안자 입력만으로 쓴 문장이 허용된다.
그런 문장은 evidence 가 비어 있고 source="proposer_input" 으로 구분해 보여 준다.
앱이 규칙으로 만든 확정 문장(유사과제 없음 등)은 source="app".

선택형 섹션(과제유형·활용계획·전략)은 choices 에 LLM 제안(proposed)과 사용자 확정(confirmed)을
따로 싣는다. 확정 전이면 confirmed 는 null.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rra.domain.models.review import ORIGIN_LABEL
from rra.domain.rules.overlap import tier_label


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
        "citations": [
            {"id": c.id, "doc_id": c.doc_id, "title": clean(c.title) if c.title else None}
            for c in view.citations
        ],
        "problems": [
            {
                "section": p["section"],
                "code": p["code"],
                "severity": p.get("severity", "error"),
                "message": clean(p["message"]),
                "sentence": p.get("sentence"),
            }
            for p in state.problems
        ],
        # 검토·버전 요약 (의견 본문은 review_payload 로)
        "version": getattr(view, "version", 1),
        "versions": list(getattr(view, "versions", []) or []),
        "review": review_summary(state, getattr(view, "review", None)),
        "flow": flow_summary(state, getattr(view, "has_working", False)),
    }


def flow_summary(state: Any, has_working: bool = False) -> dict[str, Any]:
    """전체 흐름 ③~⑥ 의 현재 위치 — 화면 stepper·배너용."""
    return {
        "status": state.status,
        "draft_review_skipped": getattr(state, "draft_review_skipped", None),
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


def review_payload(review: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """ReviewRound → dict. 의견·수정안은 외부 LLM 출력(비신뢰 텍스트) — clean 을 거친다."""
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
            k: {kk: clean(str(vv)) for kk, vv in v.items()}
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
                "reason": clean(s.reason),
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
                "comment": clean(c.comment),
                "revised_text": clean(c.revised_text) if c.revised_text else None,
                "evidence": list(c.evidence),
                "status": c.status,
                "usable": c.usable,
                "discard_reason": c.discard_reason,
            }
            for c in review.comments
        ],
    }


def version_payload(version: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    return {
        "version": version.version,
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


def versions_payload(versions: list[Any]) -> list[dict[str, Any]]:
    """버전 목록 — 본문 없이 메타만(번호·시각·경로·메모·바뀐 섹션·문장 수·알림 수·남은 메모 수)."""
    return [
        {
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
        }
        for v in versions
    ]


def diff_payload(from_v: Any, to_v: Any, diff: list[dict], *, clean: Callable[[str], str] = _same):
    """두 버전의 차이 — 섹션마다 added/removed/moved 문장."""

    def rows(items):
        return [
            {**x, **{k: clean(v) for k, v in x.items() if k in ("text", "from", "to")}}
            for x in items
        ]

    return {
        "from": from_v.version,
        "to": to_v.version,
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
                "severity": p.severity,
                "message": clean(p.message),
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


def alerts_payload(alerts: list[Any], *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """유사과제 경보 목록 → 출력용 dict (MCP·REST 공용). 제목은 수집 문서에서 온 비신뢰 텍스트."""
    return {
        "blocking": any(a.blocking for a in alerts),
        "alerts": [
            {
                "doc_id": a.doc_id,
                "title": clean(a.title),
                "tier": a.tier,
                "similarity": round(a.similarity, 4),
                "blocking": a.blocking,
                "basis": a.basis,
                "keywords": list(a.keywords),
                "status": a.status,
                "own_detail": a.own_detail,
                "tier_label": tier_label(a.tier, a.own_detail),
            }
            for a in alerts
        ],
    }


def differentiation_payload(
    proposal: Any, *, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """DifferentiationProposal → dict (CLI·MCP·REST 공용). 항목 본문은 LLM 출력(비신뢰) → clean."""
    return {
        "skipped_reason": proposal.skipped_reason,
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
                "title": clean(i.title),
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


def recommendations_payload(result: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """RecommendationResult → dict (CLI·MCP·REST 공용). 본문은 LLM 출력(비신뢰) → clean."""
    return {
        "skipped_reason": result.skipped_reason,
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
                "reasons": [clean(x) for x in r.reasons],
                "build_on": clean(r.build_on),
                "risks": clean(r.risks),
                "compared_with": list(r.compared_with),
                "evidence": list(r.evidence),
                "overlap_warning": list(r.overlap_warning),
            }
            for i, r in enumerate(result.recommendations)
        ],
        "discarded": [{k: clean(str(v)) for k, v in d.items()} for d in result.discarded],
    }


def recommendation_preview_payload(
    before: Any, after: Any, preview: Any, *, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """추천 적용 미리보기 — 바뀐 칸과 전/후 값. 사용자가 고쳐 확정한 입력으로 초안을 만든다."""
    fields = ("title_hint", "goal", "differentiation")
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
    items: list[Any], *, clean: Callable[[str], str] = _same
) -> list[dict[str, Any]]:
    """EvidenceItem → dict. 발췌·제목은 수집 자료(비신뢰)."""
    return [
        {
            "evidence_id": i.evidence_id,
            "doc_id": i.doc_id,
            "chunk_id": i.chunk_id,
            "text": clean(i.text),
            "title": clean(i.title) if i.title else None,
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
    }


def submit_check_payload(
    check: Any, *, titles: dict[str, str] | None = None, clean: Callable[[str], str] = _same
) -> dict[str, Any]:
    """SubmitCheck → dict. 항목마다 target(section:<key> | sentence:<sid> | route:<hint>)."""
    names = titles or {}
    return {
        "ok": check.ok,
        "failing": len(check.failing),
        "items": [
            {
                "key": i.key,
                "label": i.label,
                "ok": i.ok,
                "detail": clean(i.detail),
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
    return {
        "run_id": record.run_id,
        "step_seconds": dict(record.step_seconds),
        "total_seconds": record.total_seconds,
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
            "title": clean(c.title),
            "tier": c.tier,
            "similarity": c.similarity,
            "blocking": c.blocking,
            "basis": c.basis,
            "title_only": c.title_only,
            "cells": {k: clean(v) for k, v in c.cells.items()},
        }

    return {
        "aspects": list(table.aspects),
        "proposal": col(table.proposal),
        "projects": [col(c) for c in table.projects],
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


def run_state_payload(state: Any, *, legacy: bool = False) -> dict[str, Any]:
    """RunState → 상태 조회 응답 (초안 본문 없음)."""
    done, total = state.progress
    return {
        "run_id": state.run_id,
        "status": state.status,
        "progress": [done, total],
        "template": state.template,
        "legacy": legacy,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "steps": [{"name": s.name, "status": s.status, "error": s.error} for s in state.steps],
        "draft_version": state.draft_version,
        "flow": flow_summary(state),
    }


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
        "| 구성 | 아이디어 | 상태 | v1 알림 | v2 알림 | 문장 v1→v2 | 무관 인용 | 점수 | "
        "반영(수정+추가) | 충족률 | 후보 | precheck | 시간(s) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        for i in r.get("ideas") or []:
            scores = " ".join(f"{k[:2]}{v}" for k, v in (i.get("scores") or {}).items()) or "-"
            cands = ",".join(f"{k}:{v}" for k, v in (i.get("candidates") or {}).items()) or "-"
            pre = f"{i.get('precheck_alerts', 0)}건"
            if i.get("precheck_hit") is not None:
                pre += " ✓" if i["precheck_hit"] else " ✗"
            lines.append(
                f"| {r['label']} | {i['name']} | {i.get('status')} | {i.get('v1_alerts')} | "
                f"{num(i.get('v2_alerts'))} | {i.get('sentences_v1')}→{i.get('sentences_v2')} | "
                f"{i.get('irrelevant_citations')} | {scores} | "
                f"{i.get('applied')}+{i.get('additions_applied')} | "
                f"{num(i.get('checklist_coverage'))} | {cands} | {pre} | {i.get('seconds')} |"
            )
    lines.append("")
    return "\n".join(lines)
