"""Q3 섹션별 맞춤 검색 질의 — 섹션마다 제안 입력의 관련 칸(+ 설계도 핵심 메시지)으로 질의를 만든다.

전체 검색(retrieve)은 네 칸을 합친 질의 하나로 k 개를 고르므로 기대효과·활용계획 같은 섹션의 근거가
빈약하다. 섹션 질의는 저장소 질의 상한(query_max_chars)에 맞춰 자른다. 순수 함수.
"""

from __future__ import annotations

from collections.abc import Iterable

from rra.domain.models import ProposalRequest
from rra.domain.models.outline import Outline

# 섹션 → 질의에 넣을 제안 입력 칸 (순서대로 이어 붙인다)
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "tech_importance": ("title_hint", "limitation", "root_cause", "current_state"),
    "objective": ("title_hint", "goal", "limitation"),
    "method": ("title_hint", "goal", "constraints"),
    "expected_management": ("title_hint", "goal", "beneficiaries", "current_state"),
    "expected_technology": ("title_hint", "goal", "limitation"),
    "expected_standing": ("title_hint", "goal"),
    "utilization": ("title_hint", "goal", "beneficiaries"),
}
DEFAULT_MAX_CHARS = 500


def section_queries(
    req: ProposalRequest,
    keys: Iterable[str],
    outline: Outline | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, str]:
    """{섹션 키: 질의}. 질의가 될 칸이 모두 비면 그 섹션은 뺀다(전체 근거를 쓴다)."""
    out: dict[str, str] = {}
    for key in keys:
        fields = SECTION_FIELDS.get(key)
        if not fields:
            continue
        parts: list[str] = []
        plan = outline.plan(key) if outline is not None else None
        if plan is not None and plan.message:
            parts.append(plan.message)
        for name in fields:
            value = getattr(req, name, "")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        query = " ".join(dict.fromkeys(parts))[:max_chars].strip()
        if query:
            out[key] = query
    return out
