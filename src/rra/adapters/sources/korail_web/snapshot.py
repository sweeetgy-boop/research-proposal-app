"""스냅샷 저장 구조 (data/korail_web/, 커밋 금지).

    snapshots/<YYYY-MM-DD>/manifest.jsonl   항목 1건 = 줄 1개 (페이지·게시글; 첨부·이미지는 그 안에)
    snapshots/<YYYY-MM-DD>/snapshot.json    실행 요약 (건수·바이트·보류·설정)
    snapshots/<YYYY-MM-DD>/items/<menu>/<id>.txt   개인정보 제거 뒤 본문
    snapshots/<YYYY-MM-DD>/files/<sha[:2]>/<sha>.<ext>, images/<sha[:2]>/<sha>.<ext>  내용 주소 저장
    index.json                  URL → {sha256, bytes, path, snapshot} (같은 URL 은 다시 받지 않음)

항목 레코드는 비신뢰 텍스트(제목·본문)를 담는다. 파일 이름은 쓰기 전에 정리한다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

MANIFEST = "manifest.jsonl"
SUMMARY = "snapshot.json"
INDEX = "index.json"
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_id(native_id: str) -> str:
    return _ID_SAFE.sub("-", native_id)[:120]


def content_path(kind: str, sha256: str, ext: str) -> str:
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:8] or "bin"
    return f"{kind}/{sha256[:2]}/{sha256}.{ext}"


@dataclass(frozen=True)
class SnapshotDir:
    root: Path  # data/korail_web
    day: str  # YYYY-MM-DD

    @property
    def path(self) -> Path:
        return self.root / "snapshots" / self.day

    @property
    def manifest(self) -> Path:
        return self.path / MANIFEST

    def ensure(self) -> None:
        for sub in ("items", "files", "images"):
            (self.path / sub).mkdir(parents=True, exist_ok=True, mode=0o700)

    def write_bytes(self, rel: str, data: bytes) -> Path:
        target = self.path / rel
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = target.with_suffix(target.suffix + ".part")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        return target

    def write_text(self, rel: str, text: str) -> Path:
        return self.write_bytes(rel, text.encode("utf-8"))

    def append_manifest(self, record: dict[str, Any]) -> None:
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.manifest, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def write_summary(self, data: dict[str, Any]) -> None:
        (self.path / SUMMARY).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )


def list_snapshots(root: Path) -> list[str]:
    base = root / "snapshots"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and _DATE_DIR.match(p.name))


def latest_snapshot(root: Path, *, before: str | None = None) -> SnapshotDir | None:
    days = [d for d in list_snapshots(root) if before is None or d < before]
    if not days:
        return None
    for day in reversed(days):
        if (root / "snapshots" / day / MANIFEST).is_file():
            return SnapshotDir(root, day)
    return None


def read_manifest(snap: SnapshotDir) -> dict[str, dict[str, Any]]:
    """native_id → 레코드 (같은 id 가 여러 줄이면 마지막 줄)."""
    out: dict[str, dict[str, Any]] = {}
    if not snap.manifest.is_file():
        return out
    with open(snap.manifest, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("native_id"), str):
                out[rec["native_id"]] = rec
    return out


def read_summary(snap: SnapshotDir) -> dict[str, Any] | None:
    p = snap.path / SUMMARY
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def load_index(root: Path) -> dict[str, dict[str, Any]]:
    p = root / INDEX
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def save_index(root: Path, index: dict[str, dict[str, Any]]) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = root / (INDEX + ".part")
    tmp.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, root / INDEX)


def item_signature(title: str, posted: str | None, names: list[str]) -> str:
    return hashlib.sha256("\x1f".join([title, posted or "", *sorted(names)]).encode()).hexdigest()[
        :16
    ]


def today_str(today: date | None = None) -> str:
    return (today or date.today()).isoformat()
