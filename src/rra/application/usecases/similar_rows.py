"""② [유사함] 행 — 모든 진입점(REST·CLI·MCP·Streamlit)이 쓰는 한 규칙 (ADR 0054).

행이 [유사함] 인지는 제안자 선택이 정하고, 선택이 없는 행은 AI 같음 판정의 기본 선택을 따른다
(같다·일부 겹침 → [유사함], 다르다 → [관련 없음]). 선택도 AI 판정도 없는 행(규칙 판정·AI 실패·판정
전)은 [유사함] 이 아니다. 규칙 자체는 순수 함수 `domain/rules/similar_choice.effective_choice` 이고,
여기는 유스케이스·진입점이 함께 부르는 얇은 입구다:

- similar_rows / similar_count / no_similar: 비교표 [유사함] 열·활용 제안 대상·'새 영역' 다시 받기
  조건·② 화면 "유사함 n건"·/v1/precheck stage=full 의 활용 제안 실행 조건.
- basis_rows: 과제안(차별화 과제 추천)의 비교 대상 행 (precheck_levels.basis_alerts).
- default_choice_list: 화면이 선택 없는 행에 미리 고를 선택 ([유사함]·[관련 없음]).
- differentiation_rows: 활용·차별화 제안 대상. 선택 화면이 없는 진입점(CLI·MCP·Streamlit,
  `fallback`)은 AI 판정도 선택도 없을 때만 종전 후보 규칙(차단 또는 임계치×0.9)을 쓴다.

차단 게이트(effective_blocking)는 이 규칙을 쓰지 않는다 — 차단 행을 모두 제안자가 [관련 없음] 으로
골라야만 풀린다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from rra.domain.models import OverlapAlert
from rra.domain.rules.precheck_levels import basis_alerts, default_choices
from rra.domain.rules.similar_choice import effective_choice, effective_similar

Choices = Mapping[str, str]


def similar_rows(alerts: Sequence[OverlapAlert], choices: Choices) -> list[OverlapAlert]:
    """유효 선택이 [유사함] 인 행 (순서 유지)."""
    return effective_similar(alerts, choices)


def similar_count(alerts: Sequence[OverlapAlert], choices: Choices) -> int:
    """② "유사함 n건" — 행(같은 제목·연작은 한 행) 수."""
    return len(similar_rows(alerts, choices))


def no_similar(alerts: Sequence[OverlapAlert], choices: Choices) -> bool:
    """[유사함] 0건 — '새 영역' 다시 받기 조건 (ADR 0053)."""
    return not similar_rows(alerts, choices)


def basis_rows(alerts: Sequence[OverlapAlert], choices: Choices) -> list[OverlapAlert]:
    """과제안 비교 대상 — [유사함] 행이 있으면 그것만, 없으면 유효 [관련 없음] 이 아닌 행."""
    return basis_alerts(alerts, choices)


def default_choice_list(alerts: Sequence[OverlapAlert]) -> list[dict[str, str]]:
    """화면이 선택 없는 행에 미리 고를 선택 — [{doc_id, choice}]."""
    return [{"doc_id": d, "choice": c} for d, c in default_choices(alerts).items()]


def differentiation_rows(
    alerts: Sequence[OverlapAlert],
    choices: Choices,
    limit: int,
    *,
    fallback: Callable[[Sequence[OverlapAlert]], list[OverlapAlert]] | None = None,
) -> list[OverlapAlert]:
    """활용·차별화 제안 대상 — [유사함] 행. fallback 이 있고(선택 화면 없는 진입점) 어느 행에도
    유효 선택이 없으면(AI 판정 없음·제안자 선택 없음) fallback 후보."""
    rows = similar_rows(alerts, choices)
    if rows or fallback is None:
        return rows[:limit]
    if any(effective_choice(a, choices) is not None for a in alerts):
        return []
    return fallback(alerts)[:limit]
