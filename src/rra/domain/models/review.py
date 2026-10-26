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
VersionOrigin = Literal["local", "edit", "revert"]
ReviewStatus = Literal["done", "skipped", "error"]
MAX_COMMENT_CHARS = 2000
MAX_REVISED_CHARS = 4000


def sentence_id(section: str, index: int) -> str:
    """검토 입출력에서 문장을 가리키는 id — "s:<섹션>:<인덱스>" (앱이 매긴다, 비신뢰 아님)."""
    return f"s:{section}:{index}"


def parse_sentence_id(value: str) -> tuple[str, int] | None:
    parts = (value or "").split(":")
    if len(parts) != 3 or parts[0] != "s" or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2])


class ReviewComment(BaseModel):
    id: str  # "r<차수>-<번호>"
    section: str
    sentence: int | None = None  # None 이면 섹션 전체 의견
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


class ReviewTransfer(BaseModel):
    """외부 LLM 에 보낸 것의 범위 (manifest 용). 본문은 담지 않는다."""

    provider: str | None = None
    model: str | None = None
    public_doc_ids: list[str] = Field(default_factory=list)
    internal_doc_ids: list[str] = Field(default_factory=list)
    sentences_sent: int = 0
    sentences_excluded: int = 0  # include_internal=false 로 "검토 제외" 된 문장 수
    calls: int = 0  # 길이 상한으로 섹션 단위로 나눈 호출 수


class ReviewRound(BaseModel):
    round: int = Field(ge=1)
    draft_version: int = Field(ge=1)  # 검토한 초안 버전
    status: ReviewStatus = "done"
    skipped_reason: str | None = None  # "no_review_llm" 등 코드
    comments: list[ReviewComment] = Field(default_factory=list)
    resolved_ids: list[str] = Field(default_factory=list)  # 이전 차수 의견 중 해결된 id
    excluded_sentences: list[str] = Field(default_factory=list)  # 검토 제외 문장 id (internal)
    transfer: ReviewTransfer = Field(default_factory=ReviewTransfer)
    created_at: str | None = None

    def comment(self, comment_id: str) -> ReviewComment | None:
        return next((c for c in self.comments if c.id == comment_id), None)

    @property
    def open_comments(self) -> list[ReviewComment]:
        return [c for c in self.comments if c.status == "open"]


class DraftVersion(BaseModel):
    version: int = Field(ge=1)
    origin: VersionOrigin = "local"
    sections: list[Section]
    created_at: str | None = None
    based_on_review: int | None = None  # 이 버전을 만들 때 참고한 검토 차수
    reverted_from: int | None = None  # origin=revert 일 때 복원한 버전
    note: str = ""

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)
