"""공사 홈페이지(info.korail.com) 스냅샷 수집·적재 (레인 A, 2026-10-27).

crawler  — 탐색·내려받기 (`rra crawl korail`), 스냅샷은 data/korail_web/snapshots/<날짜>/
source   — 스냅샷 → Document (SourcePort `korail_web`), 첨부는 샌드박스 파싱
"""

from rra.adapters.sources.korail_web.crawler import (
    CrawlConfig,
    CrawlReport,
    KorailWebCrawler,
    MenuSpec,
)
from rra.adapters.sources.korail_web.source import KorailWebSource, normalize_korail_item

__all__ = [
    "CrawlConfig",
    "CrawlReport",
    "KorailWebCrawler",
    "KorailWebSource",
    "MenuSpec",
    "normalize_korail_item",
]
