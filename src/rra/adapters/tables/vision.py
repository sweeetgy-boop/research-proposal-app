"""판독 캐시(P3 vision_cache) 의 표 이미지 → ParsedTable (basis=image_vision).

- `VisionStorePort.cached_hashes()` 의 성공 판독 중 image_type="표" 이고 structure 에 rows 가 있는
  것만.
- doc_id 는 적재 규칙(`link_image_readings`)과 같은 `<source>:img:<sha256 앞 16자>`.
- 적재된 문서가 있고 `raw.image.unconfirmed_numbers` 가 비어 있지 않으면(수치가 OCR 로 확인되지
  않음) 그 표는 통째로 건너뛴다 — 확인 안 된 수치를 근거로 올리지 않는다(보수적).
"""

from __future__ import annotations

from typing import Any

from rra.application.ports.repository import DocumentRepository
from rra.application.ports.vision import VisionStorePort
from rra.domain.models import ParsedTable
from rra.domain.models.vision import VisionReading

DOC_ID_HASH_CHARS = 16
TABLE_TYPE = "표"


class VisionTables:
    name = "vision"

    def __init__(
        self, store: VisionStorePort, repo: DocumentRepository, *, source: str = "korail_web"
    ):
        self.store, self.repo, self.source = store, repo, source
        self.skipped: dict[str, int] = {}

    async def tables(self, *, limit: int | None = None) -> list[ParsedTable]:
        out: list[ParsedTable] = []
        self.skipped = {}
        for sha in sorted(self.store.cached_hashes()):
            if limit is not None and len(out) >= limit:
                break
            cached = self.store.get_reading(sha)
            if not isinstance(cached, dict) or not cached.get("ok"):
                continue
            try:
                reading = VisionReading.model_validate(cached.get("reading") or {})
            except ValueError:
                self._skip("invalid_reading")
                continue
            if reading.image_type != TABLE_TYPE or not isinstance(
                reading.structure.get("rows"), list
            ):
                continue
            doc_id = f"{self.source}:img:{sha[:DOC_ID_HASH_CHARS]}"
            doc = await self.repo.get_document(doc_id)
            if doc is not None:
                image = doc.raw.get("image") if isinstance(doc.raw, dict) else None
                if isinstance(image, dict) and image.get("unconfirmed_numbers"):
                    self._skip("unconfirmed_numbers")
                    continue
                doc_id = doc.doc_id
            table = _structure_table(reading.structure, doc_id, reading.title)
            if table is not None:
                out.append(table)
        return out

    def _skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _structure_table(structure: dict[str, Any], doc_id: str, title: str) -> ParsedTable | None:
    cols = structure.get("cols")
    rows = structure.get("rows")
    grid: list[list[str | None]] = []
    if isinstance(cols, list) and cols:
        grid.append([_cell(c) for c in cols])
    for row in rows or []:
        if isinstance(row, list):
            grid.append([_cell(c) for c in row])
        elif isinstance(row, dict):
            if not grid:
                grid.append([_cell(k) for k in row])
            grid.append([_cell(v) for v in row.values()])
    if len(grid) < 2:
        return None
    units = structure.get("units")
    unit = (
        str(units).strip()[:20]
        if isinstance(units, str | int | float) and str(units).strip()
        else None
    )
    return ParsedTable(
        doc_id=doc_id, rows=grid, title=title[:300] or None, unit=unit, basis="image_vision"
    )


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:480] or None
