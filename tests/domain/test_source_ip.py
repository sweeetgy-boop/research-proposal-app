"""자료원 IP 제한 판정 — 순수 함수 (레인 I)."""

from rra.domain.rules.source_ip import (
    NOTICE,
    IpPolicy,
    SourceIpBlocked,
    ip_notice,
    ip_registered,
    is_ip_error,
    lookup_needed,
    normalize_ip,
    restricted_sources,
    unregistered_notice,
)

NTIS = IpPolicy(True, ("59.0.166.199", "59.0.251.250"), "NTIS 국가R&D 과제")


def test_policy_from_mapping_cleans_ips_and_infers_restriction():
    p = IpPolicy.from_mapping(
        {"ip_restricted": True, "registered_ips": ["59.0.166.199", " 59.0.251.250 ", "bad", 7]},
        label="NTIS",
    )
    assert p.restricted and p.registered_ips == ("59.0.166.199", "59.0.251.250")
    assert p.source_label == "NTIS"
    assert IpPolicy.from_mapping({"ip_restricted": False}).restricted is False
    assert IpPolicy.from_mapping(None).restricted is False
    # ip_restricted 를 안 적었어도 목록이 있으면 제한으로 본다
    assert IpPolicy.from_mapping({"registered_ips": ["10.0.0.1"]}).restricted
    assert IpPolicy.from_mapping({"registered_ips": "59.0.166.199"}).registered_ips == ()


def test_normalize_ip_accepts_v4_v6_only():
    assert normalize_ip(" 59.0.166.199\n") == "59.0.166.199"
    assert normalize_ip("2001:DB8::1") == "2001:db8::1"
    assert normalize_ip("ntis.go.kr") == "" and normalize_ip("") == ""


def test_is_ip_error_matches_ntis_phrase_only():
    assert is_ip_error("접근 허용 IP가 아닙니다.")
    assert is_ip_error("NTIS 오류: 접근 허용  IP가 아닙니다.")
    assert is_ip_error("Not Allowed IP")
    assert not is_ip_error("유효한 인증키가 아닙니다.")
    assert not is_ip_error(None) and not is_ip_error("")


def test_ip_registered_true_when_unrestricted_none_when_unknown():
    assert ip_registered("59.0.251.250", NTIS) is True
    assert ip_registered("203.0.113.9", NTIS) is False
    assert ip_registered(None, NTIS) is None and ip_registered("nope", NTIS) is None
    assert ip_registered(None, IpPolicy(False)) is True


def test_notice_wording_is_exact():
    assert (
        unregistered_notice("203.0.113.9", "NTIS 국가R&D 과제")
        == "현재 IP 203.0.113.9 가 NTIS 국가R&D 과제 등록 IP 에 없습니다. 활용신청에 추가하세요"
    )
    assert NOTICE.format(ip="x", source="y") == (
        "현재 IP x 가 y 등록 IP 에 없습니다. 활용신청에 추가하세요"
    )
    assert unregistered_notice(None, "NTIS").startswith("현재 IP (확인 실패) 가 NTIS 등록 IP")


def test_ip_notice_cases():
    assert ip_notice("59.0.166.199", NTIS) is None  # 등록됨
    assert ip_notice("203.0.113.9", NTIS) == unregistered_notice("203.0.113.9", NTIS.source_label)
    assert ip_notice(None, NTIS) is None  # 조회 실패·거부 없음 → 진단만
    assert ip_notice(None, NTIS, blocked=True) == unregistered_notice(None, NTIS.source_label)
    # 등록 목록에 있어도 API 가 거부하면 안내 (등록 반영 전)
    assert ip_notice("59.0.166.199", NTIS, blocked=True) is not None
    assert ip_notice("1.2.3.4", IpPolicy(False, (), "ScienceON")) is None
    assert ip_notice("1.2.3.4", IpPolicy(False, (), "ScienceON"), blocked=True) is not None


def test_helpers_and_exception_type():
    assert restricted_sources({"ntis": NTIS, "scienceon": IpPolicy(False)}) == ["ntis"]
    assert lookup_needed([IpPolicy(False), NTIS]) and not lookup_needed([IpPolicy(False)])
    assert issubclass(SourceIpBlocked, RuntimeError)
