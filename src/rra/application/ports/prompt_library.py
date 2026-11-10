from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PromptLibraryPort(Protocol):
    """프롬프트 텍스트 공급자.

    프롬프트는 코드가 아니라 자산이므로 파일로 두고, 유스케이스는 이 포트로만 읽는다.
    (application 이 adapters 를 import 하지 않도록 하는 유일한 통로)
    """

    def system(self) -> str:
        """공통 시스템 프롬프트. A: <doc> 구획 무시 규칙과 JSON 강제를 포함한다."""
        ...

    def section(self, key: str) -> str:
        """섹션별 작성 지시. 미정의 키는 예외."""
        ...

    def review(self) -> str:
        """검토(Argon) 시스템 프롬프트 — 새 사실 추가 금지·근거 안에서만·한국어·JSON 객체."""
        ...

    def differentiate(self) -> str:
        """유사과제 활용·차별화 제안 시스템 프롬프트 — 자료·입력 안에서만, JSON 객체."""
        ...

    def recommend(self) -> str:
        """차별화 과제 추천 시스템 프롬프트 — 추천 0~5건 또는 사유, 자료 안에서만, JSON 객체."""
        ...

    def recommend_novel(self) -> str:
        """새 과제 추천(novel 갈래, ADR 0057) 시스템 프롬프트 — 접근 방식이 다른 안 2~3건, 장벽
        5갈래 점검·장벽 해소형 과제명, 근거 있음/추정, 자료·입력 안에서만, JSON 객체."""
        ...

    def outline(self) -> str:
        """Q2 섹션 설계도 시스템 프롬프트 — 섹션별 핵심 메시지·근거 id·연결, JSON 객체."""
        ...

    def clarify(self) -> str:
        """Q1 입력 보강 질문 시스템 프롬프트 — 빠진 정보만 최대 3개, JSON 객체."""

    def structure(self) -> str:
        """U2 간편 입력 시스템 프롬프트 — 자유 문장 → 필수 4칸, 없는 칸은 빈 값, JSON 객체."""
        ...

    def figures(self) -> str:
        """[G] 그림 명세(JSON) 작성 지시 — 본문·입력·근거에 있는 글자·수치만."""
        ...

    def figure_edit(self) -> str:
        """[G][2] 말로 고치기 — 요청을 명세 변경 {spec, style, summary} 로 바꾸는 지시."""
        ...

    def figure_techniques(self) -> str:
        """[11] 분석 기법 고르기(0~2)·분석(TechniqueSpec) 지시 — 본문·입력·근거 안에서만,
        등급은 예비 평가."""
        ...

    def brief(self) -> str:
        """U5 선행연구 브리핑 시스템 프롬프트 — 구획별 한 줄 요약·연구 공백 후보, JSON 객체."""
        ...

    def diagnose(self) -> str:
        """문제 정의 카드 진단(ADR 0065) 시스템 프롬프트 — 항목 나누기·기능 문장·사다리·문제어·
        모순·근본 원인·분류 후보·문제 성격·신호, 근거 없으면 빈 값, JSON 객체 하나."""
        ...

    def analogy_group(self) -> str:
        """비슷한 유추 자료 묶음의 비교 분석(계약 problem-card.md 4.6절) 시스템 프롬프트 — 자료마다
        핵심 방식·다른 점·활용할 점·한계, 묶음의 공통 접근·빈 부분. 초록에 있는 내용만, JSON 하나."""
        ...
