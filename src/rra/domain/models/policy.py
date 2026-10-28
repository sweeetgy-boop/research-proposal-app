"""정책 근거 추천 — ① 입력 뒤 정책(policy) 문서에서 고른 문구 3~5개.

제안자가 고른 것만 policy_basis 로 들어간다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_QUOTE = 300
MAX_SUGGESTIONS = 5
MIN_SUGGESTIONS = 3


class PolicySuggestion(BaseModel):
    """정책 문서의 문구 하나. quote 는 문서에 있는 그대로(비신뢰 텍스트)."""

    doc_id: str
    title: str = Field(max_length=300)
    year: int | None = None
    page: str | None = Field(default=None, max_length=120)  # 표·장 제목 또는 쪽 — 모르면 None
    quote: str = Field(max_length=MAX_QUOTE)
    url: str | None = None
    menu_path: str | None = Field(default=None, max_length=200)
    keywords: list[str] = Field(default_factory=list)  # 질의와 겹친 키워드
    similarity: float | None = None


# ── 정책적 중요도 작성안 (보강 질문 단계, 2026-10-28 레인 B) ─────────────────
# 정책 근거가 없을 때 수집된 정책 자료(국토부·공사 전략·감사 지적·정부 R&D 공고)에서 아이디어와
# 관련된 원문 구간을 찾아 최대 4개 안(방향마다 하나, 근거 겹침 없음)을 보인다. 안의 본문은 인용한
# 구간 안에서만 쓴다(domain/rules/policy_cards). 제안자가 고른 안(PolicyChoice)만 run 에 들어간다.
MAX_POLICY_CARDS = 4
MAX_CARD_SENTENCES = 3
MAX_CARD_SENTENCE_CHARS = 300
MAX_CHOICE_SENTENCES = 6

PolicyDirection = Literal["government", "company", "audit", "regional"]
PolicyChoiceMode = Literal["card", "merged", "edited", "manual", "none"]


class PolicySource(BaseModel):
    """작성안이 인용한 원문 구간 하나 — 문서명·연도·쪽·원문 인용·링크. quote 는 문서 그대로."""

    chunk_id: str = Field(max_length=200)
    doc_id: str = Field(max_length=200)
    source: str = Field(default="", max_length=40)
    source_label: str = Field(default="", max_length=60)
    title: str = Field(default="", max_length=300)
    year: int | None = None
    page: str | None = Field(default=None, max_length=120)
    quote: str = Field(max_length=MAX_QUOTE)
    url: str | None = Field(default=None, max_length=500)


class PolicySentence(BaseModel):
    text: str = Field(max_length=MAX_CARD_SENTENCE_CHARS)
    evidence: list[str] = Field(default_factory=list, max_length=4)  # 이 안의 sources chunk_id


class PolicyCard(BaseModel):
    """정책적 중요도 작성안 하나 (방향 하나, 2~3개 "○" 문장, 인용 구간 안에서만)."""

    id: str = Field(max_length=40)
    direction: PolicyDirection
    direction_label: str = Field(max_length=40)
    sentences: list[PolicySentence] = Field(default_factory=list, max_length=MAX_CARD_SENTENCES)
    sources: list[PolicySource] = Field(default_factory=list, max_length=4)


class PolicyChoice(BaseModel):
    """제안자가 정한 정책 근거 — run 의 2-가-(1) 정책적 중요도가 이것으로 쓰인다.

    mode: card(안 하나) | merged(두 안 합침) | edited(고른 뒤 직접 수정·AI 다듬기) | manual(직접
    작성)
    | none(정책 근거 없음으로 진행 → 빈칸 대신 "정책 근거 확인 필요" 알림, 제출 전 점검에서 다시
    표시).
    sentences 의 evidence 는 sources 의 chunk_id 만 — 생성 때 저장소에서 원문과 대조해 통과한 것만
    근거로 남는다(보안 A).
    """

    mode: PolicyChoiceMode
    card_ids: list[str] = Field(default_factory=list, max_length=2)
    sentences: list[PolicySentence] = Field(default_factory=list, max_length=MAX_CHOICE_SENTENCES)
    sources: list[PolicySource] = Field(default_factory=list, max_length=8)

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.sentences if s.text.strip())

    @property
    def evidence_ids(self) -> list[str]:
        out: list[str] = []
        for s in self.sentences:
            out.extend(e for e in s.evidence if e not in out)
        return out
