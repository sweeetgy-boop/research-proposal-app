"""정책·계획명 입력 근거 규칙 — 입력에 없는 고유명·차수·연도가 든 문장을 걸러낸다."""

import pytest

from rra.domain.rules.grounding import named_references, ungrounded

BASIS = (
    "제4차 국가철도망 구축계획에 철도 디지털 전환이 포함됨. 「스마트 철도 안전 강화 방안」 참고."
)


@pytest.mark.parametrize(
    "text",
    [
        "제4차 국가철도망 구축계획에 따라 디지털 전환을 추진함",
        "「스마트 철도 안전 강화 방안」과 연계되는 과제임",
        "정부의 구축계획에 부합함",  # 조사로 끝나는 수식어는 이름에 포함하지 않는다
        "경영전략과 연계되며 정책적 중요도가 높음",  # 일반어
        "관련 계획을 수립함",
    ],
)
def test_grounded_sentences_pass(text):
    assert ungrounded(text, [BASIS]) == []


@pytest.mark.parametrize(
    ("text", "invented"),
    [
        ("제5차 국가철도망 구축계획에 따라 추진함", "제5차"),
        ("철도산업발전 기본계획에 부합함", "철도산업발전 기본계획"),
        ("2030 탄소중립 로드맵을 따름", "탄소중립 로드맵"),
        ("「철도 혁신 비전」과 연계됨", "철도 혁신 비전"),
        ("탄소중립 로드맵 2030을 따름", "2030"),
    ],
)
def test_invented_names_and_numbers_are_caught(text, invented):
    assert invented in ungrounded(text, [BASIS])


def test_whitespace_is_ignored_when_matching():
    assert ungrounded("국가철도망구축계획에 따라", ["국가철도망 구축계획"]) == []


def test_no_allowed_text_means_every_name_is_ungrounded():
    assert ungrounded("국가철도망 구축계획에 따라", []) == ["국가철도망 구축계획"]


def test_named_references_dedupes_in_order():
    refs = named_references("「가 나」 「가 나」 2030 2030")
    assert refs == ["가 나", "2030"]
