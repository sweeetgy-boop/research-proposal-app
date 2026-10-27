"""가짜 NTIS 부가 조회(성과검색·연관콘텐츠) — ProjectOutcomePort·RelatedProjectPort 의 결정적 구현.

가짜 모드(RRA_FAKE_LLM=1) 전용. 네트워크·키 없음. ② 화면 e2e 가 "주요 성과(참고용)"·"NTIS 추천"
블록을 지나가도록 어떤 과제번호에도 같은 더미를 돌려준다 (실 어댑터
adapters/sources/ntis/insights.py 와 모양 같음).
"""

from __future__ import annotations

from typing import Any


class ScriptedNtisInsights:
    async def outcomes(self, project_no: str) -> list[dict[str, Any]]:
        return [
            {
                "kind": "paper",
                "title": "궤도 틀림 진행 예측 모델 (가짜)",
                "year": "2024",
                "venue": "한국철도학회논문집 (가짜)",
                "result_id": "PAP-FAKE-1",
            },
            {
                "kind": "patent",
                "title": "검측 이력 기반 보수 우선순위 산정 장치 (가짜)",
                "year": "2023",
                "venue": "특허청 (가짜)",
                "registration_no": "10-0000000",
            },
        ]

    async def related(self, project_no: str) -> list[dict[str, Any]]:
        return [
            {
                "project_no": "fake-rel-1",
                "title": "궤도 보수 자동화 연관 과제 (가짜)",
                "score": 0.91,
                "rank": 1,
            },
            {
                "project_no": "fake-rel-2",
                "title": "검측 데이터 통합 플랫폼 (가짜)",
                "score": 0.84,
                "rank": 2,
            },
        ]
