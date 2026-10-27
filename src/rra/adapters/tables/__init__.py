"""TableSourcePort 구현 (P2-8) — 스냅샷 첨부(xlsx·xls·pdf), 판독 캐시(표 이미지), DB 문서 본문."""

from rra.adapters.tables.documents import DocumentTables
from rra.adapters.tables.snapshot import SnapshotTables
from rra.adapters.tables.vision import VisionTables

__all__ = ["DocumentTables", "SnapshotTables", "VisionTables"]
