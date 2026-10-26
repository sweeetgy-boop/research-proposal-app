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
                        "text": clean(sent.text),
                        "evidence": sent.evidence,
                        "source": _source(sent),
                    }
                    for sent in sec.sentences
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
        # [5] 검토·버전 요약 (의견 본문은 review_payload 로)
        "version": getattr(view, "version", 1),
        "versions": list(getattr(view, "versions", []) or []),
        "review": review_summary(state, getattr(view, "review", None)),
    }


def review_summary(state: Any, latest: Any) -> dict[str, Any]:
    return {
        "rounds": state.review_rounds,
        "skipped": state.review_skipped,
        "error": state.review_error,
        "model": state.review_model,
        "latest_round": latest.round if latest else None,
        "latest_status": latest.status if latest else None,
        "open_comments": len(latest.open_comments) if latest else 0,
        "finalized_at": state.finalized_at,
    }


def review_payload(review: Any, *, clean: Callable[[str], str] = _same) -> dict[str, Any]:
    """ReviewRound → dict. 의견·수정안은 외부 LLM 출력(비신뢰 텍스트) — clean 을 거친다."""
    return {
        "round": review.round,
        "draft_version": review.draft_version,
        "status": review.status,
        "skipped_reason": review.skipped_reason,
        "created_at": review.created_at,
        "excluded_sentences": list(review.excluded_sentences),
        "resolved_ids": list(review.resolved_ids),
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
        "created_at": version.created_at,
        "based_on_review": version.based_on_review,
        "reverted_from": version.reverted_from,
        "note": version.note,
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
    """버전 목록 — 본문 없이 메타만."""
    return [
        {
            "version": v.version,
            "origin": v.origin,
            "created_at": v.created_at,
            "based_on_review": v.based_on_review,
            "reverted_from": v.reverted_from,
            "note": v.note,
            "sentences": sum(len(s.sentences) for s in v.sections),
        }
        for v in versions
    ]


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
