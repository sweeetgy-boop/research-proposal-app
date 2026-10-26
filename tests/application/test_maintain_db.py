"""DB 유지보수 유스케이스 — 재색인 위임, 백업 이름·보관 회전(keep)."""

from datetime import datetime
from pathlib import Path

from rra.application.ports import DatabaseMaintenancePort
from rra.application.usecases.maintain_db import BackupDatabase, ReindexDocuments


class FakeMaintenance:
    def __init__(self):
        self.reindexed = 0
        self.backups: list[Path] = []

    async def reindex(self):
        self.reindexed += 1
        return {"chunks": 3, "dim": 32, "model": "fake"}

    async def backup(self, out):
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sqlite")
        self.backups.append(path)
        return path


def test_fake_satisfies_port():
    assert isinstance(FakeMaintenance(), DatabaseMaintenancePort)


async def test_reindex_delegates():
    db = FakeMaintenance()
    assert await ReindexDocuments(db)() == {"chunks": 3, "dim": 32, "model": "fake"}
    assert db.reindexed == 1


async def test_backup_into_directory_names_by_clock_and_keeps_only_recent(tmp_path):
    db = FakeMaintenance()
    ticks = iter(datetime(2026, 10, d, 3, 30) for d in range(1, 11))
    backup = BackupDatabase(db, clock=lambda: next(ticks))
    (tmp_path / "other.sqlite").write_bytes(b"x")  # 규칙 밖 파일은 건드리지 않는다
    reports = [await backup(tmp_path, keep=7) for _ in range(10)]
    assert reports[0].path.name == "rra-20261001-033000.sqlite"
    names = sorted(p.name for p in tmp_path.glob("rra-*.sqlite"))
    assert len(names) == 7 and names[0] == "rra-20261004-033000.sqlite"
    assert [p.name for p in reports[-1].removed] == ["rra-20261003-033000.sqlite"]
    assert len(reports[-1].kept) == 7 and (tmp_path / "other.sqlite").exists()


async def test_backup_to_explicit_file_does_not_rotate(tmp_path):
    db = FakeMaintenance()
    report = await BackupDatabase(db)(tmp_path / "snap.sqlite", keep=1)
    assert report.path == tmp_path / "snap.sqlite" and report.removed == [] and report.kept == []


async def test_keep_zero_disables_rotation(tmp_path):
    db = FakeMaintenance()
    backup = BackupDatabase(db, clock=lambda: datetime(2026, 10, 26, 3, 30))
    report = await backup(tmp_path, keep=0)
    assert report.removed == [] and report.path.exists()
