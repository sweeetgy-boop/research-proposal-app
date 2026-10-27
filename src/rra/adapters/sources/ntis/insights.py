"""NTIS 성과검색(public_result)·연관콘텐츠 추천(ConnectionContent) 어댑터 —

ProjectOutcomePort·RelatedProjectPort.

형식은 2026-10-27 실응답(tests/fixtures/ntis/ntis_outcome_*.xml·ntis_related_*.json)으로 확정.
- 성과검색: `collection=rpaper|rpatent`, `SRWR=<과제번호>`, `searchFd=BI`, `addQuery=DBT=PAP|PAT`.
  레코드 `HIT NO SITID=PAP|PAT`. 논문 필드 ResultTitle·JournalName·IssnNumber·PubYear|Year·ResultID·
  Abstract/Full·DigitalObjectIdentifier·ProjectID(과제번호)·ProjectTitle·PerformAgency, 특허
  ResultTitle·RegistNumber·Registrant·RegistType(출원|등록)·IprType·Year·ProjectID. 저자(Author)·
  발명자 이름은 읽지 않는다. Registrant 는 기관으로 보일 때만 남긴다.
- 연관콘텐츠: `pjtId=<과제번호>`, `collection=project` → JSON `{PJT_ID, KOR_PJT_NM, exist, count,
  items:[{PJT_ID, KOR_PJT_NM, similarity_score, rank, creat_dt}]}` — Accept 에 json 이 있으면 이
  객체가 JSON 문자열 안에 한 번 더 감싸여 오고(`unwrap_json_string`) `creat_dt` 에 비표준 `NaN`
  이 섞인다.
  정규화(normalize_outcome·normalize_related)는 순수 함수.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from rra.adapters.sources import _xml
from rra.adapters.sources._base import GuardedClient
from rra.adapters.sources._orgs import is_organization
from rra.adapters.sources.ntis.client import NtisClient, NtisError, unwrap_json_string
from rra.adapters.sources.ntis.projects import pick

JSON_TYPES = frozenset({"application/json", "text/json", "text/plain", "text/html", "text/xml"})
OUTCOME_COLLECTIONS: dict[str, tuple[str, str]] = {
    "paper": ("rpaper", "PAP"),
    "patent": ("rpatent", "PAT"),
}
FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("ResultTitle/Korean", "ResultTitle", "Title/Korean", "Title"),
    "year": ("PubYear", "PublicationYear", "Year", "ProjectYear"),
    "journal": ("JournalName", "Journal"),
    "registrant": ("Registrant", "Applicant"),
    "registration_no": ("RegistNumber", "ApplicationNumber", "RegistrationNumber"),
    "result_id": ("ResultID", "ResultId", "TermSn"),
    "project_no": ("ProjectID", "ProjectNumber"),
    "doi": ("DigitalObjectIdentifier", "DOI"),
    "regist_type": ("RegistType",),
}
MAX_ITEMS = 10
# 연결 확인용 과제번호 — 한국철도기술연구원 과제(2026-10-27 실응답: 논문 13·특허 2·연관 10).
# 빈 결과도 정상 응답이지만 건수가 보이는 과제가 진단에 낫다.
PROBE_PROJECT_NO = "1615007833"


def normalize_outcome(kind: str, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    title = pick(raw, FIELDS["title"])
    if not title:
        return None
    if kind == "paper":
        venue = pick(raw, FIELDS["journal"])
    else:
        registrant = pick(raw, FIELDS["registrant"])
        venue = registrant if registrant and is_organization(registrant) else ""
    return {
        "kind": kind,
        "title": title,
        "year": pick(raw, FIELDS["year"])[:4] or None,
        "venue": venue or None,
        "result_id": pick(raw, FIELDS["result_id"]) or None,
        "registration_no": pick(raw, FIELDS["registration_no"]) or None
        if kind == "patent"
        else None,
        "project_no": pick(raw, FIELDS["project_no"]) or None,
        "doi": pick(raw, FIELDS["doi"]) or None if kind == "paper" else None,
        "regist_type": pick(raw, FIELDS["regist_type"]) or None if kind == "patent" else None,
    }


def normalize_related(payload: Any) -> list[dict[str, Any]]:
    """ConnectionContent JSON → [{project_no,title,score,rank}]. 모르는 꼴이면 빈 목록."""
    if isinstance(payload, dict):
        items = payload.get("items")
        if items is None and isinstance(payload.get("RESULT"), dict):
            items = payload["RESULT"].get("items")
    else:
        items = payload
    if not isinstance(items, list):
        return []
    out = []
    for it in items[: MAX_ITEMS * 2]:
        if not isinstance(it, dict):
            continue
        score = it.get("similarity_score")
        out.append(
            {
                "project_no": str(
                    it.get("PJT_ID") or it.get("pjtId") or it.get("ProjectNumber") or ""
                ),
                "title": str(
                    it.get("KOR_PJT_NM") or it.get("title") or it.get("ProjectTitle") or ""
                ),
                "score": score if isinstance(score, int | float) and math.isfinite(score) else None,
                "rank": it.get("rank") if isinstance(it.get("rank"), int) else None,
            }
        )
    return out


class NtisInsightSource:
    """성과검색 + 연관콘텐츠 — 두 포트를 한 객체가 구현한다 (같은 키·같은 클라이언트).

    ProbingSource 도 된다 (`rra sources check --source ntis_insights`): 성과검색(rpaper·rpatent)·
    연관콘텐츠를 과제번호 하나로 1회씩 불러 IP·키 수락 여부를 본다 (레인 I)."""

    source = "ntis_insights"

    def __init__(
        self,
        client: GuardedClient,
        *,
        apprv_key: SecretStr,
        base_url: str,
        outcome_path: str,
        related_path: str,
        record_tag: str = "HIT",
        display_count: int = MAX_ITEMS,
    ):
        self.api = NtisClient(client, apprv_key=apprv_key, base_url=base_url)
        self.outcome_path, self.related_path = outcome_path, related_path
        self.record_tag = record_tag or "HIT"
        self.display_count = max(1, min(display_count, 100))

    async def aclose(self) -> None:
        await self.api.aclose()

    async def probe(self) -> dict[str, Any]:
        """연결 확인 — 성과검색 2회(논문·특허) + 연관콘텐츠 1회. 건수만 (본문·키 없음)."""
        outcomes = await self.outcomes(PROBE_PROJECT_NO)
        related = await self.related(PROBE_PROJECT_NO)
        return {
            "probe_project_no": PROBE_PROJECT_NO,
            "outcomes": len(outcomes),
            "related": len(related),
        }

    async def outcomes(self, project_no: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for kind, (collection, dbt) in OUTCOME_COLLECTIONS.items():
            root = await self.api.get_xml(
                self.outcome_path,
                {
                    "collection": collection,
                    "SRWR": project_no,
                    "searchFd": "BI",
                    "addQuery": f"DBT={dbt}",
                    "startPosition": "1",
                    "displayCnt": str(self.display_count),
                },
            )
            for rec in _xml.find_records(root, self.record_tag):
                item = normalize_outcome(kind, _xml.flatten(rec))
                if item and (item["project_no"] in (None, project_no)):
                    out.append(item)
        return out

    async def related(self, project_no: str) -> list[dict[str, Any]]:
        body = await self.api.get_body(
            self.related_path,
            {"pjtId": project_no, "collection": "project"},
            accept_types=JSON_TYPES,
        )
        try:
            payload = json.loads(unwrap_json_string(body))  # 문자열 안의 JSON 도 (실응답)
        except ValueError as exc:
            raise NtisError("NTIS 연관콘텐츠 응답이 JSON 이 아닙니다.") from exc
        return normalize_related(payload)
