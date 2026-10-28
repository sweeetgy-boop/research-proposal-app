"""초안이 있는 run 에서 ①·② 입력을 바꿨을 때 — 바뀐 칸 → 다시 써야 할 섹션 (항목 17). 순수 규칙.

화면은 저장할 때 세 가지를 묻는다:
- 보기만 하고 돌아가기 — 아무것도 저장하지 않는다.
- 바뀐 내용과 관련된 섹션만 다시 쓰기(mode=sections) — 새 버전. 그 섹션의 제안자 수정·입력 문장
  (proposer_edit·proposer_input)과 앱 문장(app)은 그대로 두고 나머지만 다시 쓴다 (U3 다시 쓰기와
  같은 규칙). 관련 없는 섹션은 손대지 않는다.
- 초안 전체 다시 생성(mode=all) — 새 버전. 모든 본문 섹션을 새로 쓴다 (제안자 수정 문장도 새로
  쓴다). 기존 초안은 이전 버전으로 남아 [버전·비교]에서 보고 복원할 수 있다.

근거 자료(검색 집합)는 다시 검색하지 않는다 — 처음 검색한 집합 안에서만 쓴다 (보안 A: 문장의 근거
id 는 이 run 의 검색 집합과 대조). 우선 근거(②에서 고른 자료)는 그 집합 안의 것만 앞세운다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

RegenMode = Literal["sections", "all"]

# 문제 정의 4칸·보충 정보는 거의 모든 섹션의 근거라 바뀌면 본문 전체가 관련 섹션이다
CORE_FIELDS: frozenset[str] = frozenset(
    {"current_state", "root_cause", "limitation", "goal", "supplement"}
)
ALL_BODY = "*"

# 입력 칸 → 그 칸을 읽는 섹션 (adapters/llm/prompts/section_*.md·system.md 기준)
FIELD_SECTIONS: dict[str, tuple[str, ...]] = {
    "current_state": (ALL_BODY,),
    "root_cause": (ALL_BODY,),
    "limitation": (ALL_BODY,),
    "goal": (ALL_BODY,),
    "supplement": (ALL_BODY,),
    "title_hint": ("title",),
    "constraints": ("method", "utilization"),
    "policy_basis": ("policy_importance", "strategy_alignment"),
    "beneficiaries": (
        "expected_management",
        "expected_technology",
        "expected_standing",
        "utilization",
    ),
    "remarks": ("overlap_review",),
    "differentiation": ("objective", "method", "overlap_review"),
    # ② 유사과제 확인에서 고른 우선 근거 — 근거를 쓰는 섹션 전부
    "priority_evidence": ("@evidence",),
    # 양식 칸에만 들어가는 값 — 다시 쓸 섹션 없음 (마무리 때 그대로 반영)
    "department": (),
    "budget": (),
}
FIELD_LABELS: dict[str, str] = {
    "current_state": "현재 상황",
    "root_cause": "발생 원인",
    "limitation": "현행 대응의 한계",
    "goal": "해결 목표",
    "supplement": "보충 정보",
    "title_hint": "가제",
    "constraints": "제약 조건",
    "policy_basis": "정책 근거",
    "beneficiaries": "활용 부서",
    "remarks": "특이사항 메모",
    "differentiation": "차별화 방향",
    "priority_evidence": "우선 근거(유사과제 확인)",
    "department": "제안부서",
    "budget": "소요예산",
}
MODE_NOTES: dict[str, str] = {
    "sections": "입력 변경 — 관련 섹션 다시 쓰기",
    "all": "입력 변경 — 초안 전체 다시 생성",
}


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, Mapping):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_norm(v) for v in value]
    return value


def changed_fields(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    old_priority: Sequence[str] = (),
    new_priority: Sequence[str] | None = None,
) -> list[str]:
    """바뀐 입력 칸 이름 (FIELD_SECTIONS 순서). 공백만 다른 것은 같다고 본다.
    new_priority 가 None 이면 우선 근거는 비교하지 않는다."""
    out = [
        f
        for f in FIELD_SECTIONS
        if f != "priority_evidence" and _norm(old.get(f)) != _norm(new.get(f))
    ]
    if new_priority is not None and list(dict.fromkeys(old_priority)) != list(
        dict.fromkeys(new_priority)
    ):
        out.append("priority_evidence")
    return out


def affected_sections(
    fields: Iterable[str],
    section_keys: Sequence[str],
    *,
    evidence_sections: Iterable[str] = (),
) -> list[str]:
    """바뀐 칸 → 다시 쓸 섹션 (양식 순서). 선택형 섹션은 제안값만 새로 나오고 확정값은 그대로다."""
    wanted: set[str] = set()
    for f in fields:
        for target in FIELD_SECTIONS.get(f, ()):
            if target == ALL_BODY:
                wanted |= set(section_keys)
            elif target == "@evidence":
                wanted |= set(evidence_sections)
            elif target in section_keys:
                wanted.add(target)
    return [k for k in section_keys if k in wanted]


def regen_targets(
    mode: RegenMode, affected: Sequence[str], section_keys: Sequence[str]
) -> list[str]:
    """mode=sections 면 관련 섹션만, all 이면 모든 섹션."""
    return list(affected) if mode == "sections" else list(section_keys)


def preserves_proposer(mode: RegenMode) -> bool:
    """제안자가 고친·적은 문장을 그 자리에 두는가 — 관련 섹션만 다시 쓸 때만."""
    return mode == "sections"


def change_summary(fields: Iterable[str]) -> list[dict[str, str]]:
    return [{"field": f, "label": FIELD_LABELS.get(f, f)} for f in fields]
