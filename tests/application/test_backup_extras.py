"""`rra db backup` 은 DB 사본 옆에 공사 홈페이지 스냅샷 기록(index.json·manifest.jsonl)도 둔다."""

from datetime import datetime
from pathlib import Path

from rra.application.usecases.maintain_db import BackupDatabase


class _Db:
    async def reindex(self):
        return {}

    async def backup(self, out):
        Path(out).write_bytes(b"sqlite")
        return Path(out)


async def test_backup_copies_extra_files_and_prunes_them_with_old_copies(tmp_path):
    root = tmp_path / "korail_web"
    (root / "snapshots" / "2026-10-27").mkdir(parents=True)
    index = root / "index.json"
    index.write_text("{}")
    manifest = root / "snapshots" / "2026-10-27" / "manifest.jsonl"
    manifest.write_text('{"native_id": "x"}\n')
    ticks = iter([datetime(2026, 10, 27, 3, 30), datetime(2026, 10, 28, 3, 30)])
    backup = BackupDatabase(
        _Db(), clock=lambda: next(ticks), extra_files=[index, manifest, root / "missing"]
    )
    out = tmp_path / "backups"
    out.mkdir()
    first = await backup(out, keep=1)
    assert [p.name for p in first.extras] == [
        "rra-20261027-033000.korail_web.index.json",
        "rra-20261027-033000.2026-10-27.manifest.jsonl",
    ]
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in first.extras)
    second = await backup(out, keep=1)
    assert [p.name for p in second.removed] == ["rra-20261027-033000.sqlite"]
    assert sorted(p.name for p in out.iterdir()) == [
        "rra-20261028-033000.2026-10-27.manifest.jsonl",
        "rra-20261028-033000.korail_web.index.json",
        "rra-20261028-033000.sqlite",
    ]
