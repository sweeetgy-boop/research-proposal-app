"""가짜 실시간 검색 자료원 ([4], RRA_FAKE_LLM=1) — 네트워크 없이 자료원마다 정해진 문서 2건.

웹 개발자가 POST /v1/precheck 의 live_search·live 배지를 키 없이 볼 수 있게 한다. NTIS 는
과제 1건 + 보고서 1건(과제는 ② 유사과제 후보, 보고서는 관련 연구).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rra.domain.models import Document

_DOCS: dict[str, list[dict[str, Any]]] = {
    "scienceon": [
        {
            "doc_id": "scienceon:FAKE-LIVE-1",
            "doc_type": "paper",
            "title": "궤도 틀림 자동 검측 알고리즘 연구 (가짜 실시간)",
            "abstract": "궤도 틀림을 영상으로 자동 검측하는 알고리즘을 제안한다.",
        },
        {
            "doc_id": "scienceon:FAKE-LIVE-2",
            "doc_type": "patent",
            "title": "궤도 상태 감지 장치 (가짜 실시간)",
            "abstract": "궤도 상태를 감지하는 센서 장치.",
        },
    ],
    "ntis": [
        {
            "doc_id": "ntis:FAKELIVE001",
            "doc_type": "rnd_project",
            "title": "궤도 상태 실시간 감지 기술 개발 (가짜 실시간)",
            "abstract": "궤도 상태를 실시간으로 감지하는 국가 R&D 과제.",
        },
        {
            "doc_id": "ntis:FAKELIVE002",
            "doc_type": "report",
            "title": "궤도 유지보수 효율화 연구 보고서 (가짜 실시간)",
            "abstract": "궤도 유지보수 효율화에 관한 연구 보고서.",
        },
    ],
    "openalex": [
        {
            "doc_id": "openalex:W1000000001",
            "doc_type": "paper",
            "title": "Automatic track geometry defect detection (fake live)",
            "abstract": "We detect track geometry defects automatically from images.",
            "lang": "en",
        },
        {
            "doc_id": "openalex:W1000000002",
            "doc_type": "paper",
            "title": "Railway track condition monitoring review (fake live)",
            "abstract": "A review of railway track condition monitoring methods.",
            "lang": "en",
        },
    ],
}


class FakeLiveSource:
    def __init__(self, source: str, lang: str):
        self.source = source
        self.lang = lang

    async def fetch(self, queries: list[str], limit: int) -> list[Document]:
        return [
            Document(
                source=self.source,  # type: ignore[arg-type]
                text_basis="abstract",
                pub_date=date(2026, 1, 1),
                **spec,
            )
            for spec in _DOCS[self.source][:limit]
        ]


class FakeKeywordLLM:
    """가짜 키워드 LLM — 정해진 국문·영문 키워드 JSON (Argon 자리)."""

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False) -> str:
        return (
            '{"ko": ["궤도 상태 감지", "궤도 틀림 검측", "궤도 유지보수"], '
            '"en": ["track condition monitoring", "track geometry defect", "railway track"]}'
        )


def fake_live_sources() -> dict[str, FakeLiveSource]:
    return {
        "scienceon": FakeLiveSource("scienceon", "ko"),
        "ntis": FakeLiveSource("ntis", "ko"),
        "openalex": FakeLiveSource("openalex", "en"),
    }
