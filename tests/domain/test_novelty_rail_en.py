"""영문 자료의 철도 분야 판정 (config/novelty.yaml rail_field, 2026-11-10).

유추는 '다른 분야 사례'가 목적이라 영문 철도 논문도 걸러야 한다. 철도 밖 자료가 잘못 걸리지
않는지(training·track record·ballast water)도 고정한다."""

import pytest

from rra.config_loader import novelty_config
from rra.domain.models import Document
from rra.domain.models.problem_card import CardText, Facets, ProblemCard, ProblemTerms
from rra.domain.rules.novelty import card_rail_terms, card_rail_terms_en, rail_reason
from rra.settings import Settings

RULE = novelty_config(Settings()).rail_field


def doc(title: str, abstract: str = "", **raw) -> Document:
    return Document(
        doc_id="openalex:W1",
        source="scienceon",
        doc_type="paper",
        title=title,
        abstract=abstract,
        lang="en",
        raw=raw,
    )


@pytest.mark.parametrize(
    "title",
    [
        "Track irregularity data",
        "Correlation of track irregularities and vehicle responses based on measured data",
        "Measurements and analysis of track irregularities on high speed maglev lines",
        "DETECTION METHOD FOR UNSUPPORTED SLEEPERS BASED ON TRACK IRREGULARITY",
        "DEVELOPMENT OF THE BRIDGE DEFLECTION-TRACK IRREGULARITY CONVERSION PROGRAM",
        "Settlement of ballasted track under cyclic loading",
        "Condition monitoring of rolling stock bearings",
        "Wheel-rail contact forces on curves",
        "Ballast fouling and sleeper support stiffness",  # 약한 말 두 개
        "A maglev guideway vibration study",
    ],
)
def test_english_rail_titles_are_rail(title):
    assert rail_reason(doc(title), RULE) == "terms"


@pytest.mark.parametrize(
    "title",
    [
        "Training deep networks for structural health monitoring",
        "A track record of pigeon deterrent trials on buildings",
        "Fast-track approval of odor control devices",
        "Ballast water treatment and odor emissions on ships",
        "Eye tracking of visitors at tourist attractions",
        "Sleeper cells in bird roost detection",
        "Autonomous Detection and Deterrence of Pigeons on Buildings by Drones",
        "Development of an Air Duct Damper to Prevent Backflow Odor",
        "Handrail design for public restrooms",
    ],
)
def test_non_rail_english_titles_are_not_rail(title):
    assert rail_reason(doc(title), RULE) is None


def test_phrase_in_abstract_head_counts_but_single_weak_word_does_not():
    assert rail_reason(doc("Vibration data set", "We release track geometry records."), RULE) == (
        "abstract"
    )
    assert rail_reason(doc("Vibration data set", "Our track record is long."), RULE) is None


def card(objects_ko, objects_en, target="", place="") -> ProblemCard:
    return ProblemCard(
        facets=Facets(target=CardText(value=target), place=CardText(value=place)),
        terms=ProblemTerms(objects_ko=objects_ko, objects_en=objects_en),
    )


def test_card_about_rail_asset_promotes_weak_words_for_that_request_only():
    track = card(["궤도", "가속도센서"], ["track", "vehicle", "accelerometer"], target="궤도")
    extra = card_rail_terms_en(track, RULE)
    assert "track" in extra and "sleeper" in extra and "vehicle" not in extra
    single = doc("Long-term track settlement prediction")  # 약한 말 하나
    assert rail_reason(single, RULE) is None
    assert rail_reason(single, RULE, extra_en=extra) == "terms"
    # 초록에만 있는 약한 말은 승격해도 보지 않는다(제목·키워드만)
    assert rail_reason(doc("Vibration data", "the track was wet"), RULE, extra_en=extra) is None
    # 대상이 철도 시설이 아니면(비둘기·악취) 승격 없음 — 장소 칸이 철도여도 대상어 영문은 그대로
    pigeon = card(["비둘기", "조류"], ["pigeon", "bird"], target="비둘기")
    assert card_rail_terms_en(pigeon, RULE) == ()
    in_station = card(["비둘기"], ["pigeon"], target="비둘기", place="철도역사 승강장 지붕")
    assert "pigeon" not in card_rail_terms_en(in_station, RULE)


def ko(title: str) -> Document:
    return Document(doc_id="scienceon:K1", source="scienceon", doc_type="paper", title=title)


@pytest.mark.parametrize(
    "title",
    [
        "자기부상선로 검측장치",
        "지하구조물의 변위거동에 따른 침목플로팅궤도의 손상영향분석",
        "고속선 ESJ에서의 차상신호파형 왜곡특성 분석",
        "도시철도 승강장 혼잡도 분석",
    ],
)
def test_korean_compound_rail_titles_are_rail(title):
    assert rail_reason(ko(title), RULE) == "terms"


@pytest.mark.parametrize(
    "title",
    [
        "전송선로 임피던스 정합 회로",
        "교량 가속도센서 기반 구조물 모니터링",
        "도로 노면 상태 검측 차량",
        "설비 예지 진단을 위한 진동 분석",
    ],
)
def test_korean_non_rail_titles_are_not_rail_without_a_rail_card(title):
    assert rail_reason(ko(title), RULE) is None


def test_rail_card_promotes_korean_rail_terms_inside_compounds():
    track = card(["궤도", "가속도센서"], ["track"], target="궤도")
    rail_ko, rail_en = card_rail_terms(track, RULE)
    assert "궤도" in rail_ko and "선로" in rail_ko and "track" in rail_en
    doc_ = ko("현방식 방향틀림 검측치의 기준선 보정: 슬래브궤도 구간")
    assert rail_reason(doc_, RULE) is None
    assert rail_reason(doc_, RULE, extra_ko=rail_ko) == "terms"
    # 철도 밖 자료는 그대로 남는다
    assert rail_reason(ko("교량 가속도센서 기반 구조물 모니터링"), RULE, extra_ko=rail_ko) is None
    assert card_rail_terms(card(["비둘기"], ["pigeon"], target="비둘기"), RULE) == ((), ())
