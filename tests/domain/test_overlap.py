import pytest

from rra.domain.rules.overlap import department_listed, judge, tier_of, unlisted_department


def test_own_tier_blocks_at_lower_threshold(docs, own):
    alerts = judge([(docs[0], 0.82), (docs[1], 0.82)], own=own)
    own = next(a for a in alerts if a.doc_id == "alio:1")
    ext = next(a for a in alerts if a.doc_id == "openalex:W1")
    assert own.tier == "own" and own.blocking
    assert ext.tier == "external" and not ext.blocking


def test_alert_carries_basis(docs):
    summary = docs[0].model_copy(update={"text_basis": "summary"})
    (alert,) = judge([(summary, 0.5)])
    assert alert.basis == "summary"


def _korail(department, orgs=("korail",)):
    from rra.domain.models import Document

    return Document(
        doc_id="alio:x",
        source="alio",
        doc_type="internal_report",
        title="t",
        orgs=list(orgs),
        department=department,
    )


@pytest.mark.parametrize(
    ("department", "listed"),
    [
        ("경영연구처", True),
        ("경영 연구처", True),  # 공백 차이
        ("철도연구원 경영연구처", True),  # 토큰 일치
        ("경영연구처(자산개발)", True),
        ("기술연구처/궤도팀", True),
        ("경영연구처분실", False),  # 목록 이름을 포함만 함 — 부분 문자열 매칭 안 함
        ("한국철도공사 철도연구원장실", False),
        ("안전계획처", False),
        ("", False),
        (None, False),
    ],
)
def test_department_listed_is_exact_or_token_match(own, department, listed):
    assert department_listed(department, own) is listed


def test_own_requires_both_org_and_listed_department(own):
    assert tier_of(_korail("경영연구처"), own) == "own"
    assert tier_of(_korail("안전계획처"), own) == "domestic_rail"
    assert tier_of(_korail("경영연구처", orgs=("krri",)), own) == "external"  # 타 기관 동명 부서
    assert tier_of(_korail("경영연구처")) == "domestic_rail"  # own 기준 없으면 own 티어 없음


def test_substring_철도연구원_alone_no_longer_decides_own(own):
    doc = _korail("철도연구원 부설 무언가")  # 토큰 "철도연구원" 은 목록에 있으므로 own
    assert tier_of(doc, own) == "own"
    assert tier_of(_korail("철도연구원분원"), own) == "domestic_rail"  # 부분 문자열은 아님


def test_unlisted_department_only_for_own_org(own):
    assert unlisted_department(_korail("안전계획처"), own) == "안전계획처"
    assert unlisted_department(_korail("경영연구처"), own) is None
    assert unlisted_department(_korail("안전계획처", orgs=("kr",)), own) is None
    assert unlisted_department(_korail(None), own) is None


# ── 키워드 조건: 유사도만으로 차단하지 않는다 ─────────────────
from pathlib import Path  # noqa: E402

from rra.domain.models import Document  # noqa: E402
from rra.domain.rules.keywords import KeywordRule  # noqa: E402

SUMMARY = (Path(__file__).parents[1] / "fixtures/alio/summary/korail_2026_asset.txt").read_text(
    encoding="utf-8"
)
ASSET_DOC = Document(
    doc_id="alio:sum-asset",
    source="alio",
    doc_type="internal_report",
    title="지속가능한 자산개발 사업다각화 모델 제안 연구",
    body=SUMMARY,
    orgs=["korail"],
    department="경영연구처",
    text_basis="summary",
)
# 실측 (multilingual-e5-base, 2026-10-13): 궤도 0.832 · 자산개발 0.867 · 구내식당 0.797
TRACK = (
    "궤도 검측 이력 기반 궤도 틀림 열화 예측 및 보수 우선순위 산정 경부선 구간에서 궤도 틀림이 "
    "반복 발생하고 다짐 작업 후에도 다시 열화된다 노반·도상 침하로 진행 속도가 다르다"
)
ASSET = (
    "코레일 보유 유휴부지와 역세권 자산이 단순 매각 방식으로 처분되어 자산이 줄고 있다. "
    "직접개발·임대·합작 등 다양한 자산개발 구조를 검토할 사업 모델과 타당성 분석 체계가 없다. "
    "자산개발 사업다각화 모델을 제안하고 시범부지의 사업 타당성을 분석한다."
)
CAFETERIA = (
    "역 구내 식당의 점심 메뉴를 개선하여 직원 만족도를 높이는 방안. "
    "메뉴가 단조롭고 대기 시간이 길다."
)
RULE = KeywordRule()


def test_only_asset_proposal_blocks_against_asset_summary(own):
    asset = judge([(ASSET_DOC, 0.867)], own=own, query=ASSET, keywords=RULE)[0]
    track = judge([(ASSET_DOC, 0.832)], own=own, query=TRACK, keywords=RULE)[0]
    cafe = judge([(ASSET_DOC, 0.80)], own=own, query=CAFETERIA, keywords=RULE)[0]
    assert asset.tier == track.tier == cafe.tier == "own"
    assert asset.blocking and {"자산개발", "유휴부지", "매각", "타당성"} <= set(asset.keywords)
    assert not track.blocking and track.keywords == []  # 유사도는 0.80 을 넘지만 비차단 경보
    assert not cafe.blocking and cafe.keywords == []


def test_generic_only_overlap_does_not_block(own):
    doc = ASSET_DOC.model_copy(update={"body": "철도 공사 사업 개선 연구 분석 방안 기술 시스템"})
    query = "철도 공사 사업 개선 연구 궤도 틀림"
    (alert,) = judge([(doc, 0.95)], own=own, query=query, keywords=RULE)
    assert not alert.blocking and alert.keywords == []


def test_without_keyword_rule_similarity_alone_decides(own):
    (alert,) = judge([(ASSET_DOC, 0.832)], own=own, query=TRACK)
    assert alert.blocking and alert.keywords == []


def test_keywords_below_threshold_do_not_block(own):
    (alert,) = judge([(ASSET_DOC, 0.70)], own=own, query=ASSET, keywords=RULE)
    assert not alert.blocking and alert.keywords  # 키워드는 보여 주되 임계치 미달


# ── 국가R&D 과제 티어 (NTIS, 2026-10-27) ─────────────────────
def _ntis(doc_type="rnd_project", orgs=("korail",), department=None):
    from rra.domain.models import Document

    return Document(
        doc_id="ntis:1415171234",
        source="ntis",
        doc_type=doc_type,
        title="t",
        orgs=list(orgs),
        department=department,
    )


def test_ntis_projects_are_national_rnd_regardless_of_agency(own):
    assert tier_of(_ntis(), own) == "national_rnd"
    assert tier_of(_ntis(orgs=("krri",)), own) == "national_rnd"
    assert tier_of(_ntis(orgs=()), own) == "national_rnd"
    assert tier_of(_ntis()) == "national_rnd"  # own 기준 없어도


def test_ntis_own_department_still_wins_and_reports_are_not_national_rnd(own):
    assert (
        tier_of(_ntis(department="철도연구원"), own) == "own"
    )  # 부서가 있으면(미래 필드) own 이 우선
    assert tier_of(_ntis(doc_type="report"), own) == "domestic_rail"  # 보고서는 기관 태그로


def test_national_rnd_threshold_and_label(own):
    from rra.domain.rules.overlap import DEFAULT_THRESHOLDS, no_overlap_statement, tier_label

    assert DEFAULT_THRESHOLDS["national_rnd"] == DEFAULT_THRESHOLDS["own"] == 0.80
    (alert,) = judge([(_ntis(), 0.81)], own=own)
    assert alert.tier == "national_rnd" and alert.blocking and alert.own_detail is None
    assert tier_label("national_rnd") == "국가R&D 과제"
    assert "국가R&D 과제 0.80" in no_overlap_statement({"ntis": 3}, [])[-1]


def test_judge_keeps_input_order_within_blocking_groups(docs, own):
    """reranker 가 고른 순서를 유사도 재정렬로 버리지 않는다 (ADR 0028). 입력이 유사도 순이면
    종전과 같다."""
    low, high = docs[0].model_copy(update={"doc_id": "alio:low"}), docs[0]
    alerts = judge([(low, 0.81), (high, 0.95), (docs[1], 0.50)], own=own)
    assert [a.doc_id for a in alerts] == ["alio:low", "alio:1", "openalex:W1"]
    assert [a.blocking for a in alerts] == [True, True, False]
