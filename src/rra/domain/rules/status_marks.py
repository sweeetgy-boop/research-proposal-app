"""상태 표시는 버전을 만들지 않는다 (항목 21, ADR 0042) — 순수 함수.

- 상태 표시: 그림 [확인함], 추천 그림 [넣기 확정]·[필요 없음]·[다시 넣기], 근거 승인·제외, 선택형
확정,
  로컬 검토 제안 [무시]. 현재 버전의 표시 파일(VersionMarks)에 쌓고 버전 번호는 그대로다.
- 내용 변경(새 버전): [새 버전으로 저장], AI 다시 쓰기 반영, 그림 다시 그리기·말로 고치기·글자
고치기·
  기본 그림·기법 바꾸기·추가·빼기, 근거 교체, 로컬 검토 제안 [반영], 복원, 입력 변경 다시 쓰기.
- apply_marks: 버전 + 표시 → 화면·점검·마무리가 보는 버전. 표시한 뒤 그림이 바뀌었으면(image_sha
다름)
  그 그림의 표시는 적용하지 않는다.
- status_only_marks: 예전 run 에서 그림 확인 등으로 만들어진 "상태만 바뀐 버전" 을 찾는다(지우지
않고
  버전 목록에서 "확인 기록" 으로 접는다).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from rra.domain.models import DraftVersion, EvidenceDecision, Figure
from rra.domain.models.marks import MARK_LABELS, FigureMark, StatusMark, VersionMarks
from rra.domain.rules.evidence import decisions_for_sections
from rra.domain.rules.figures import figure_diff
from rra.domain.rules.versions import same_content

# 그림 카드 동작 중 상태 표시인 것 → 확인 기록 종류
FIGURE_MARK_ACTIONS: dict[str, str] = {
    "confirm": "figure_confirm",
    "accept": "figure_accept",
    "dismiss": "figure_dismiss",
    "restore": "figure_restore",
}
# figure_diff 의 change 중 상태 표시인 것 → 확인 기록 종류
_STATUS_FIGURE_CHANGES: dict[str, str] = {
    "confirmed": "figure_confirm",
    "accepted": "figure_accept",
    "dismissed": "figure_dismiss",
    "restored": "figure_restore",
}
EVIDENCE_MARK_ACTIONS = frozenset({"approve", "exclude"})


def is_figure_mark(action: str) -> bool:
    return action in FIGURE_MARK_ACTIONS


def is_evidence_mark(decisions: Iterable[EvidenceDecision]) -> bool:
    """근거 판단 요청이 상태 표시만인가 (교체가 하나라도 있으면 본문 근거 id 가 바뀐다 → 새
    버전)."""
    items = list(decisions)
    return bool(items) and all(d.action in EVIDENCE_MARK_ACTIONS for d in items)


def _fresh(marks: VersionMarks | None, version: int) -> VersionMarks:
    if marks is None or marks.version != version:
        return VersionMarks(version=version)
    return marks


def apply_marks(version: DraftVersion, marks: VersionMarks | None) -> DraftVersion:
    """버전 + 그 버전의 표시. 표시가 없으면 버전 그대로(같은 객체)."""
    if marks is None or marks.empty or marks.version != version.version:
        return version
    figures: list[Figure] = []
    for fig in version.figures:
        m = marks.figures.get(fig.id)
        if m is None or m.image_sha != fig.image_sha:
            figures.append(fig)
            continue
        update: dict = {}
        if m.confirmed is not None:
            update["confirmed"] = m.confirmed
        if m.included is not None:
            update["included"] = m.included
        if m.recommendation_status is not None and fig.recommendation is not None:
            update["recommendation"] = fig.recommendation.model_copy(
                update={"status": m.recommendation_status, "at": m.recommendation_at}
            )
        figures.append(fig.model_copy(update=update) if update else fig)
    decisions = (
        version.evidence_decisions
        if marks.evidence_decisions is None
        else decisions_for_sections(version.sections, marks.evidence_decisions)
    )
    return version.model_copy(update={"figures": figures, "evidence_decisions": decisions})


def add_log(
    marks: VersionMarks | None,
    version: int,
    kind: str,
    *,
    target: str = "",
    label: str = "",
    at: str | None = None,
) -> VersionMarks:
    out = _fresh(marks, version)
    log = [*out.log, StatusMark(kind=kind, target=target, label=label, at=at)][-500:]  # type: ignore[arg-type]
    return out.model_copy(update={"log": log, "updated_at": at})


def mark_figure(
    marks: VersionMarks | None,
    version: int,
    figure: Figure,
    action: str,
    *,
    label: str = "",
    at: str | None = None,
) -> VersionMarks:
    """그림 상태 표시 — figure 는 표시를 반영한 뒤의 그림(confirmed·included·recommendation)."""
    kind = FIGURE_MARK_ACTIONS[action]
    out = _fresh(marks, version)
    rec = figure.recommendation
    entry = FigureMark(
        image_sha=figure.image_sha,
        confirmed=figure.confirmed,
        included=figure.included,
        recommendation_status=rec.status if rec is not None else None,
        recommendation_at=rec.at if rec is not None else None,
    )
    figures = {**out.figures, figure.id: entry}
    out = out.model_copy(update={"figures": figures})
    return add_log(out, version, kind, target=figure.id, label=label, at=at)


def mark_evidence(
    marks: VersionMarks | None,
    version: int,
    merged: Sequence[EvidenceDecision],
    changed: Sequence[EvidenceDecision],
    *,
    at: str | None = None,
) -> VersionMarks:
    """근거 승인·제외 — merged 는 누적 판단 전체, changed 는 이번에 새로 바뀐 판단(기록용)."""
    out = _fresh(marks, version).model_copy(update={"evidence_decisions": list(merged)})
    for d in changed:
        out = add_log(out, version, f"evidence_{d.action}", target=d.sentence_id, at=at)
    return out


def new_decisions(
    before: Iterable[EvidenceDecision], after: Iterable[EvidenceDecision]
) -> list[EvidenceDecision]:
    old = {(d.sentence_id, d.evidence_id, d.action) for d in before}
    return [d for d in after if (d.sentence_id, d.evidence_id, d.action) not in old]


def carry_figure_marks(target: Sequence[Figure], current: Sequence[Figure]) -> list[Figure]:
    """복원 — 되돌린 버전의 그림 중 지금 그림과 같은 것(id·그림·명세가 같음)은 지금의 상태 표시를
    이어받는다(복원했다고 이미 한 확인이 풀리지 않게)."""
    now = {f.id: f for f in current}
    out: list[Figure] = []
    for fig in target:
        cur = now.get(fig.id)
        if (
            cur is not None
            and cur.image_sha == fig.image_sha
            and cur.spec.model_dump() == fig.spec.model_dump()
        ):
            fig = fig.model_copy(
                update={
                    "confirmed": cur.confirmed,
                    "included": cur.included,
                    "recommendation": cur.recommendation,
                }
            )
        out.append(fig)
    return out


def status_only_marks(previous: DraftVersion, version: DraftVersion) -> list[StatusMark] | None:
    """예전 run 의 "상태만 바뀐 버전" — 본문·메모가 이전 버전과 같고 그림·근거 판단의 상태 표시만
    다르면 그 표시 목록, 아니면 None (내용이 바뀌었거나 아무것도 안 바뀐 버전)."""
    if version.origin != "edit":
        return None
    if not same_content(previous.sections, version.sections):
        return None
    if [a.model_dump() for a in previous.annotations] != [
        a.model_dump() for a in version.annotations
    ]:
        return None
    out: list[StatusMark] = []
    for row in figure_diff(previous.figures, version.figures):
        kind = _STATUS_FIGURE_CHANGES.get(row["change"])
        if kind is None:
            return None
        out.append(StatusMark(kind=kind, target=row["figure_id"], at=version.created_at))  # type: ignore[arg-type]
    for d in new_decisions(previous.evidence_decisions, version.evidence_decisions):
        if d.action not in EVIDENCE_MARK_ACTIONS:
            return None
        out.append(
            StatusMark(kind=f"evidence_{d.action}", target=d.sentence_id, at=version.created_at)  # type: ignore[arg-type]
        )
    return out or None


def mark_label(mark: StatusMark, figure_names: Mapping[str, str] | None = None) -> str:
    """확인 기록 한 줄의 화면 문구 — "그림 확인 — 분석 기법 그림 – SWOT 분석" (내부 id 는 쓰지
    않는다)."""
    base = MARK_LABELS.get(mark.kind, "확인")
    name = mark.label or (figure_names or {}).get(mark.target, "")
    return f"{base} — {name}" if name else base


def count_marks(marks: Iterable[StatusMark]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in marks:
        out[m.kind] = out.get(m.kind, 0) + 1
    return out
