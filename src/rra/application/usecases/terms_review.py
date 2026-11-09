"""동의어 검토표 만들기 (`rra terms review`, 레인 E, ADR 0059, 계약 docs/contracts/overlap-facets.md
§4).

`config/generic_terms.candidates.yaml`·`rail_terms.candidates.yaml`(미커밋) 을 읽어 선별 규칙
(`domain/rules/synonyms.select_synonyms`)으로 묶고, 검토표(`docs/review/terms-review.md`, 체크 칸
`- [ ]`)와
고신뢰 항목만 `config/overlap.yaml synonyms.candidates` 구역에 적는다. **스위치 `synonyms.enabled`
는
건드리지 않는다** — 사람 검토 뒤 사용자가 켠다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from rra.application.ports.terms_review import TermCandidatesReaderPort, TermsReviewWriterPort
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.synonyms import (
    SynonymConfig,
    SynonymReview,
    high_confidence,
    select_synonyms,
)


@dataclass(frozen=True)
class TermsReviewReport:
    rows: int  # 읽은 후보 행 수
    reviews: int
    high: int
    review_path: str
    candidates_path: str


class TermsReview:
    def __init__(
        self,
        reader: TermCandidatesReaderPort,
        writer: TermsReviewWriterPort,
        rule: KeywordRule,
        *,
        config: SynonymConfig | None = None,
        today: Callable[[], date] = date.today,
    ):
        self.reader, self.writer, self.rule = reader, writer, rule
        self.config = config or SynonymConfig()
        self.today = today

    def __call__(self) -> TermsReviewReport:
        rows = self.reader.read()
        reviews = select_synonyms(rows, self.rule, self.config)
        high = high_confidence(reviews)
        review_path = self.writer.write_review(render_review(reviews, len(rows), self.today()))
        cand_path = self.writer.write_candidates(high)
        return TermsReviewReport(
            rows=len(rows),
            reviews=len(reviews),
            high=len(high),
            review_path=review_path,
            candidates_path=cand_path,
        )


def render_review(reviews: Sequence[SynonymReview], rows: int, today: date) -> str:
    """검토표 Markdown — 항목·구성원·빈도·공출현 근거 수·추천 여부·체크 칸. 한국어."""
    high = [r for r in reviews if r.confidence == "high"]
    rest = [r for r in reviews if r.confidence != "high"]
    lines = [
        f"# 동의어 후보 검토표 ({today.isoformat()}, 레인 E, ADR 0059)",
        "",
        "`rra terms review` 가 `config/*.candidates.yaml`(`rra terms candidates` 결과, 미커밋) 을 "
        "읽어 자동 선별한 결과다.",
        "**검토 전 — 운영 반영 안 함.** 확인한 항목은 `- [x]` 로 바꾸고, 틀린 묶음은 지운다. "
        "고신뢰 항목은",
        "`config/overlap.yaml synonyms.candidates` 구역에 같은 내용으로 들어 있다. 사람 검토가 "
        "끝나기 전에는 `synonyms.enabled` 를 켜지 않는다.",
        "",
        f"- 읽은 후보 행: {rows}건 · 묶음: {len(reviews)}건 "
        f"(고신뢰 {len(high)} · 검토 필요 {len(rest)})",
        "- 고신뢰 = 철도 용어 씨앗 묶음의 구성원이 후보에 둘 이상 나타나고 문서빈도 하한 이상.",
        "- 검토 필요 = 씨앗 구성원이 하나만 나타났거나(공출현 확인 불가), 포함 관계(상·하위어일 수 "
        "있음)로 묶인 것.",
        "- 질의 확장은 OR(FTS5 토큰별 인용)로만 쓰고 차단 키워드 겹침에는 쓰지 않는다(1단계).",
        "",
        "## 1. 고신뢰 (overlap.yaml 후보 구역에 적음)",
        "",
        "| 확인 | 대표어 | 구성원(빈도 순) | 문서빈도 합 | 공출현 근거 | 후보에 없던 씨앗 | 추천 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in high:
        lines.append(_row(r, "반영 추천"))
    if not high:
        lines.append("| | (없음) | | | | | |")
    lines += [
        "",
        "## 2. 검토 필요",
        "",
        "| 확인 | 대표어 | 구성원(빈도 순) | 문서빈도 합 | 공출현 근거 | 근거 | 추천 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rest:
        basis = {
            "seed": "씨앗 1개만 나타남",
            "related": "관련어 묶음(상·하위어·관련어)",
            "contains": "포함 관계(상·하위어 가능)",
        }[r.basis]
        lines.append(_row(r, "보류 — 사람 판단", basis_text=basis))
    if not rest:
        lines.append("| | (없음) | | | | | |")
    lines.append("")
    return "\n".join(lines)


def _row(r: SynonymReview, recommend: str, *, basis_text: str | None = None) -> str:
    extra = basis_text if basis_text is not None else (", ".join(r.missing) or "—")
    return (
        f"| - [ ] | {r.canonical} | {', '.join(r.variants)} | {r.doc_freq} | {r.cooccur} | "
        f"{extra} | {recommend} |"
    )
