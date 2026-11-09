"""유사과제 4축 분해 (ADR 0059, 계약 docs/contracts/overlap-facets.md) — 0단계 계약 모델.

아이디어·과제를 target(대상)·problem(문제)·method(방법)·place(장소) 네 축으로 나눈다. 축 값은
짧은 문자열이고 비어도 된다(분해 실패·해당 없음). `FacetOverlap` 은 두 글 사이의 축별 겹침 —
0(다름)·1(부분)·2(같음).

- 분해 결과는 비신뢰(로컬 모델 출력, 보안 A) — 길이 상한·한 줄만. 어떤 축도 차단을 바꾸지 않는다
  (ADR 0059: 차단 규칙 변경은 평가 결과 뒤 결정). 기능 스위치 `config/overlap.yaml`
  `facets.enabled` 가 false 면 어디서도 만들지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

FACET_KEYS: tuple[str, ...] = ("target", "problem", "method", "place")
FACET_LABELS: dict[str, str] = {
    "target": "대상",
    "problem": "문제",
    "method": "방법",
    "place": "장소",
}
MAX_FACET_CHARS = 80

FacetLevel = Literal[0, 1, 2]  # 0 다름 · 1 부분 · 2 같음


def _one_line(value: str) -> str:
    text = " ".join(str(value).split())
    return text[:MAX_FACET_CHARS]


class Facets(BaseModel):
    """4축 값 — 각 문자열, 비어도 됨. `source` 는 누가 나눴는지(local 모델 | rule 규칙 |
    none 미분해)."""

    model_config = ConfigDict(frozen=True)

    target: str = ""
    problem: str = ""
    method: str = ""
    place: str = ""
    source: Literal["local", "rule", "none"] = "none"

    @field_validator("target", "problem", "method", "place", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        return _one_line(v) if isinstance(v, str) else ""

    def is_empty(self) -> bool:
        return not any(getattr(self, k) for k in FACET_KEYS)

    def as_dict(self) -> dict[str, str]:
        return {k: getattr(self, k) for k in FACET_KEYS}


class FacetOverlap(BaseModel):
    """두 글의 축별 겹침 {축: 0|1|2}. 없는 축은 0. 판정 출력(Argon `facet_overlap`)이나 규칙이
    채운다."""

    model_config = ConfigDict(frozen=True)

    target: FacetLevel = 0
    problem: FacetLevel = 0
    method: FacetLevel = 0
    place: FacetLevel = 0

    @classmethod
    def from_mapping(cls, raw: object) -> FacetOverlap:
        """비신뢰 매핑 → 모델. 모르는 키·범위 밖 값은 0 으로(폐기하지 않는다 — 판정 보조값일 뿐)."""
        if not isinstance(raw, dict):
            return cls()
        values: dict[str, int] = {}
        for key in FACET_KEYS:
            v = raw.get(key)
            if isinstance(v, bool):
                v = int(v)
            if isinstance(v, (int, float)) and int(v) in (0, 1, 2):
                values[key] = int(v)
        return cls(**values)  # type: ignore[arg-type]

    def total(self) -> int:
        return sum(getattr(self, k) for k in FACET_KEYS)

    def all_high(self) -> bool:
        """네 축 모두 2 — 차단 기준 후보(ADR 0059, 평가 뒤 결정). 지금은 표시만."""
        return all(getattr(self, k) == 2 for k in FACET_KEYS)

    def as_dict(self) -> dict[str, int]:
        return {k: getattr(self, k) for k in FACET_KEYS}
