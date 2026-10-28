"""문서 표시 (ADR 0040) — 내부 번호 대신 제목·자료원 이름. 검토 의견 글의 번호 바꾸기."""

import re
from pathlib import Path
from types import SimpleNamespace

from rra.domain.models.document import SourceType
from rra.domain.rules.doc_refs import (
    SOURCE_NAMES,
    doc_ref,
    has_internal_id,
    replace_internal_ids,
    source_name,
)

ROOT = Path(__file__).resolve().parents[2]


def test_source_names_cover_every_source_and_match_the_web_table():
    from typing import get_args

    assert set(get_args(SourceType)) <= set(SOURCE_NAMES)
    ts = (ROOT / "web/src/lib/docRefs.ts").read_text(encoding="utf-8")
    block = ts.split("export const SOURCE_NAMES", 1)[1].split("};", 1)[0]
    web = dict(re.findall(r'^\s*([a-z_0-9]+):\s*"([^"]+)",', block, re.M))
    assert web == SOURCE_NAMES
    assert source_name("korail_web") == "공사 홈페이지" and source_name("x") == "수집 자료"


def test_doc_ref_hides_url_of_internal_documents():
    ref = doc_ref("own:2023-01", "궤도 과제", url="https://x", visibility="internal")
    assert ref == {
        "doc_id": "own:2023-01",
        "title": "궤도 과제",
        "source": "own",
        "source_label": "사내 과제",
        "url": None,
    }
    assert doc_ref("molit:1", None, url="https://m")["title"] == "제목 없는 자료"
    assert doc_ref("molit:1", "계획", url="https://m")["url"] == "https://m"


def test_replace_internal_ids_in_review_text():
    titles = {"own:2023-01": "궤도 점검 과제", "alio:sum-0f3a12ab": "알리오 요약"}
    sections = {"method": "연구방법", "objective": "연구목표"}
    cases = {
        "근거 [own:2023-01#3] 와 다름": "근거 「궤도 점검 과제」 와 다름",
        "출처(근거: alio:sum-0f3a12ab#1)를 보면": "출처「알리오 요약」를 보면",
        "ntis:1711234 과제와 겹침": "관련 자료 과제와 겹침",
        "그림 f:method:t1 은 3단계, f:objective:2": (
            "연구방법 분석 기법 그림 1 은 3단계, 연구목표 그림 2"
        ),
        "s:objective:0 문장이 길다": "연구목표 문장 1 문장이 길다",
        "sum-0f3a12ab 참고": "「알리오 요약」 참고",
        "(doc_id: openalex:W123#0) 인용": "인용",
    }
    for raw, want in cases.items():
        got = replace_internal_ids(raw, titles, section_titles=sections)
        assert got == want and not has_internal_id(got)


def test_review_payload_maps_ids_in_comments_and_carries_evidence_refs():
    from rra.domain.models.review import ReviewComment, ReviewRound, ReviewTransfer
    from rra.entrypoints.views import review_payload

    review = ReviewRound(
        round=1,
        draft_version=1,
        created_at="2026-10-28T00:00:00Z",
        transfer=ReviewTransfer(provider="gemini", model="m"),
        comments=[
            ReviewComment(
                id="c1",
                section="method",
                sentence=0,
                issue_type="근거",
                comment="[own:2023-01#3] 와 그림 f:method:t1 이 어긋남",
                revised_text="고친 문장임.",
                evidence=["own:2023-01#3"],
            )
        ],
    )
    cites = [
        SimpleNamespace(
            id="own:2023-01#3",
            doc_id="own:2023-01",
            title="궤도 점검 과제",
            source="own",
            url=None,
            visibility="internal",
        )
    ]
    out = review_payload(review, citations=cites, section_titles={"method": "연구방법"})
    c = out["comments"][0]
    assert c["comment"] == "「궤도 점검 과제」 와 연구방법 분석 기법 그림 1 이 어긋남"
    assert c["evidence_refs"][0]["title"] == "궤도 점검 과제"
    assert c["evidence_refs"][0]["source_label"] == "사내 과제"
