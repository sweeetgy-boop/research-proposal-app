"""버전 목록의 설명 — 실제로 바뀐 섹션·그림, 확인 기록, 작성자 배지 (항목 21, ADR 0042). 순수 함수.

- 바뀐 섹션은 이전 버전과의 실제 차이(문장·선택값)로만 센다. 그림만 바뀐 버전은 "바뀐 섹션" 이 없고
  "바뀐 그림" 에 그림 이름이 나온다(예전 run 은 그림의 섹션을 changed_sections 에 넣었다).
- 예전 run 의 상태만 바뀐 버전(그림 확인 등)은 status_only=True — 화면이 "확인 기록" 으로 접는다.
- 메모 "그림 confirm" 같은 내부 동작 이름은 한국어로 바꾼다("그림 확인 — 연구 개념도").
- 그림 이름: 레인 C 의 Figure.display_name 이 있으면 그것, 없으면 종류·기법 이름으로 만든다
  (figure_name — 레인 C 병합 뒤에는 display_name 이 우선한다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models import DraftVersion, Figure
from rra.domain.models.figure import KIND_LABEL
from rra.domain.models.marks import StatusMark, VersionMarks
from rra.domain.rules.figures import figure_diff
from rra.domain.rules.status_marks import mark_label, status_only_marks
from rra.domain.rules.versions import changed_sections

# 그림 카드 동작(메모 "그림 <동작>") → 화면 문구
FIGURE_ACTION_LABELS: dict[str, str] = {
    "confirm": "그림 확인",
    "accept": "추천 그림 넣기 확정",
    "dismiss": "추천 그림 필요 없음",
    "restore": "추천 그림 다시 넣기",
    "include": "그림 다시 넣기",
    "exclude": "그림 빼기",
    "words": "그림 말로 고치기",
    "texts": "그림 글자 고치기",
    "baseline": "기본 그림으로 되돌리기",
    "regenerate": "그림 다시 그리기",
    "swap": "분석 기법 바꾸기",
}
# figure_diff change → 화면 문구 (바뀐 그림 줄)
FIGURE_CHANGE_LABELS: dict[str, str] = {
    "added": "추가",
    "removed": "삭제",
    "redrawn": "다시 그림",
    "texts": "내용 고침",
    "included": "다시 넣음",
    "excluded": "뺌",
    "baseline": "기본 그림으로",
    "swapped": "기법 바꿈",
    "accepted": "넣기 확정",
    "dismissed": "필요 없음",
    "restored": "다시 넣음",
    "confirmed": "확인",
}
_STATUS_CHANGES = frozenset({"confirmed", "accepted", "dismissed", "restored"})
# 화면에 영어를 내보내지 않는다 — 종류 이름 중 영어가 섞인 것은 한국어로
_KIND_NAMES: dict[str, str] = {
    **KIND_LABEL,
    "comparison": "차별성 비교표",
    "as_is_to_be": "현재·개선 비교 그림",
}


def figure_name(figure: Figure, technique_labels: Mapping[str, str] | None = None) -> str:
    """그림 이름 — "분석 기법 그림 – SWOT 분석", "연구 개념도". display_name(레인 C)이 있으면
    그것."""
    shown = getattr(figure, "display_name", None)
    if isinstance(shown, str) and shown.strip():
        return shown.strip()
    if figure.kind == "technique":
        key = str(getattr(figure.spec, "technique", "") or "")
        label = (technique_labels or {}).get(key) or str(getattr(figure.spec, "title", "") or "")
        return f"분석 기법 그림 – {label}" if label else "분석 기법 그림"
    return _KIND_NAMES.get(figure.kind, "그림")


def figure_names(
    versions: Sequence[DraftVersion], technique_labels: Mapping[str, str] | None = None
) -> dict[str, str]:
    """모든 버전의 그림 id → 이름 (나중 버전 이름이 이긴다)."""
    out: dict[str, str] = {}
    for v in versions:
        for f in v.figures:
            out[f.id] = figure_name(f, technique_labels)
    return out


def note_label(note: str, names: Sequence[str] = ()) -> str:
    """저장 메모의 화면 문구. "그림 confirm" → "그림 확인 — 연구 개념도". 제안자 메모는 그대로."""
    text = (note or "").strip()
    if text.startswith("그림 "):
        action = text[3:].split(" ", 1)[0]
        label = FIGURE_ACTION_LABELS.get(action)
        if label is not None:
            return f"{label} — {', '.join(names)}" if names else label
    return text


def writer_label(writer: str | None, local_sections: int = 0) -> str | None:
    """v1 배지 — 실제 작성자. Argon 이 쓰고 일부 섹션이 로컬로 넘어갔으면 "Argon 작성(일부
    로컬)"."""
    if writer == "gemini":
        return "Argon 작성(일부 로컬)" if local_sections > 0 else "Argon 작성"
    if writer == "local":
        return "로컬 작성"
    return None


@dataclass(frozen=True)
class VersionRow:
    version: int
    status_only: bool = False  # 예전 run 의 상태만 바뀐 버전 → "확인 기록" 으로 접는다
    changed_sections: list[str] = field(default_factory=list)  # 실제 차이로 센 섹션
    changed_figures: list[str] = field(default_factory=list)  # "연구 개념도 다시 그림"
    marks: list[str] = field(default_factory=list)  # 확인 기록 문구 (이 버전에 쌓인 표시)
    description: str = ""
    origin_label: str | None = None  # v1 작성자 배지 (없으면 화면이 origin_label 을 쓴다)

    def dump(self) -> dict[str, Any]:
        return {
            "status_only": self.status_only,
            "changed_sections": list(self.changed_sections),
            "changed_figures": list(self.changed_figures),
            "marks": list(self.marks),
            "confirmations": len(self.marks),
            "description": self.description,
        }


def version_rows(
    versions: Sequence[DraftVersion],
    marks: Mapping[int, VersionMarks] | None = None,
    *,
    technique_labels: Mapping[str, str] | None = None,
    writer: str | None = None,
    local_sections: int = 0,
) -> list[VersionRow]:
    """버전마다 설명 줄. versions 는 번호 순(버전 파일 그대로 — 표시를 합치지 않은 것)."""
    ordered = sorted(versions, key=lambda v: v.version)
    names = figure_names(ordered, technique_labels)
    rows: list[VersionRow] = []
    prev: DraftVersion | None = None
    for v in ordered:
        own_marks: list[StatusMark] = list(
            (marks or {}).get(v.version, VersionMarks(version=v.version)).log
        )
        legacy = status_only_marks(prev, v) if prev is not None else None
        if prev is None:
            sections = []  # 첫 버전 — "바뀐 섹션" 대신 "초안 작성"
            fig_rows: list[dict[str, Any]] = []
        else:
            sections = changed_sections(prev.sections, v.sections)
            fig_rows = figure_diff(prev.figures, v.figures)
        content_figs = [r for r in fig_rows if r["change"] not in _STATUS_CHANGES]
        changed_figs = [
            f"{names.get(r['figure_id'], '그림')} {FIGURE_CHANGE_LABELS.get(r['change'], '바뀜')}"
            for r in content_figs
        ]
        all_marks = [*(legacy or []), *own_marks]
        mark_lines = [mark_label(m, names) for m in all_marks]
        touched = list(dict.fromkeys(names.get(r["figure_id"], "그림") for r in fig_rows))
        desc = note_label(v.note, touched)
        if prev is None and not desc:
            desc = "초안 작성"
        rows.append(
            VersionRow(
                version=v.version,
                status_only=legacy is not None,
                changed_sections=[] if legacy is not None else sections,
                changed_figures=[] if legacy is not None else changed_figs,
                marks=mark_lines,
                description=desc,
                origin_label=writer_label(writer, local_sections)
                if (v.version == 1 and v.origin == "local")
                else None,
            )
        )
        prev = v
    return rows
