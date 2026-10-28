"""U7 제출 전 점검 — 체크리스트 한 장. 렌더를 막지 않는다 (알림만). 순수 함수.

항목마다 target(섹션 키 / 문장 id / 경로 힌트)을 붙여 화면이 바로 이동할 수 있게 한다.
- required_sections: 필수 섹션이 모두 채워졌는가 (lint missing 오류)
- failed_sections: 로컬 작성이 실패해 빈칸인 섹션 (ADR 0027, "다시 생성" 으로 채운다)
- unresolved_alerts: 미해결 알림 수 (코드별 건수)
- evidence_approval: 근거 승인 비율 (U1 판단, 대상 근거 수 대비 approve)
- open_memos: 남은 Argon 메모 (open annotations)
- stale_edits: 최종 검토 이후 수정 건수
- choices_confirmed: 선택형 확정 여부 (과제유형·활용계획·전략)
- field_limits: 칸 길이 초과 (render_check overflow)
- strategy_source: 전략체계 목록이 임시(draft)인가
- figures_unconfirmed: [G] 제안자가 아직 [확인함] 하지 않은 그림 수 (제안서에 넣는 그림만)
- figures_source: [G] 출처 캡션이 없는 수치 그래프
- figures_mismatch: [G] 1차 검토가 "본문과 그림이 어긋남" 으로 지적한 그림(열린 의견)
- figures_undecided: [11] 추천 그림 중 [넣기 확정]·[필요 없음]을 고르지 않은 것 (그대로 두면
  제안서에 들어간다)
- review_state: 최종 검토 완료 또는 검토 건너뜀(마무리 가능)인가
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models import DraftVersion, Figure, RunState
from rra.domain.models.review import sentence_id
from rra.domain.rules import review_flow
from rra.domain.rules.lint import LintRules

STRATEGY_KEY = "strategy_alignment"


@dataclass(frozen=True)
class CheckItem:
    key: str
    label: str
    ok: bool
    detail: str = ""
    count: int = 0
    target: str | None = None  # "section:<key>" | "sentence:<sid>" | "route:<hint>"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubmitCheck:
    items: list[CheckItem]

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items)

    @property
    def failing(self) -> list[CheckItem]:
        return [i for i in self.items if not i.ok]


def submit_check(
    *,
    state: RunState,
    version: DraftVersion | None,
    problems: Sequence[Mapping[str, Any]],
    rules: LintRules,
    confirmed: Mapping[str, list[str]],
    overflow: Sequence[Any],
    evidence_counts: Mapping[str, int],
    strategy_source: str = "confirmed",
    strategy_options: int = 0,
    figures: Sequence[Figure] = (),
    figure_comments: int = 0,
) -> SubmitCheck:
    items: list[CheckItem] = []
    sections = {s.key: s for s in (version.sections if version else [])}

    missing = [k for k in rules.required_sections if k not in sections or not sections[k].sentences]
    skipped = {
        p["section"]
        for p in problems
        if p["code"] in ("input_missing", "catalog_empty", "no_relevant_evidence")
    }
    missing = [k for k in missing if k not in skipped]
    items.append(
        CheckItem(
            "required_sections",
            "필수 섹션",
            not missing,
            "빈 섹션: " + ", ".join(rules.titles.get(k, k) for k in missing)
            if missing
            else "모두 채워짐",
            len(missing),
            f"section:{missing[0]}" if missing else None,
            {"missing": missing},
        )
    )

    failed = list(getattr(state, "failed_sections", None) or [])
    items.append(
        CheckItem(
            "failed_sections",
            "생성 실패 섹션",
            not failed,
            "다시 생성 필요: " + ", ".join(rules.titles.get(f.key, f.key) for f in failed)
            if failed
            else "없음",
            len(failed),
            f"section:{failed[0].key}" if failed else None,
            {"failed": [{"key": f.key, "reason": f.reason} for f in failed]},
        )
    )

    by_code: dict[str, int] = {}
    first_target: str | None = None
    for p in problems:
        by_code[p["code"]] = by_code.get(p["code"], 0) + 1
        if first_target is None:
            idx = p.get("sentence")
            first_target = (
                f"sentence:{sentence_id(p['section'], idx)}"
                if idx is not None
                else f"section:{p['section']}"
            )
    total = sum(by_code.values())
    items.append(
        CheckItem(
            "unresolved_alerts",
            "미해결 알림",
            total == 0,
            ", ".join(f"{c} {n}건" for c, n in sorted(by_code.items())) if total else "없음",
            total,
            first_target,
            {"by_code": by_code},
        )
    )

    ev_total = int(evidence_counts.get("total", 0))
    approved = int(evidence_counts.get("approve", 0))
    rate = round(approved / ev_total, 3) if ev_total else None
    items.append(
        CheckItem(
            "evidence_approval",
            "근거 승인 비율",
            ev_total == 0 or approved == ev_total,
            f"승인 {approved}/{ev_total}" if ev_total else "판단할 근거 없음",
            ev_total - approved if ev_total else 0,
            "route:evidence" if ev_total and approved < ev_total else None,
            {"rate": rate, **{k: int(v) for k, v in evidence_counts.items()}},
        )
    )

    open_memos = [a for a in (version.annotations if version else []) if a.status == "open"]
    first_memo = open_memos[0] if open_memos else None
    items.append(
        CheckItem(
            "open_memos",
            "남은 검토 메모",
            not open_memos,
            f"{len(open_memos)}건" if open_memos else "없음",
            len(open_memos),
            None
            if first_memo is None
            else (
                f"sentence:{sentence_id(first_memo.section, first_memo.sentence)}"
                if first_memo.sentence is not None
                else f"section:{first_memo.section}"
            ),
        )
    )

    items.append(
        CheckItem(
            "stale_edits",
            "최종 검토 이후 수정",
            not state.stale,
            f"{state.stale_edits}건 — 다시 받기는 선택" if state.stale else "없음",
            state.stale_edits if state.stale else 0,
            "route:final-review" if state.stale else None,
        )
    )

    unconfirmed = [k for k in rules.choices if not confirmed.get(k)]
    items.append(
        CheckItem(
            "choices_confirmed",
            "선택형 확정",
            not unconfirmed,
            "미확정: " + ", ".join(rules.titles.get(k, k) for k in unconfirmed)
            if unconfirmed
            else "확정됨",
            len(unconfirmed),
            f"section:{unconfirmed[0]}" if unconfirmed else None,
            {"unconfirmed": unconfirmed},
        )
    )

    rows = [{"slot": o.slot, "chars": o.chars, "limit": o.limit, "kind": o.kind} for o in overflow]
    items.append(
        CheckItem(
            "field_limits",
            "칸 길이",
            not rows,
            ", ".join(f"{r['slot']} {r['chars']}>{r['limit']}" for r in rows)
            if rows
            else "초과 없음",
            len(rows),
            f"section:{rows[0]['slot']}"
            if rows and rows[0]["kind"] == "section"
            else ("route:finalize" if rows else None),
            {"overflow": rows},
        )
    )

    if STRATEGY_KEY in rules.choices:
        draft_list = strategy_source != "confirmed"
        items.append(
            CheckItem(
                "strategy_source",
                "전략체계 목록",
                not draft_list and strategy_options > 0,
                "임시 목록 사용 중 — 확정 목록으로 바꿀 것"
                if draft_list
                else ("목록 비어 있음 (2-가-(3) 빈칸)" if strategy_options == 0 else "확정 목록"),
                1 if (draft_list or strategy_options == 0) else 0,
                f"section:{STRATEGY_KEY}" if (draft_list or strategy_options == 0) else None,
                {"source": strategy_source, "options": strategy_options},
            )
        )

    included = [f for f in figures if f.included]
    if figures:
        pending = [f for f in included if not f.confirmed]
        items.append(
            CheckItem(
                "figures_unconfirmed",
                "확인 전 그림",
                not pending,
                f"확인 전 그림 {len(pending)}개 — 카드에서 숫자·글자를 원문과 확인한 뒤 [확인함]"
                if pending
                else (f"그림 {len(included)}개 모두 확인됨" if included else "넣은 그림 없음"),
                len(pending),
                f"section:{pending[0].section}" if pending else None,
                {"figures": [f.id for f in pending], "included": len(included)},
            )
        )
        undecided = [f for f in figures if f.undecided]
        if undecided or any(f.recommendation is not None for f in figures):
            items.append(
                CheckItem(
                    "figures_undecided",
                    "결정 전 추천 그림",
                    not undecided,
                    f"추천 그림 {len(undecided)}개 — [넣기 확정] 또는 [필요 없음]을 고르십시오. "
                    "그대로 마무리하면 제안서에 들어갑니다."
                    if undecided
                    else "추천 그림 모두 결정함",
                    len(undecided),
                    f"section:{undecided[0].section}" if undecided else None,
                    {"figures": [f.id for f in undecided]},
                )
            )
        no_source = [f for f in included if f.kind == "stat_chart" and not f.source_caption]
        items.append(
            CheckItem(
                "figures_source",
                "그래프 출처 표시",
                not no_source,
                f"출처 캡션 없음 {len(no_source)}개" if no_source else "모두 표시됨",
                len(no_source),
                f"section:{no_source[0].section}" if no_source else None,
                {"figures": [f.id for f in no_source]},
            )
        )
        items.append(
            CheckItem(
                "figures_mismatch",
                "본문과 그림 일치",
                figure_comments == 0,
                f"검토 지적 {figure_comments}건 — 그림을 고치거나 메모를 처리"
                if figure_comments
                else "지적 없음",
                figure_comments,
                f"section:{included[0].section}" if figure_comments and included else None,
            )
        )

    can = review_flow.can_finalize(
        state.status, final_reviewed=state.final_reviews > 0, review_skipped=state.review_skipped
    )
    items.append(
        CheckItem(
            "review_state",
            "검토 상태",
            can,
            "마무리 가능" if can else f"{state.status} — 최종 검토 완료(또는 건너뜀) 뒤 마무리",
            0 if can else 1,
            None if can else "route:final-review",
            {
                "status": state.status,
                "final_reviews": state.final_reviews,
                "review_skipped": state.review_skipped,
            },
        )
    )
    return SubmitCheck(items=items)
