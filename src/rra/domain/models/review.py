"""검토(Argon) 차수·초안 버전 모델 — [5] 작성 → 검토 → 제안자 수정 → 재검토 → 최종 마무리.

- ReviewComment: 문장별 의견. revised_text 는 5-4 검증(grounding·numbers·정책명·foreign_script·
  evidence 범위)을 통과한 것만 남고, 실패하면 status=discarded 로 원문 유지(comment 는 그대로).
- ReviewRound: 차수(n) 결과 파일(review_rN.json). 외부 전송 범위(doc_id public/internal, 보낸 문장
  수)를 기록한다. 원문·개인정보는 담지 않는다 (의견·수정안은 LLM 출력 = 비신뢰 텍스트).
- DraftVersion: draft_v1 = 로컬 초안, 이후 편집·되돌리기마다 새 버전. 모든 버전 보존.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .draft import Section

IssueType = Literal[
    "근거 불일치", "수치", "논리", "일관성", "문장", "서식요건", "중복·차별화", "외국 문자"
]
ISSUE_TYPES: tuple[str, ...] = (
    "근거 불일치",
    "수치",
    "논리",
    "일관성",
    "문장",
    "서식요건",
    "중복·차별화",
    "외국 문자",
)
CommentStatus = Literal["open", "resolved", "discarded"]
# 심사 기준 채점 (P5) — 철도연구원 심사 관점 4개, 각 1~5점. 2점 이하는 관련 문장에 의견으로 연결
CRITERIA: tuple[str, ...] = ("필요성", "차별성", "실현가능성", "기대효과")
WEAK_SCORE = 2
# 기준 → 점수가 낮을 때 의견을 붙일 기본 섹션(문장 id 가 없을 때)·issue_type
CRITERION_SECTIONS: dict[str, tuple[str, ...]] = {
    "필요성": ("policy_importance", "tech_importance"),
    "차별성": ("tech_importance", "overlap_review"),
    "실현가능성": ("method", "objective"),
    "기대효과": ("expected_management", "expected_technology", "expected_standing"),
}
CRITERION_ISSUE: dict[str, str] = {
    "필요성": "논리",
    "차별성": "중복·차별화",
    "실현가능성": "논리",
    "기대효과": "일관성",
}
MAX_REASON_CHARS = 300
# 버전을 만든 경로: local = 로컬 생성(v1), argon = Argon 1차 검토 자동 반영(v2 "Argon 보완"),
# edit = 제안자 편집(저장), final_review = 최종 검토 반영, revert = 복원
VersionOrigin = Literal["local", "argon", "edit", "final_review", "revert"]
ORIGIN_LABEL: dict[str, str] = {
    "local": "로컬 생성",
    "argon": "Argon 보완",
    "edit": "제안자 편집",
    "final_review": "최종 검토 반영",
    "revert": "복원",
}
ReviewStatus = Literal["done", "skipped", "error"]
ReviewKind = Literal["draft", "final"]  # 1차(초안 생성의 일부, 자동) / 최종(요청 시 1회)
# 수정안 없는 의견 / 폐기된 수정안의 의견 / 섹션 의견
AnnotationKind = Literal["opinion", "discarded", "section"]
MAX_MEMO_CHARS = 200
MAX_COMMENT_CHARS = 2000
MAX_REVISED_CHARS = 4000
# U1 근거 적합성 — Argon 1차 검토가 문장마다 내는 판정 (추가 호출 없음)
SUPPORT_VALUES: tuple[str, ...] = ("지지", "부분", "불일치")
SUPPORT_MISMATCH = "불일치"
# U1 제안자 근거 판단 — replace 는 이번 run 검색 집합 안의 id 로만
DecisionAction = Literal["approve", "replace", "exclude"]


def sentence_id(section: str, index: int) -> str:
    """검토 입출력에서 문장을 가리키는 id — "s:<섹션>:<인덱스>" (앱이 매긴다, 비신뢰 아님)."""
    return f"s:{section}:{index}"


def parse_sentence_id(value: str) -> tuple[str, int] | None:
    parts = (value or "").split(":")
    if len(parts) != 3 or parts[0] != "s" or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2])


CommentKind = Literal["revision", "addition"]  # 문장 의견·수정안 / Q5 빠진 요소 추가 문장 제안


class ReviewComment(BaseModel):
    id: str  # "r<차수>-<번호>"
    section: str
    sentence: int | None = None  # None 이면 섹션 전체 의견
    kind: CommentKind = "revision"
    after: int | None = None  # addition 일 때 넣을 위치(그 문장 뒤, None 이면 섹션 끝)
    issue_type: str = "문장"
    comment: str = Field(default="", max_length=MAX_COMMENT_CHARS)
    revised_text: str | None = Field(default=None, max_length=MAX_REVISED_CHARS)
    evidence: list[str] = Field(default_factory=list)  # 기존 근거 id 중에서만
    status: CommentStatus = "open"
    discard_reason: str | None = None  # 규칙 위반으로 폐기된 수정안의 사유 (코드)

    @property
    def usable(self) -> bool:
        """제안자가 "수정안 사용"으로 고를 수 있는 의견 — 검증 통과한 수정안이 있을 때."""
        return self.status == "open" and bool(self.revised_text)


class CriterionScore(BaseModel):
    """심사 기준 하나의 점수와 근거 한 줄 (외부 LLM 출력 — 비신뢰 텍스트, 길이 상한)."""

    criterion: str
    score: int = Field(ge=1, le=5)
    reason: str = Field(default="", max_length=MAX_REASON_CHARS)
    sentence_ids: list[str] = Field(default_factory=list)  # 근거가 된 문장 (보낸 문장 안에서만)

    @property
    def weak(self) -> bool:
        return self.score <= WEAK_SCORE


def score_comments(
    scores: list[CriterionScore],
    *,
    round_no: int,
    start_no: int,
    sent_ids: set[str],
    sections_present: set[str],
) -> list[ReviewComment]:
    """2점 이하 기준 → 관련 문장(sentence_ids) 또는 기본 섹션에 붙는 의견. 순수 함수."""
    out: list[ReviewComment] = []
    n = start_no
    for s in scores:
        if not s.weak:
            continue
        text = f"[{s.criterion} {s.score}점] {s.reason}".strip()[:MAX_COMMENT_CHARS]
        issue = CRITERION_ISSUE.get(s.criterion, "논리")
        targets = [sid for sid in s.sentence_ids if sid in sent_ids]
        if targets:
            for sid in targets:
                parsed = parse_sentence_id(sid)
                if parsed is None:
                    continue
                n += 1
                out.append(
                    ReviewComment(
                        id=f"r{round_no}-{n}",
                        section=parsed[0],
                        sentence=parsed[1],
                        issue_type=issue,
                        comment=text,
                    )
                )
            continue
        for key in CRITERION_SECTIONS.get(s.criterion, ()):
            if key in sections_present:
                n += 1
                out.append(
                    ReviewComment(
                        id=f"r{round_no}-{n}", section=key, issue_type=issue, comment=text
                    )
                )
                break
    return out


class ReviewTransfer(BaseModel):
    """외부 LLM 에 보낸 것의 범위 (manifest 용). 본문은 담지 않는다."""

    provider: str | None = None
    model: str | None = None
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    sentences_sent: int = 0
    sentences_excluded: int = 0  # include_internal=false 로 "검토 제외" 된 문장 수
    calls: int = 0  # 길이 상한으로 섹션 단위로 나눈 호출 수


class EvidenceDecision(BaseModel):
    """문장 하나의 근거 id 하나에 대한 제안자 판단. replacement 는 replace 일 때 새 근거 id."""

    sentence_id: str
    evidence_id: str
    action: DecisionAction = "approve"
    replacement: str | None = Field(default=None, max_length=200)

    @property
    def key(self) -> tuple[str, str]:
        return (self.sentence_id, self.evidence_id)


class EvidenceDecisionRequest(BaseModel):
    decisions: list[EvidenceDecision] = Field(default_factory=list, max_length=500)
    note: str = Field(default="", max_length=MAX_MEMO_CHARS)
    base_version: int | None = Field(default=None, ge=1)


class ReviewRound(BaseModel):
    round: int = Field(ge=1)  # 1 = 1차(draft) 검토, 2.. = 최종 검토 (final_round = round - 1)
    kind: ReviewKind = "draft"
    draft_version: int = Field(ge=1)  # 검토한 초안 버전
    status: ReviewStatus = "done"
    skipped_reason: str | None = None  # "no_review_llm" 등 코드
    comments: list[ReviewComment] = Field(default_factory=list)
    resolved_ids: list[str] = Field(default_factory=list)  # 이전 차수 의견 중 해결된 id
    excluded_sentences: list[str] = Field(default_factory=list)  # 검토 제외 문장 id (internal)
    transfer: ReviewTransfer = Field(default_factory=ReviewTransfer)
    scores: list[CriterionScore] = Field(
        default_factory=list
    )  # 심사 기준 채점 (P5). 이전 차수 파일은 빈 목록
    created_at: str | None = None
    # 1차 검토: 자동 반영 결과 — 반영된 의견 id, 폐기된 의견 id (v2 가 만들어졌으면 applied_version)
    applied_ids: list[str] = Field(default_factory=list)
    applied_version: int | None = None
    # 최종 검토: 1차 대비 점수 변화 {기준: ±n}
    score_delta: dict[str, int] = Field(default_factory=dict)
    # Q7 핵심 섹션 후보 선택 {섹션: {"choice": "A"|"B", "reason": str}}
    candidate_choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    # Q5 섹션별 필수 요소 충족 {섹션: {요소: True/False}} (검토 LLM 판단, 비신뢰)
    checklist: dict[str, dict[str, bool]] = Field(default_factory=dict)

    @property
    def checklist_coverage(self) -> float | None:
        items = [v for sec in self.checklist.values() for v in sec.values()]
        return (sum(1 for v in items if v) / len(items)) if items else None

    # U1 근거 적합성 — 문장 id → 지지|부분|불일치 (보낸 문장 안에서만). 이전 차수 파일은 빈 값
    support: dict[str, str] = Field(default_factory=dict)

    @property
    def final_round(self) -> int | None:
        return self.round - 1 if self.kind == "final" else None

    def comment(self, comment_id: str) -> ReviewComment | None:
        return next((c for c in self.comments if c.id == comment_id), None)

    @property
    def open_comments(self) -> list[ReviewComment]:
        return [c for c in self.comments if c.status == "open"]


class Annotation(BaseModel):
    """버전에 붙는 문장 메모 — 수정안 없는 의견·폐기 수정안의 의견·섹션 의견. 처리됨으로 접는다."""

    id: str  # 의견 id (r1-3) 또는 "a<번호>"
    section: str
    sentence: int | None = None  # None 이면 섹션 메모
    kind: AnnotationKind = "opinion"
    text: str = Field(default="", max_length=MAX_COMMENT_CHARS)  # 의견 본문 (비신뢰 텍스트)
    reason: str | None = None  # 폐기 사유 코드
    status: Literal["open", "done"] = "open"


class DraftVersion(BaseModel):
    version: int = Field(ge=1)
    origin: VersionOrigin = "local"
    sections: list[Section]
    created_at: str | None = None
    based_on_review: int | None = None  # 이 버전을 만들 때 참고한 검토 차수
    reverted_from: int | None = None  # origin=revert 일 때 복원한 버전
    note: str = Field(default="", max_length=MAX_MEMO_CHARS)  # 저장 메모 (선택)
    changed_sections: list[str] = Field(default_factory=list)  # 이전 버전과 달라진 섹션
    alerts: int = 0  # 저장 시점의 lint 알림 수
    annotations: list[Annotation] = Field(default_factory=list)  # 문장 메모 (Argon 의견)
    # U1 제안자 근거 판단 — 버전에 붙어 다음 버전으로 이어진다 (replace 뒤에는 새 id 기준)
    evidence_decisions: list[EvidenceDecision] = Field(default_factory=list)

    @property
    def sentence_count(self) -> int:
        return sum(len(s.sentences) for s in self.sections)

    @property
    def open_annotations(self) -> int:
        return sum(1 for a in self.annotations if a.status == "open")

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)


# ── 제안자 편집 요청 (④ 직접 수정·보완) ─────────────────────
EditAction = Literal["use_revision", "keep", "manual", "delete", "insert_after"]


class SentenceEdit(BaseModel):
    """문장별 선택.

    use_revision 은 검증을 통과한 수정안(comment_id)만, manual 은 직접 수정(원래 근거 유지,
    origin=proposer_edit), delete 는 삭제, insert_after 는 그 문장 뒤에 새 문장(proposer_input).
    """

    sentence_id: str  # "s:<섹션>:<인덱스>"
    action: EditAction = "keep"
    comment_id: str | None = (
        None  # use_revision 일 때 채택한 의견 id (없으면 그 문장의 최신 수정안)
    )
    text: str | None = Field(default=None, max_length=MAX_REVISED_CHARS)  # manual·insert_after


class SectionEdit(BaseModel):
    """섹션 전체 편집 — 문장 목록(texts) 또는 통문(text, 문장으로 나눈다)으로 바꾼다.
    같은 문장은 근거·출처를 이어받고, 새 문장은 proposer_input(근거 없음)."""

    section: str
    texts: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, max_length=20_000)
    order: list[str] | None = None  # 순서만 바꿀 때: 기존 문장 id 목록


class EditRequest(BaseModel):
    sentences: list[SentenceEdit] = Field(default_factory=list)
    sections: list[SectionEdit] = Field(default_factory=list)
    note: str = Field(default="", max_length=MAX_MEMO_CHARS)  # 저장 메모
    base_version: int | None = Field(default=None, ge=1)  # 동시 편집 보호 — 다르면 거부(409)
    done_annotations: list[str] = Field(default_factory=list)  # "처리됨" 으로 접을 메모 id
