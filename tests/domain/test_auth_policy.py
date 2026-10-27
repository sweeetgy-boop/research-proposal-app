"""로그인 정책 순수 규칙 (레인 A): 가명 ID 형식·run 저장소 키·잠금·지연·일일 상한."""

import pytest

from rra.domain.models import Principal
from rra.domain.rules import auth_policy as ap
from rra.domain.rules.auth_policy import LockoutPolicy, LoginGuard

DIGEST = "ab12cd34ef56" + "0" * 52


def test_pseudonyms_and_run_user_keys():
    staff = ap.staff_principal(DIGEST)
    assert staff.kind == "staff" and staff.id == "staff:ab12cd34ef56"
    assert ap.run_user(staff) == "staff-ab12cd34ef56"
    guest = ap.guest_principal("team-a")
    assert guest.id == "guest:team-a" and ap.run_user(guest) == "guest-team-a"
    assert ap.run_user(ap.admin_principal()) == "local" and ap.admin_principal().is_admin
    with pytest.raises(ValueError):
        ap.staff_pseudonym("zz")  # hex 가 아님
    with pytest.raises(ValueError):
        ap.guest_principal("Bad Id")  # 공백·대문자
    assert (
        ap.valid_staff_no("K-12345")
        and not ap.valid_staff_no("홍길동")
        and not ap.valid_staff_no("1")
    )


def test_daily_limits_by_kind_and_day():
    assert ap.daily_run_limit(Principal(kind="guest", id="guest:g")) == 10
    assert ap.daily_run_limit(Principal(kind="staff", id="staff:ab12cd34ef56")) == 20
    assert ap.daily_run_limit(ap.admin_principal()) is None
    created = ["2026-10-27T01:00:00+00:00"] * 3 + ["2026-10-26T23:00:00+00:00"] * 5
    assert ap.daily_limit_reached(created, "2026-10-27", 3)
    assert not ap.daily_limit_reached(created, "2026-10-27", 4)
    assert not ap.daily_limit_reached(created, "2026-10-27", None)


def test_account_lock_after_five_consecutive_failures_and_expires():
    g = LoginGuard()
    for i in range(4):
        g.failure("staff:a", "1.1.1.1", now=100 + i)
        assert not g.locked("staff:a", "1.1.1.1", now=100 + i)
    g.failure("staff:a", "1.1.1.1", now=104)
    assert g.locked("staff:a", "1.1.1.1", now=105)
    assert not g.locked("staff:b", "2.2.2.2", now=105)  # 다른 계정·IP 는 무관
    assert not g.locked("staff:a", "1.1.1.1", now=104 + 601)  # 10분 뒤 풀린다
    g.success("staff:a")
    assert not g.locked("staff:a", None, now=106)


def test_ip_lock_after_twenty_failures_in_window_and_global_delay():
    g = LoginGuard(LockoutPolicy(global_failures=25, global_delay_sec=1.5))
    for i in range(20):
        g.failure(None, "9.9.9.9", now=1000 + i)  # 미등록 사번 — 계정 키 없음
    assert g.locked("staff:x", "9.9.9.9", now=1020)
    assert not g.locked("staff:x", "8.8.8.8", now=1020)
    assert g.delay(now=1020) == 0.0
    for i in range(6):
        g.failure(None, "7.7.7.7", now=1021 + i)
    assert g.delay(now=1027) == 1.5  # 전체 26건 > 25
    assert g.delay(now=1027 + 601) == 0.0  # 창이 지나면 해제
    assert not g.locked("staff:x", "9.9.9.9", now=1000 + 601)


def test_valid_password_min_length_is_configurable():
    from rra.domain.rules.auth_policy import DEFAULT_MIN_PASSWORD_LENGTH, valid_password

    assert DEFAULT_MIN_PASSWORD_LENGTH == 8
    assert not valid_password("")
    assert not valid_password("1234567") and valid_password("12345678")
    assert valid_password("1234", 4) and not valid_password("123", 4)  # 시범 한정 4자
    assert valid_password("x", 0)  # 0·음수는 1 로 본다 (빈 값은 항상 거부)
