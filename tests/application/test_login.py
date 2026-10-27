"""로그인 유스케이스 (레인 A) — fake 저장소. 실패 메시지는 하나, 잠금·지연은 정책대로."""

import hashlib

import pytest

from rra.application.ports import AuthStorePort
from rra.application.usecases.login import Login, LoginFailed
from rra.domain.rules.auth_policy import LOGIN_FAILED_MESSAGE, LockoutPolicy, LoginGuard


class FakeAuthStore:
    def __init__(self, staff=(), guest=None):
        self._staff = set(staff)
        self._guest = guest  # (id, password) | None

    def verify_staff(self, staff_no):
        if not self._staff or staff_no not in self._staff:
            return None
        return hashlib.sha256(staff_no.encode()).hexdigest()  # 사번마다 다른 가명

    def staff_enabled(self):
        return bool(self._staff)

    def verify_guest(self, guest_id, password):
        return self._guest is not None and (guest_id, password) == self._guest

    def guest_id(self):
        return self._guest[0] if self._guest else None

    def add_staff(self, staff_no):
        self._staff.add(staff_no)
        return True

    def remove_staff(self, staff_no):
        self._staff.discard(staff_no)
        return True

    def staff_count(self):
        return len(self._staff)

    def set_guest(self, guest_id, password):
        self._guest = (guest_id, password)

    def disable_guest(self):
        self._guest = None
        return True

    def status(self):
        return {"staff_count": len(self._staff), "guest": self._guest is not None, "secret": True}


def test_fake_store_satisfies_port():
    assert isinstance(FakeAuthStore(), AuthStorePort)


def test_staff_login_registered_vs_unregistered_same_message():
    login = Login(FakeAuthStore(staff={"K-100"}), clock=lambda: 10.0)
    ok = login.staff("K-100", ip="1.1.1.1")
    expected = "staff:" + hashlib.sha256(b"K-100").hexdigest()[:12]
    assert ok.principal.kind == "staff" and ok.principal.id == expected
    with pytest.raises(LoginFailed) as exc:
        login.staff("K-999", ip="1.1.1.1")
    assert str(exc.value) == LOGIN_FAILED_MESSAGE
    assert login.status() == {"staff_enabled": True, "guest_enabled": False}


def test_staff_login_disabled_when_list_is_empty():
    login = Login(FakeAuthStore(staff=()), clock=lambda: 10.0)
    with pytest.raises(LoginFailed):
        login.staff("K-100")
    assert login.status()["staff_enabled"] is False


def test_guest_login_success_failure_and_case_folding():
    login = Login(FakeAuthStore(guest=("team", "pw-secret-1")), clock=lambda: 10.0)
    assert login.guest("Team", "pw-secret-1").principal.id == "guest:team"
    for bad in (("team", "wrong"), ("other", "pw-secret-1"), ("team", "")):
        with pytest.raises(LoginFailed) as exc:
            login.guest(*bad)
        assert str(exc.value) == LOGIN_FAILED_MESSAGE


def test_account_lockout_blocks_even_the_right_password_and_ip_lockout():
    now = [100.0]
    login = Login(FakeAuthStore(guest=("team", "pw-secret-1")), clock=lambda: now[0])
    for _ in range(5):
        with pytest.raises(LoginFailed):
            login.guest("team", "nope", ip="5.5.5.5")
    with pytest.raises(LoginFailed):  # 잠금 — 맞는 비밀번호도 거부
        login.guest("team", "pw-secret-1", ip="5.5.5.5")
    now[0] += 601
    assert login.guest("team", "pw-secret-1", ip="5.5.5.5").principal.kind == "guest"
    login2 = Login(FakeAuthStore(staff={"K-1"}), clock=lambda: 50.0)
    for i in range(20):
        with pytest.raises(LoginFailed):
            login2.staff(f"NO-{i}", ip="6.6.6.6")
    with pytest.raises(LoginFailed):  # IP 잠금 — 등록된 사번도 그 IP 에서는 거부
        login2.staff("K-1", ip="6.6.6.6")
    assert login2.staff("K-1", ip="6.6.6.7").principal.kind == "staff"


def test_global_failure_flood_adds_delay_to_the_result():
    policy = LockoutPolicy(global_failures=3, global_delay_sec=2.0, ip_failures=100)
    login = Login(FakeAuthStore(staff={"K-1"}), guard=LoginGuard(policy), clock=lambda: 1.0)
    for i in range(4):
        with pytest.raises(LoginFailed):
            login.staff(f"NO-{i}", ip=f"10.0.0.{i}")
    with pytest.raises(LoginFailed) as exc:
        login.staff("NO-x", ip="10.0.0.9")
    assert exc.value.delay_sec == 2.0
    assert login.staff("K-1", ip="10.0.0.9").delay_sec == 2.0  # 성공에도 지연
