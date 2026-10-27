"""③ 초안 생성 파이프라인 단계 설정 (config/pipeline.yaml) — 단계마다 켜고 끈다 (ADR 0013).

[E] 는 뼈대와 단계 연결(로컬 작성 → 규칙 검사 → v1 → Argon 1차 검토 → v2)만 만들고, 품질 단계
(clarify·outline·section_search·exemplars·additions·two_candidates·reranker)는 [Q] 에서 채운다.
기본값은 측정 뒤 효과가 확인된 것만 켠다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineConfig(BaseModel):
    clarify: bool = False  # Q1 입력 보강 질문 (초안 생성 전, 최대 3개)
    outline: bool = False  # Q2 섹션 설계도
    section_search: bool = False  # Q3 섹션별 맞춤 검색
    exemplars: bool = False  # Q4 채택 과제 본보기
    rule_check: bool = True  # Q6 규칙 검사·자동 정리 (Argon 전)
    draft_review: bool = True  # ③ Argon 1차 검토 → 검증 통과분 자동 반영 → v2 (키 없으면 v1)
    additions: bool = False  # Q5 Argon 보완 작성(빠진 요소 추가 문장)
    two_candidates: bool = False  # Q7 핵심 섹션 두 후보 → 1차 검토에서 선택
    reranker: bool = (
        True  # Q8 cross-encoder reranker (2026-10-27 측정 뒤 기본 켬; 모델 없으면 생략)
    )
    draft_review_retries: int = Field(default=1, ge=0, le=3)  # 1차 검토 실패 시 재시도 횟수

    def enabled_steps(self) -> list[str]:
        return [k for k, v in self.model_dump().items() if v is True]
