"""배포 버전 읽기 — version.json 우선, 없으면 git HEAD, 둘 다 없으면 unknown. 비밀 없음."""

import json
from datetime import UTC, datetime

from rra.adapters.deploy import read_version

NOW = datetime(2026, 10, 28, 0, 34, tzinfo=UTC)


def test_version_file_wins_and_is_sanitized(tmp_path):
    path = tmp_path / "deploy" / "version.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "commit": "D65D75B789A117851F9DDFA57D42A46C4E4A9275",
                "deployed_at": "2026-10-28T09:34:13+09:00",
                "prs": ["#61", 62, {"bad": 1}],
                "token": "should-not-pass",
            }
        )
    )
    info = read_version(path, repo_root=tmp_path, now=NOW)
    assert info == {
        "commit": "d65d75b789a117851f9ddfa57d42a46c4e4a9275",
        "short": "d65d75b",
        "deployed_at": "2026-10-28T09:34:13+09:00",
        "prs": ["#61", "62"],
        "source": "deploy",
    }


def test_falls_back_to_git_head_then_unknown(tmp_path, monkeypatch):
    missing = tmp_path / "none.json"
    (tmp_path / "bad.json").write_text("{not json")
    monkeypatch.setattr("rra.adapters.deploy.version._git_head", lambda root: "abc1234def")
    info = read_version(missing, repo_root=tmp_path, now=NOW)
    assert info["source"] == "git" and info["short"] == "abc1234" and info["prs"] == []
    assert info["deployed_at"].startswith("2026-10-28")
    assert read_version(tmp_path / "bad.json", repo_root=tmp_path, now=NOW)["source"] == "git"
    monkeypatch.setattr("rra.adapters.deploy.version._git_head", lambda root: "")
    info = read_version(missing, repo_root=tmp_path, now=NOW)
    assert info["source"] == "unknown" and info["commit"] == "" and info["short"] == ""
    assert read_version(missing, now=NOW)["source"] == "unknown"  # repo_root 없음 → git 안 봄
