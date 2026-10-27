"""NTIS 국가R&D 연구보고서 검색(rresearchpdf) — SourcePort. 선행연구·섹션 근거용

(doc_type="report").

형식은 공개 매뉴얼 "국가R&D 연구보고서 검색 서비스"(2021-12-28): 파라미터
query·searchField·startPosition·displayCount· returnType=xml, 레코드 HIT, 필드
TermSn·PublicationYear|PublicationYm·ResearchPublicNo·PublicationAgency·
ResultTitle/Korean·Abstract/Korean·Keyword/Korean·DocUrl·ProjectNumber·ProjectTitle·LeadAgency|ManageAgency.
ManagerName/Manager(연구책임자)는 읽지 않는다. 같은 보고서가 ScienceON(REPORT, doc_type
internal_report)에도 있으면 domain/rules/dedup.report_identity(과제번호+제목) 로 하나만 남는다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient, RequestBudgetExceeded
from rra.adapters.sources._orgs import org_tags
from rra.adapters.sources.ntis.client import MAX_QUERY_CHARS, NtisClient, NtisError, total_hits
from rra.adapters.sources.ntis.projects import parse_date, pick, split_list
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.ntis")

KIND = "national_rnd_report"
FIELDS: dict[str, tuple[str, ...]] = {
    "id": ("TermSn", "ResearchPublicNo"),
    "report_no": ("ResearchPublicNo",),
    "title": ("ResultTitle/Korean", "ResultTitle/English", "ResultTitle"),
    "abstract": ("Abstract/Korean", "Abstract/English", "Abstract"),
    "keywords": ("Keyword/Korean", "Keyword"),
    "contents": ("Contents",),
    "year": ("PublicationYear", "PublicationYm"),
    "publisher": ("PublicationAgency",),
    "lead_agency": ("LeadAgency", "ManageAgency"),
    "url": ("DocUrl", "NrmsUrl"),
    "project_no": ("ProjectNumber",),
    "project_title": ("ProjectTitle",),
    "language": ("PublicationLanguage",),
}
MAX_TITLE_CHARS = 500
MAX_TEXT_CHARS = 8000
_ID = re.compile(r"^[0-9A-Za-z_-]{4,40}$")
_PROJECT_NO = re.compile(r"^[0-9A-Za-z_-]{4,40}$")


def _year_date(value: str) -> date | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 8:
        return parse_date(digits[:8])
    if len(digits) >= 6:
        try:
            return date(int(digits[:4]), max(1, min(12, int(digits[4:6]))), 1)
        except ValueError:
            return None
    if len(digits) == 4:
        return date(int(digits), 1, 1)
    return None


def normalize_report(raw: Mapping[str, Any], institutions: Sequence[Mapping[str, Any]]) -> Document:
    native = pick(raw, FIELDS["id"])
    if not _ID.match(native):
        raise ValueError("NTIS 보고서 성과번호가 없거나 형식이 다릅니다.")
    title = pick(raw, FIELDS["title"])[:MAX_TITLE_CHARS]
    if not title:
        raise ValueError(f"ntis:{native} 보고서명 없음")
    url = pick(raw, FIELDS["url"])
    project_no = pick(raw, FIELDS["project_no"])
    org_names = [n for n in (pick(raw, FIELDS["lead_agency"]), pick(raw, FIELDS["publisher"])) if n]
    language = pick(raw, FIELDS["language"]).lower()
    return Document(
        doc_id=f"ntis:{native}",
        source="ntis",
        doc_type="report",
        title=title,
        abstract=pick(raw, FIELDS["abstract"])[:MAX_TEXT_CHARS] or None,
        pub_date=_year_date(pick(raw, FIELDS["year"])),
        orgs=org_tags(org_names, institutions),
        authors=[],  # 연구책임자 이름은 저장하지 않는다
        lang="en" if language.startswith("eng") else "ko",
        url=url if url.startswith("https://") else None,
        text_basis="abstract",
        visibility="public",
        toc=[t for t in split_list(pick(raw, FIELDS["contents"]))][:40] or None,
        codes=split_list(pick(raw, FIELDS["keywords"]))[:20],
        raw={
            "kind": KIND,
            "report_no": pick(raw, FIELDS["report_no"]) or None,
            "project_no": project_no if _PROJECT_NO.match(project_no) else None,
            "project_title": pick(raw, FIELDS["project_title"]) or None,
            "orgs_named": org_names,
            "year": pick(raw, FIELDS["year"])[:4] or None,
        },
    )


class NtisReportSource:
    source = "ntis"

    def __init__(
        self,
        client: GuardedClient,
        *,
        apprv_key: SecretStr,
        base_url: str,
        report_path: str,
        queries: list[str],
        institutions: Sequence[Mapping[str, Any]],
        search_field: str = "BI",
        display_count: int = 100,
        record_tag: str | None = None,
        per_query_limit: int | None = None,
    ):
        self.api = NtisClient(client, apprv_key=apprv_key, base_url=base_url)
        self.path = report_path
        self.queries = queries
        self.institutions = list(institutions)
        self.search_field = search_field if search_field.isalnum() else "BI"
        self.display_count = max(1, min(display_count, 100))
        self.record_tag = record_tag or None
        self.per_query_limit = per_query_limit

    def __repr__(self) -> str:
        return "NtisReportSource()"

    async def aclose(self) -> None:
        await self.api.aclose()

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        if not self.record_tag:
            raise NtisError("config/sources.yaml ntis.record_tag 가 비어 있습니다.")
        if limit <= 0:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in [query] if query else list(self.queries):
            start, taken = 1, 0
            while len(out) < limit and (
                self.per_query_limit is None or taken < self.per_query_limit
            ):
                try:
                    root = await self._fetch_root(q, start, count=self.display_count)
                except RequestBudgetExceeded:
                    logger.warning("ntis.reports.budget_exhausted collected=%d", len(out))
                    return out[:limit]
                records = [_xml.flatten(r) for r in _xml.find_records(root, self.record_tag)]
                for r in records:
                    key = r.get("TermSn") or r.get("ResearchPublicNo") or ""
                    if key and key in seen:
                        continue
                    seen.add(key)
                    out.append(r)
                    taken += 1
                start += self.display_count
                if len(records) < self.display_count or start > total_hits(root):
                    break
        return out[:limit]

    async def probe(self) -> dict[str, Any]:
        root = await self._fetch_root(self.queries[0] if self.queries else "철도", 1, count=5)
        return {
            "total": total_hits(root) or None,
            "record_tag_candidates": sorted({_xml.local(r.tag) for r in _xml.find_records(root)}),
        }

    async def _fetch_root(self, query: str, start: int, *, count: int) -> Any:
        return await self.api.get_xml(
            self.path,
            {
                "collection": "researchpdf",
                "query": query.strip()[:MAX_QUERY_CHARS],
                "searchField": self.search_field,
                "startPosition": str(start),
                "displayCount": str(count),
                "returnType": "xml",
            },
        )

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_report(raw, self.institutions)
