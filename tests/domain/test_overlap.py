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
