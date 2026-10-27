"""저장소에 사번·비밀번호·해시가 들어오지 않게: data/auth 는 git 추적 대상이 아니다 (레인 A)."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git 없음")


def test_data_auth_is_ignored_and_not_tracked():
    assert "/data/auth/" in (ROOT / ".gitignore").read_text().splitlines()
    tracked = subprocess.run(
        [GIT, "ls-files", "data"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout
    assert "auth" not in tracked
    ignored = subprocess.run(
        [GIT, "check-ignore", "-q", "data/auth/secret"], cwd=ROOT, check=False
    )
    assert ignored.returncode == 0  # 무시 대상


def test_auth_yaml_holds_no_secrets():
    text = (ROOT / "config" / "auth.yaml").read_text()
    for key in ("password", "hash", "hmac"):
        assert f"{key}:" not in text
