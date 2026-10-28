"""deploy/launchd plist 5종 — 라벨·바인딩·비밀 없음·일정·백업 7벌·야간 적재·터널 (파일만)."""

import plistlib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
PLISTS = {
    "com.rra.api": ROOT / "deploy/launchd/com.rra.api.plist",
    "com.rra.mlx": ROOT / "deploy/launchd/com.rra.mlx.plist",
    "com.rra.backup": ROOT / "deploy/launchd/com.rra.backup.plist",
    "com.rra.ingest": ROOT / "deploy/launchd/com.rra.ingest.plist",
    "com.rra.tunnel": ROOT / "deploy/launchd/com.rra.tunnel.plist",
    "com.rra.awake": ROOT / "deploy/launchd/com.rra.awake.plist",
}
TUNNEL_EXAMPLE = ROOT / "deploy/cloudflared/config.example.yml"
SECRET_NAMES = ("TOKEN", "KEY", "MAC", "CLIENT_ID", "PASSWORD")
PUBLIC_HOST = "rra.ai-edu-lab.co.kr"


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


def test_tunnel_plist_runs_named_tunnel_from_config_without_secrets():
    """터널 plist: `cloudflared tunnel --config …/config.yml run rra`, 상시, 비밀 없음."""
    data = load("com.rra.tunnel")
    args = data["ProgramArguments"]
    assert args[0].endswith("/cloudflared") and args[1] == "tunnel" and args[-2:] == ["run", "rra"]
    assert args[args.index("--config") + 1].endswith("/.cloudflared/config.yml")
    assert "--token" not in args and not any(".json" in a or "cert.pem" in a for a in args)
    assert "--url" not in args  # quick tunnel(임의 공개 주소) 금지 — 이름 있는 터널만
    assert data["KeepAlive"] == {"SuccessfulExit": False} and data["RunAtLoad"] is True
    text = PLISTS["com.rra.tunnel"].read_text(encoding="utf-8")
    assert "0.0." + "0.0" not in text  # 모든 인터페이스 바인딩 문자열 금지


def test_tunnel_example_config_routes_public_host_to_loopback_only():
    """config.example.yml: 공개 호스트 1개 → 127.0.0.1:8000, 마지막은 404, ID 는 자리표시자."""
    text = TUNNEL_EXAMPLE.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    assert cfg["tunnel"] == "<TUNNEL_ID>" and "<TUNNEL_ID>.json" in cfg["credentials-file"]
    rules = cfg["ingress"]
    assert rules[-1] == {"service": "http_status:404"}
    named = [r for r in rules[:-1] if "hostname" in r]
    assert [r["hostname"] for r in named] == [PUBLIC_HOST]
    assert all(r["service"].startswith("http://127.0.0.1:") for r in named)
    assert "8501" not in text  # Streamlit 은 공개하지 않는다
    assert "api_token" not in text.lower() and "-----BEGIN" not in text


def test_awake_plist_keeps_caffeinate_running():
    """[1] 맥 항상 켜짐 — /usr/bin/caffeinate -dimsu 를 RunAtLoad·KeepAlive 로."""
    data = load("com.rra.awake")
    assert data["ProgramArguments"] == ["/usr/bin/caffeinate", "-dimsu"]
    assert data["RunAtLoad"] is True and data["KeepAlive"] is True

