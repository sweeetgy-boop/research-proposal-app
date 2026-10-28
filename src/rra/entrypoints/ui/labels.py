"""표시용 문자열 — 한글 라벨과 비신뢰 텍스트 정리. 로직 없음."""

from __future__ import annotations

import re

TIER = {
    "own": "사내(철도연구원)",
    "national_rnd": "국가R&D 과제",
    "domestic_rail": "국내 철도기관",
    "external": "외부",
    "procurement": "발주 용역",
}
OWN_DETAIL = {"institute": "사내(철도연구원)", "company": "사내(공사)"}


def tier_text(tier: str, own_detail: str | None = None) -> str:
    if tier == "own":
        return OWN_DETAIL.get(own_detail or "institute", TIER["own"])
    return TIER.get(tier, tier)


BASIS = {
    "summary": "공개 요약",
    "abstract": "초록·과제요약",
    "full_text": "원문",
    "image_vision": "이미지 판독",  # 웹 이미지 OCR 대조 + Argon 판독 — 원본 링크는 raw.image.url
}
PROBLEM = {
    "missing": "필수 섹션 비어 있음",
    "too_long": "분량 초과",
    "no_evidence": "근거 없음",
    "evidence_forbidden": "입력만 근거로 써야 함",
    "unsupported_number": "입력·근거에 없는 수치",
    "input_missing": "근거 입력 없음 — 빈칸",
    "policy_basis_needed": "정책 근거 확인 필요",
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
    "procuring": "용역으로 진행 중/예정",  # 발주 용역 공고 (P2-6)
}
STATUS = {
    "queued": "대기",
    "running": "생성 중 (로컬 작성)",
    "interrupted": "중단됨 (재개 가능)",
    "failed": "실패",
    "invalid": "완료 (규칙 위반 있음)",
    "draft_reviewing": "Argon 1차 검토 중",
    "drafted": "초안 완료",
    "editing": "수정 중",
    "final_reviewing": "Argon 최종 검토 중",
    "final_reviewed": "최종 검토 완료",
    "finalized": "마무리됨",
    # 옛 이름 (저장된 run)
    "done": "초안 완료",
    "reviewing": "검토 중",
    "reviewed": "초안 완료",
}
ORIGIN = {
    "llm": "로컬 작성",
    "app": "앱 확정",
    "input": "제안자 입력",
    "argon": "Argon 보완",
    "argon_addition": "Argon 추가",
    "reviewed": "최종 검토 반영",
    "proposer_edit": "제안자 수정",
    "proposer_input": "제안자 추가",
    "proposer": "제안자 수정",
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
