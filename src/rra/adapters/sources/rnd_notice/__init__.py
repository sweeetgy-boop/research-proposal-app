"""정부 R&D 사업공고(KAIA·IRIS) 스냅샷 수집·적재 (P2-7)."""

from rra.adapters.sources.rnd_notice.crawler import NoticeConfig, RndNoticeCrawler, SiteSpec
from rra.adapters.sources.rnd_notice.source import RndNoticeSource, normalize_notice

__all__ = ["NoticeConfig", "RndNoticeCrawler", "RndNoticeSource", "SiteSpec", "normalize_notice"]
