"""표시용 문자열 — 한글 라벨과 비신뢰 텍스트 정리. 로직 없음."""

from __future__ import annotations

import re

TIER = {"own": "사내(철도연구원)", "domestic_rail": "국내 철도기관", "external": "외부"}
BASIS = {"summary": "공개 요약", "abstract": "초록·과제요약", "full_text": "원문"}
PROBLEM = {
    "missing": "필수 섹션 비어 있음",
    "too_long": "분량 초과",
    "no_evidence": "근거 없음",
    "evidence_forbidden": "입력만 근거로 써야 함",
    "unsupported_number": "입력·근거에 없는 수치",
    "input_missing": "근거 입력 없음 — 빈칸",
    "catalog_empty": "선택지 목록 비어 있음 — 빈칸",
    "no_choice": "제안된 선택지 없음 — 직접 선택",
    "no_relevant_evidence": "관련도 하한을 넘는 근거 없음 — 빈칸",
}
STATUS_PROJECT = {  # 사내 과제 기록의 상태 (OverlapAlert.status)
    "completed": "완료",
    "ongoing": "진행중",
    "stopped": "중단",
    "rejected": "미채택 — 보완 재제안 검토",
    "proposed": "제안·검토 중",
}
STATUS = {
    "queued": "대기",
    "running": "생성 중",
    "interrupted": "중단됨 (재개 가능)",
    "failed": "실패",
    "invalid": "완료 (규칙 위반 있음)",
    "done": "완료",
}
SOURCE = {
    "app": "앱 확정 문장",
    "proposer_input": "제안자 입력 근거",
    "retrieved": "자료 인용",
}
SECTION_FALLBACK = {
    "title": "연구과제명",
    "task_type": "과제유형",
    "policy_importance": "정책적 중요도",
    "tech_importance": "기술적 중요도",
    "strategy_alignment": "경영전략 정합성",
    "objective": "연구목적",
    "method": "연구 방법 및 주요내용",
    "expected_management": "기대효과 (경영혁신)",
    "expected_technology": "기대효과 (기술혁신)",
    "expected_standing": "기대효과 (대외위상)",
    "utilization": "연구결과 활용계획",
    "overlap_review": "특이사항 (유사과제 검토)",
}

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MD = re.compile(r"([\\`*_{}\[\]()#+\-!<>|~])")


def clean(text: object, limit: int = 2000) -> str:
    """제어문자 제거 + 절단. 마크다운을 해석하지 않는 자리(표 셀·st.text)에 쓴다."""
    s = _CONTROL.sub(" ", str(text)).strip()
    return s if len(s) <= limit else s[:limit] + "…"


def plain(text: object, limit: int = 2000) -> str:
    """비신뢰 텍스트를 화면에 그대로 보이게 한다 — 제어문자 제거, 마크다운·링크 무력화, 절단."""
    return _MD.sub(r"\\\1", clean(text, limit))


def section_title(key: str, titles: dict[str, str]) -> str:
    return titles.get(key) or SECTION_FALLBACK.get(key) or key
