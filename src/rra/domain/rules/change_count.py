"""④ 편집의 "변경 n건" — 마지막 검토 이후 바뀐 것을 종류별로 센다 (순수, 2026-10-28 레인 B).

예전에는 저장하지 않은 문장 편집만 세서, 그림 확인·근거 승인·선택값 확정·정책 근거 고르기·보완 메모
처럼 바로 저장되는 동작은 "변경 0건" 이었고 [새 버전으로 저장] 이 꺼졌다. 이제 기준 버전(마지막 최종
검토 버전, 없으면 초안 v1·v2 중 최신)과 현재 버전을 비교해 모든 종류를 센다. 저장하지 않은 편집은
화면이 더한다(web editModel.countChanges).

종류(CHANGE_LABELS): 문장 수정·삭제·추가, 선택값(제안값) 변경, 그림 추가·변경·확인·빼기·다시 넣기,
근거 승인·교체·제외, 선택형 확정, 정책 근거 선택, 보완 메모.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models import DraftVersion
from rra.domain.rules.versions import diff_versions

CHANGE_LABELS: dict[str, str] = {
    "sentence_edit": "문장 수정",
    "sentence_delete": "문장 삭제",
    "sentence_add": "문장 추가",
    "choice_value": "선택값 변경",
    "figure_add": "그림 추가",
    "figure_change": "그림 변경",
    "figure_confirm": "그림 확인",
    "figure_remove": "그림 빼기",
    "figure_include": "그림 다시 넣기",
    "figure_decision": "추천 그림 결정",
    "evidence_approve": "근거 승인",
    "evidence_replace": "근거 교체",
    "evidence_exclude": "근거 제외",
    "choice_confirm": "선택형 확정",
    "policy_choice": "정책 근거 선택",
    "memo": "보완 메모",
}
# 비교 기준 버전으로 보는 origin — 초안(로컬·Argon 작성). 최종 검토 뒤에는 그 버전이 기준
BASE_ORIGINS = frozenset({"local", "argon"})


@dataclass(frozen=True)
class ChangeSummary:
    base_version: int
    current_version: int
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def dump(self) -> dict[str, Any]:
        return {
            "base_version": self.base_version,
            "current_version": self.current_version,
            "total": self.total,
            "items": [
                {"type": k, "label": CHANGE_LABELS.get(k, k), "count": n}
                for k, n in self.counts.items()
                if n
            ],
        }


def base_version(versions: Sequence[DraftVersion], final_reviewed: int | None) -> DraftVersion:
    """비교 기준 — 마지막 최종 검토 버전, 없으면 초안(local·argon) 중 최신, 그것도 없으면
    첫 버전."""
    by_no = {v.version: v for v in versions}
    if final_reviewed is not None and final_reviewed in by_no:
        return by_no[final_reviewed]
    drafts = [v for v in versions if v.origin in BASE_ORIGINS]
    if drafts:
        return max(drafts, key=lambda v: v.version)
    return min(versions, key=lambda v: v.version)


def _figure_counts(old: DraftVersion, new: DraftVersion) -> dict[str, int]:
    out = {
        k: 0
        for k in (
            "figure_add",
            "figure_change",
            "figure_confirm",
            "figure_remove",
            "figure_include",
            "figure_decision",
        )
    }
    before = {f.id: f for f in old.figures}
    after = {f.id: f for f in new.figures}
    for fid, f in after.items():
        prev = before.get(fid)
        if prev is None:
            out["figure_add"] += 1
            continue
        a, b = prev.recommendation, f.recommendation
        if a is not None and b is not None and (a.status, a.technique) != (b.status, b.technique):
            # [11] 추천 그림 넣기 확정·필요 없음·다시 넣기·기법 바꾸기 — 하나의 "결정" 으로 센다
            out["figure_decision"] += 1
            continue
        if prev.included and not f.included:
            out["figure_remove"] += 1
        elif not prev.included and f.included:
            out["figure_include"] += 1
        if (
            prev.spec != f.spec
            or prev.image_sha != f.image_sha
            or prev.caption != f.caption
            or prev.renderer != f.renderer
        ):
            out["figure_change"] += 1
        elif f.confirmed and not prev.confirmed:
            out["figure_confirm"] += 1
    out["figure_remove"] += sum(1 for fid in before if fid not in after)
    return out


def _evidence_counts(old: DraftVersion, new: DraftVersion) -> dict[str, int]:
    out = {"evidence_approve": 0, "evidence_replace": 0, "evidence_exclude": 0}
    before = {(d.sentence_id, d.evidence_id, d.action) for d in old.evidence_decisions}
    for d in new.evidence_decisions:
        if (d.sentence_id, d.evidence_id, d.action) in before:
            continue
        key = f"evidence_{d.action}"
        if key in out:
            out[key] += 1
    return out


def count_changes(
    base: DraftVersion,
    current: DraftVersion,
    *,
    confirmed_after_base: bool = False,
    policy_after_base: bool = False,
    memo_sections: Iterable[str] = (),
) -> ChangeSummary:
    """기준 버전 → 현재 버전의 변경 종류별 건수. 바로 저장되는 기록(선택형 확정·정책 근거·보완
    메모)은
    기준 버전 이후에 바뀌었는지만 받는다."""
    counts: dict[str, int] = dict.fromkeys(CHANGE_LABELS, 0)
    for d in diff_versions(base, current):
        # 바뀐 문장은 "빠진 것 + 새로 생긴 것" 한 쌍으로 나온다 — 짝지은 만큼 수정, 나머지는
        # 삭제·추가
        removed, added = len(d.get("removed") or []), len(d.get("added") or [])
        edits = min(removed, added)
        counts["sentence_edit"] += edits
        counts["sentence_delete"] += removed - edits
        counts["sentence_add"] += added - edits
    old_choices = {s.key: list(s.choices) for s in base.sections}
    for s in current.sections:
        if s.key in old_choices and s.choices != old_choices[s.key]:
            counts["choice_value"] += 1
    counts.update(_figure_counts(base, current))
    counts.update(_evidence_counts(base, current))
    counts["choice_confirm"] = int(confirmed_after_base)
    counts["policy_choice"] = int(policy_after_base)
    counts["memo"] = len(set(memo_sections))
    return ChangeSummary(base.version, current.version, counts)


def after(stamp: str | None, base: DraftVersion) -> bool:
    """기록 시각이 기준 버전 이후인가 (ISO 문자열 비교 — 같은 형식·UTC)."""
    return bool(stamp) and (base.created_at is None or str(stamp) >= str(base.created_at))


def memo_sections_after(answers_at: Mapping[str, str] | None, base: DraftVersion) -> list[str]:
    return [k for k, at in (answers_at or {}).items() if after(at, base)]
