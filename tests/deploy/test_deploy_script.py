"""tools/deploy.sh — 문법·실행 권한·필수 단계(main 확인, run 확인, kickstart, healthz, 기록)."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "tools/deploy.sh"
BASH = shutil.which("bash") or "/bin/bash"


def test_script_is_executable_and_parses():
    assert os.access(SCRIPT, os.X_OK)
    subprocess.run([BASH, "-n", str(SCRIPT)], check=True)  # noqa: S603 — 고정 인자
    out = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), "--help"], capture_output=True, text=True, check=True
    )
    assert "tools/deploy.sh" in out.stdout


def test_script_contains_required_steps_and_no_secrets():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "git fetch -q origin main",
        "rev-parse origin/main",
        "npm run build",
        "runs active --json",
        "--wait",
        "--force",
        "launchctl kickstart -k",
        "com.rra.api",
        "/healthz",
        "/login",
        "https://rra.taile5afcf.ts.net",
        "docs/history/deploys",
        "pending.md",
        "version.json",
    ):
        assert needle in text, needle
    assert "RRA_API_TOKEN" not in text and "GEMINI" not in text


def test_history_deploys_folder_has_rules_and_pending_list():
    folder = ROOT / "docs/history/deploys"
    assert (folder / "README.md").exists()
    pending = (folder / "pending.md").read_text(encoding="utf-8")
    assert "반영 대기" in pending and "보안 수정" in pending
