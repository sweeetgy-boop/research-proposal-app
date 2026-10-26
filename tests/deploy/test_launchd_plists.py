"""deploy/launchd plist 4종 — 라벨·바인딩·비밀 없음·일정·백업 보관 7벌·야간 적재 옵션 (파일만)."""

import plistlib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PLISTS = {
    "com.rra.api": ROOT / "deploy/launchd/com.rra.api.plist",
    "com.rra.mlx": ROOT / "deploy/launchd/com.rra.mlx.plist",
    "com.rra.backup": ROOT / "deploy/launchd/com.rra.backup.plist",
    "com.rra.ingest": ROOT / "deploy/launchd/com.rra.ingest.plist",
}
SECRET_NAMES = ("TOKEN", "KEY", "MAC", "CLIENT_ID", "PASSWORD")


def load(name):
    with PLISTS[name].open("rb") as f:
        return plistlib.load(f)


@pytest.mark.parametrize("name", list(PLISTS))
def test_plist_parses_with_label_and_no_secrets(name):
    data = load(name)
    assert data["Label"] == name and data["ProgramArguments"]
    env = data.get("EnvironmentVariables", {})
    assert not any(any(s in key.upper() for s in SECRET_NAMES) for key in env), name
    assert all("Logs/rra-" in data[k] for k in ("StandardOutPath", "StandardErrorPath"))


def test_api_and_mlx_bind_loopback_only():
    for name in ("com.rra.api", "com.rra.mlx"):
        args = load(name)["ProgramArguments"]
        assert "--host" in args and args[args.index("--host") + 1] == "127.0.0.1", name
        assert load(name)["KeepAlive"] == {"SuccessfulExit": False}


def test_backup_rotates_seven_copies_daily_after_ingest():
    backup, ingest = load("com.rra.backup"), load("com.rra.ingest")
    args = backup["ProgramArguments"]
    assert args[1:3] == ["db", "backup"] and args[args.index("--keep") + 1] == "7"
    assert backup["StartCalendarInterval"] == {"Hour": 3, "Minute": 30}
    assert ingest["StartCalendarInterval"] == {"Hour": 2, "Minute": 30}  # 백업보다 먼저


def test_nightly_ingest_covers_all_sources_and_skips_missing_keys():
    args = load("com.rra.ingest")["ProgramArguments"]
    assert args[1] == "ingest" and "--skip-unavailable" in args
    sources = args[args.index("--source") + 1].split(",")
    assert sources[0] == "openalex" and {"scienceon", "ntis", "kipris"} <= set(sources)
    assert {"alio", "alio_summary", "own_projects", "own_docs"} <= set(sources)


async def test_backup_keep_seven_leaves_exactly_seven(tmp_path):
    """plist 의 --keep 7 이 실제로 7벌만 남기는지 (유스케이스 회전)."""
    from datetime import datetime

    from rra.application.usecases.maintain_db import BackupDatabase
    from tests.application.test_maintain_db import FakeMaintenance

    ticks = iter(datetime(2026, 10, 1, 3, 30 + m) for m in range(0, 30))
    backup = BackupDatabase(FakeMaintenance(), clock=lambda: next(ticks))
    for _ in range(9):
        report = await backup(tmp_path, keep=7)
    assert len(report.kept) == 7 and len(list(tmp_path.glob("rra-*.sqlite"))) == 7
    assert report.removed and all(not p.exists() for p in report.removed)
