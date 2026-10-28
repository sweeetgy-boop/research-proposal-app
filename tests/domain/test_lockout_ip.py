"""auth_policy.lockout_ip — 접속자를 모르는 주소는 IP 별 잠금 키가 없다."""

import pytest

from rra.domain.rules.auth_policy import lockout_ip


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 100.64.0.5 ", "100.64.0.5"),
        ("2001:db8::1", "2001:db8::1"),
        ("127.0.0.1", None),
        ("127.0.0.2", None),
        ("::1", None),
        ("0.0.0.0", None),  # noqa: S104 — 바인딩 아님, 입력값
        ("", None),
        (None, None),
        ("unknown", None),
        ("evil; DROP", None),
    ],
)
def test_lockout_ip(ip, expected):
    assert lockout_ip(ip) == expected
