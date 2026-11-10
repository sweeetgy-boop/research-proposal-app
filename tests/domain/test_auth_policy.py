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


def test_failure_reports_the_moment_a_lock_starts_and_its_scope():
    """잠금이 시작된 그 실패에서만 started 가 채워진다(계정·IP 따로). 잠긴 뒤 실패는 비어 있다."""
    g = LoginGuard()
    for i in range(4):
        assert g.failure("guest:team", "1.1.1.1", now=100 + i).started == ()
        assert g.lock_scope("guest:team", "1.1.1.1", now=100 + i) is None
    assert g.failure("guest:team", "1.1.1.1", now=104).started == ("account",)
    assert g.lock_scope("guest:team", "1.1.1.1", now=105) == "account"
    assert g.failure("guest:team", "1.1.1.1", now=105).started == ()  # 이미 잠김 — 다시 알리지 않음
    assert g.lock_scope("guest:other", "1.1.1.1", now=105) is None
    assert g.lock_scope("guest:team", "1.1.1.1", now=105 + 601) is None  # 마지막 실패 뒤 10분


def test_ip_lock_start_scope_and_release_after_window():
    g = LoginGuard()
    for i in range(19):
        assert g.failure(None, "9.9.9.9", now=1000 + i).started == ()
    assert g.failure(None, "9.9.9.9", now=1019).started == ("ip",)
    assert g.lock_scope(None, "9.9.9.9", now=1020) == "ip"
    assert g.lock_scope("staff:x", "9.9.9.9", now=1020) == "ip"
    assert g.lock_scope(None, "8.8.8.8", now=1020) is None
    assert g.lock_scope(None, None, now=1020) is None  # 접속자를 모르면 IP 잠금 없음
    assert g.lock_scope(None, "9.9.9.9", now=1000 + 601) is None  # 창이 지나면 풀린다
    assert g.failure(None, "9.9.9.9", now=1000 + 700).started == ()  # 풀린 뒤 새로 센다
    # 계정·IP 가 같은 실패에서 함께 걸리면 둘 다 알린다
    both = LoginGuard(LockoutPolicy(account_failures=2, ip_failures=2))
    both.failure("guest:team", "7.7.7.7", now=1)
    assert both.failure("guest:team", "7.7.7.7", now=2).started == ("account", "ip")
    assert both.lock_scope("guest:team", "7.7.7.7", now=3) == "account"  # 계정 먼저


def test_slowdown_start_is_reported_once_with_the_failure_count():
    g = LoginGuard(LockoutPolicy(global_failures=3, global_delay_sec=2.0, ip_failures=100))
    outcomes = [g.failure(None, None, now=10 + i) for i in range(6)]
    assert [o.slowdown_started for o in outcomes] == [False, False, False, True, False, False]
    assert outcomes[3].failures == 4
    assert g.failure(None, None, now=10 + 700).slowdown_started is False  # 창이 지나 다시 0 부터


def test_lock_log_lines_carry_kind_scope_ip_only():
    policy = LockoutPolicy(global_delay_sec=2.0)
    started = ap.FailureOutcome(started=("account", "ip"), slowdown_started=True, failures=51)
    lines = ap.lock_log_lines("guest", "5.5.5.5", blocked=None, outcome=started, policy=policy)
    assert lines == (
        "api.login.locked kind=guest scope=account ip=5.5.5.5 seconds=600",
        "api.login.locked kind=guest scope=ip ip=5.5.5.5 seconds=600",
        "api.login.slowdown failures=51 delay=2",
    )
    quiet = ap.FailureOutcome(failures=3)
    assert ap.lock_log_lines("token", None, blocked="ip", outcome=quiet, policy=policy) == (
        "api.login.blocked kind=token scope=ip ip=-",
    )
    assert ap.lock_log_lines("staff", "1.1.1.1", blocked=None, outcome=quiet, policy=policy) == ()
