"""deploy/launchd/com.rra.eval.plist — 야간 L1 평가 (ADR 0058): 04:30(백업 뒤), heavy lock 경유,
원 저장소 경로·venv, 비밀 없음, 로그 ~/Library/Logs/rra-eval*."""

import plistlib
from pathlib import Path

ROOT = Path(__file__).parents[2]
PLIST = ROOT / "deploy/launchd/com.rra.eval.plist"
REPO = "/Users/chan/projects/research-proposal-app"
SECRET_NAMES = ("TOKEN", "KEY", "MAC", "CLIENT_ID", "PASSWORD")


def load():
    with PLIST.open("rb") as f:
        return plistlib.load(f)


def test_eval_plist_runs_l1_under_heavy_lock_after_backup():
    data = load()
    assert data["Label"] == "com.rra.eval"
    args = data["ProgramArguments"]
    assert args[0] == f"{REPO}/.venv/bin/python" and args[1] == f"{REPO}/tools/with_heavy_lock.py"
    assert args[2] == "--" and args[3] == f"{REPO}/.venv/bin/python"
    assert args[4:7] == ["-m", "rra.entrypoints.cli_eval", "run"]
    assert args[args.index("--suite") + 1] == "l1"
    assert data["StartCalendarInterval"] == {"Hour": 4, "Minute": 30}  # 백업 03:30 뒤
    assert data["WorkingDirectory"] == REPO


def test_eval_plist_has_no_secrets_and_logs_under_library():
    data = load()
    env = data["EnvironmentVariables"]
    assert not any(any(s in key.upper() for s in SECRET_NAMES) for key in env)
    assert env["RRA_DATA_DIR"] == f"{REPO}/data" and env["RRA_CONFIG_DIR"] == f"{REPO}/config"
    assert env["RRA_HEAVY_LOCK"] == f"{REPO}/runs/.heavy.lock"
    assert all("Logs/rra-eval" in data[k] for k in ("StandardOutPath", "StandardErrorPath"))
    text = PLIST.read_text(encoding="utf-8")
    assert "--sealed" not in text  # 야간은 연습용 묶음 — 봉인 묶음은 최종 확인 1회만
