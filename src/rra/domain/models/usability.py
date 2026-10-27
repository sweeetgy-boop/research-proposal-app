"""사용자 관점 검토 반영(U1~U8) 설정 — config/usability.yaml. 항목마다 켜고 끈다 (기본 켬).

- evidence_view      U1 근거 원문 바로보기 (GET …/sentences/{sid}/evidence)
- evidence_support   U1 Argon 1차 검토에 문장별 근거 적합성(support) 판정을 함께 요청
- evidence_decisions U1 제안자 근거 판단(approve·replace·exclude) 저장
- quick_input        U2 간편 입력 — 자유 문장 → 필수 4칸 구조화 + 보완 질문
- section_rewrite    U3 섹션별 AI 다시 쓰기
- section_questions  U3 섹션 체크리스트 기반 보완 질문
- comparison         U4 차별성 비교표
- brief              U5 선행연구 브리핑
- schedule_metrics   U6 연구기간이 있으면 추진일정(개월)·성과지표 지시 + 일정 초과 알림
- submit_check       U7 제출 전 점검
- usage_record       U8 run 별 usage.json 기록
- feedback           U8 마무리 뒤 만족도 기록
- strategy_source    전략체계 목록의 출처 상태: confirmed(확정) | draft(임시) — U7 점검 항목
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class UsabilityConfig(BaseModel):
    evidence_view: bool = True
    evidence_support: bool = True
    evidence_decisions: bool = True
    quick_input: bool = True
    section_rewrite: bool = True
    section_questions: bool = True
    comparison: bool = True
    brief: bool = True
    schedule_metrics: bool = True
    submit_check: bool = True
    usage_record: bool = True
    feedback: bool = True
    strategy_source: Literal["confirmed", "draft"] = "confirmed"

    def enabled(self) -> list[str]:
        return [k for k, v in self.model_dump().items() if v is True]
