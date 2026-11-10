"""영문 자료의 철도 분야 판정 (config/novelty.yaml rail_field, 2026-11-10).

유추는 '다른 분야 사례'가 목적이라 영문 철도 논문도 걸러야 한다. 철도 밖 자료가 잘못 걸리지
않는지(training·track record·ballast water)도 고정한다."""

import pytest

from rra.config_loader import novelty_config
from rra.domain.models import Document
from rra.domain.models.problem_card import CardText, Facets, ProblemCard, ProblemTerms
from rra.domain.rules.novelty import rail_asset_basis, rail_reason
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


def test_rail_asset_is_judged_by_object_and_target_not_place():
    """대상 자체가 철도 시설인가 — 대상어·대상 칸만 본다. 장소 칸(철도역사)은 보지 않는다."""
    track = card(["궤도", "가속도센서"], ["track"], target="궤도 및 운행 차량 탑재 가속도 센서")
    assert rail_asset_basis(track, RULE) == ["궤도"]
    assert rail_asset_basis(card(["전차선", "아크"], [], target="전차선"), RULE) == ["전차선"]
    # 철도역사의 비둘기·공중화장실 악취·관광객 — 대상은 철도 밖에도 있다
    pigeon = card(["비둘기", "조류"], ["pigeon"], target="비둘기", place="철도역사 승강장 지붕")
    odor = card(
        ["악취", "배수구"], ["odor"], target="배관·배수구 악취 가스", place="철도역사 공중화장실"
    )
    tour = card(["관광객", "이동수단"], ["tourist"], target="관광객, 연계 이동 수단")
    for c in (pigeon, odor, tour):
        assert rail_asset_basis(c, RULE) == []
    assert rail_asset_basis(None, RULE) == []


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
def test_korean_non_rail_titles_are_not_rail(title):
    assert rail_reason(ko(title), RULE) is None
