"""동의어 검토표 포트 (레인 E, ADR 0059). 후보 통계 읽기(`config/*.candidates.yaml`, 미커밋)와
검토표(`docs/review/terms-review.md`)·`overlap.yaml synonyms.candidates` 구역 쓰기. 구현은
adapters/terms."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rra.domain.rules.synonyms import SynonymReview, TermStatRow


@runtime_checkable
class TermCandidatesReaderPort(Protocol):
    def read(self) -> list[TermStatRow]:
        """두 후보 파일의 행 (kind 는 rail | generic). 파일이 없으면 빈 목록."""
        ...


@runtime_checkable
class TermsReviewWriterPort(Protocol):
    def write_review(self, markdown: str) -> str:
        """검토표 파일을 쓰고 경로 문자열을 돌려준다."""
        ...

    def write_candidates(self, reviews: Sequence[SynonymReview]) -> str:
        """`overlap.yaml` 의 `synonyms.candidates` 구역만 바꾼다(다른 줄·주석은 그대로).
        경로 문자열."""
        ...
