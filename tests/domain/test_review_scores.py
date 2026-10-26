"""심사 기준 채점(P5) — CriterionScore 와 2점 이하 → 의견 연결 (순수 규칙)."""

import pytest
from pydantic import ValidationError

from rra.domain.models.review import (
    CRITERIA,
    CriterionScore,
    ReviewRound,
    score_comments,
)


def test_criteria_and_score_bounds():
    assert CRITERIA == ("필요성", "차별성", "실현가능성", "기대효과")
    assert CriterionScore(criterion="필요성", score=2).weak
    assert not CriterionScore(criterion="필요성", score=3).weak
    with pytest.raises(ValidationError):
        CriterionScore(criterion="필요성", score=6)
    with pytest.raises(ValidationError):
        CriterionScore(criterion="필요성", score=0)
    assert ReviewRound(round=1, draft_version=1).scores == []  # 이전 차수 파일 호환


def test_weak_scores_attach_to_cited_sentences_or_default_section():
    scores = [
        CriterionScore(criterion="필요성", score=4, reason="좋음"),
        CriterionScore(
            criterion="차별성",
            score=2,
            reason="차이 없음",
            sentence_ids=["s:tech_importance:1", "s:nope:0"],
        ),
        CriterionScore(criterion="실현가능성", score=1, reason="검증 없음"),
        CriterionScore(criterion="기대효과", score=2, reason="정성뿐", sentence_ids=["s:method:9"]),
    ]
    comments = score_comments(
        scores,
        round_no=2,
        start_no=3,
        sent_ids={"s:tech_importance:1", "s:method:0"},
        sections_present={"tech_importance", "method", "expected_technology"},
    )
    assert [(c.id, c.section, c.sentence, c.issue_type) for c in comments] == [
        ("r2-4", "tech_importance", 1, "중복·차별화"),  # 보낸 문장 id 만
        ("r2-5", "method", None, "논리"),  # 문장 id 없음 → 기본 섹션 중 존재하는 첫 섹션
        ("r2-6", "expected_technology", None, "일관성"),  # s:method:9 는 보낸 문장이 아님 → 섹션
    ]
    assert comments[0].comment == "[차별성 2점] 차이 없음" and all(
        c.status == "open" for c in comments
    )
    assert (
        score_comments(scores[:1], round_no=1, start_no=0, sent_ids=set(), sections_present=set())
        == []
    )
