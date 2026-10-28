"""② 유사과제 화면 문구 — 내부 코드를 화면에 보이지 않게 한국어 문구로 (2026-10-28 레인 A)."""

from __future__ import annotations

JUDGED_BY_LABELS: dict[str, str] = {"argon": "Argon", "local": "로컬 모델", "rule": "규칙"}

_JUDGMENT_MESSAGES: dict[str, str] = {
    "ai:argon": "Argon 이 대상·문제·방법이 실제로 같은지 판정했습니다 — '같다' 만 차단합니다.",
    "ai:local": "Argon 판정에 실패해 로컬 모델이 판정했습니다 — '같다' 만 차단합니다.",
    "rule_fallback": "AI 판정 실패 — 규칙 기준",
    "off": "AI 판정 꺼짐 — 규칙 기준(점수·핵심 키워드)",
    "no_candidates": "판정할 유사과제 후보가 없습니다.",
}

_DIFF_SKIPS: dict[str, str] = {
    "no_similar_selected": (
        "유사함으로 고른 과제가 없어 활용 제안은 건너뜁니다. "
        "아래 차별화 과제안이 아이디어와 관련 연구로 방향을 제안합니다."
    ),
    "no_candidates": "차단·근접 유사과제가 없어 건너뛰었습니다.",
    "no_documents": "비교할 과제 문서를 읽지 못했습니다.",
    "parse_failed": "AI 응답을 해석하지 못했습니다 — 다시 시도하십시오.",
}

_REC_SKIPS: dict[str, str] = {
    "no_alerts_or_evidence": "비교할 과제·근거 자료가 없어 건너뛰었습니다.",
    "no_documents": "비교할 과제 문서를 읽지 못했습니다.",
    "parse_failed": "AI 응답을 해석하지 못했습니다 — 다시 시도하십시오.",
    "llm_failed": "AI 호출에 실패했습니다 — 다시 시도하십시오.",
}


def judgment_message(status: str, judged_by: str | None) -> str:
    key = f"{status}:{judged_by}" if status == "ai" else status
    return _JUDGMENT_MESSAGES.get(key, _JUDGMENT_MESSAGES["off"])


def differentiation_skip_label(reason: str | None) -> str | None:
    if not reason:
        return None
    return _DIFF_SKIPS.get(reason, "제안을 만들지 못했습니다 — 다시 시도하십시오.")


def recommendation_skip_label(reason: str | None) -> str | None:
    if not reason:
        return None
    return _REC_SKIPS.get(reason, "과제안을 만들지 못했습니다 — 다시 시도하십시오.")


def extraction_label(extraction: str, by: str | None) -> str:
    if extraction == "ai":
        who = JUDGED_BY_LABELS.get(by or "", "AI")
        return f"기존 과제 칸은 {who} 가 요약·초록 원문에서 뽑은 문장입니다(원문 밖 내용 없음)."
    return "기존 과제 칸은 요약·초록의 머리말 아래 문장입니다(AI 추출 실패 또는 꺼짐 — 규칙 기준)."


GATE_BLOCKING = (
    "차단 경보를 확인해 주세요 — 각 행에서 [유사함]·[관련 없음] 을 고르거나 확인란에 표시하십시오."
)
RELEASED_NOTE = "차단 과제를 모두 [관련 없음] 으로 골라 차단 경보를 풀었습니다."
