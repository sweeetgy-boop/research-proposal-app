from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CatalogEntry(BaseModel):
    """알리오 공시 카탈로그 한 행 (공공데이터포털 fileData). 제목은 비신뢰 텍스트."""

    catalog_id: str
    institution_tag: str  # korail / krri / kr
    title: str
    published: date | None = None
    url: str | None = None  # 참고용. 자동 다운로드하지 않는다 (robots.txt)
