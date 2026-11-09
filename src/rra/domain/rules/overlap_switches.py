"""유사과제 고도화 1단계 기능 스위치 (ADR 0059, 계약 docs/contracts/overlap-facets.md §1).

`config/overlap.yaml` 의 세 절 `facets`·`idf_weighting`·`synonyms` 의 `enabled` 값. 기본 모두 false
—
false 면 ② 결과는 스위치 도입 전과 같다(회귀 시험 `tests/application/test_overlap_switch_off.py`).
읽기는 `config_loader.load_overlap_switches`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OverlapSwitches(BaseModel):
    model_config = ConfigDict(frozen=True)

    facets: bool = False  # 4축 분해 → 축별 질의 RRF 합침 + 판정 출력 facet_overlap
    idf_weighting: bool = False  # 핵심어 겹침에 말뭉치 IDF 가중
    synonyms: bool = False  # 동의어 확장 (사람 검토 뒤에만)

    @property
    def any_on(self) -> bool:
        return self.facets or self.idf_weighting or self.synonyms


OFF = OverlapSwitches()
