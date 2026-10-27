"""NTIS (국가R&D) — 과제검색·연구보고서 검색(SourcePort), 성과검색·연관콘텐츠(부가 조회 포트)."""

from rra.adapters.sources.ntis.client import (
    NtisClient,
    NtisError,
    NtisIpBlocked,
    NtisProjectSource,
)
from rra.adapters.sources.ntis.insights import NtisInsightSource
from rra.adapters.sources.ntis.projects import normalize_project
from rra.adapters.sources.ntis.reports import NtisReportSource, normalize_report

__all__ = [
    "NtisClient",
    "NtisError",
    "NtisIpBlocked",
    "NtisInsightSource",
    "NtisProjectSource",
    "NtisReportSource",
    "normalize_project",
    "normalize_report",
]
