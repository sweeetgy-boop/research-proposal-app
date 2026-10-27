"""P3 ⑥ 적재 준비 — 본문이 이김, 개인정보 제거, image_vision + raw.image, 실패는 OCR 만."""

from rra.application.usecases.link_image_readings import compose_text, link_readings
from rra.domain.models import Document
from rra.domain.models.vision import ImageReadResult, OcrLine, OcrResult, VisionReading
from rra.domain.rules.vision_trust import CHECK_MARK
from tests.vision_helpers import DIAGRAM_READING, TABLE_READING, item, make_image

PAGE = Document(
    doc_id="alio:page-1",
    source="alio",
    doc_type="internal_report",
    title="경영목표",
    body="한국철도공사 경영목표 페이지.\n비전: 국민과 함께하는 철도\n담당 부서 안내",
    url="https://info.korail.com/vision",
    orgs=["korail"],
    department="경영기획처",
    visibility="public",
)


def result(
    data: bytes, reading: dict | None, *, status="argon", ocr_text="", **kw
) -> ImageReadResult:
    it = item(data, kw.pop("path", "img/a.png"), page_doc_id="alio:page-1", **kw)
    return ImageReadResult(
        sha256=it.sha256,
        status=status,
        item=it,
        ocr=OcrResult(lines=[OcrLine(text=t, confidence=0.9) for t in ocr_text.splitlines()])
        if ocr_text
        else None,
        reading=VisionReading(**reading) if reading else None,
        **{k: v for k, v in kw.items() if k in ("confirmed_numbers", "unconfirmed_numbers")},
    )


def test_reading_becomes_image_vision_document_with_badge_metadata():
    data = make_image(800, 400, ["표"])
    r = result(data, TABLE_READING, confirmed_numbers=["1,234만명"], unconfirmed_numbers=["5.3%"])
    out = link_readings([r], {"alio:page-1": PAGE})

    assert out.skipped == {} and len(out.documents) == 1
    doc = out.documents[0]
    assert doc.doc_id == f"alio:img:{r.sha256[:16]}" and doc.source == "alio"
    assert doc.text_basis == "image_vision" and doc.doc_type == "web_page"
    assert doc.title == "경영목표 — 수송 실적" and doc.url == "https://info.korail.com/vision"
    assert doc.department == "경영기획처" and doc.visibility == "public"
    meta = doc.raw["image"]
    assert (
        meta["url"] == "https://info.korail.com/img/img/a.png"
        and meta["page_doc_id"] == "alio:page-1"
    )
    assert meta["image_type"] == "표" and meta["unconfirmed_numbers"] == ["5.3%"]
    assert "수송인원 | 1,234만명 | 1,300만명" in doc.body
    assert f"{CHECK_MARK} 증가율 | 3.5% | 5.3%" in doc.body
    assert out.chunks and all(
        c.basis == "image_vision" and c.doc_id == doc.doc_id for c in out.chunks
    )


def test_body_text_wins_over_image_text():
    data = make_image(800, 400, ["체계도"])
    partial = {
        **DIAGRAM_READING,
        "text": "비전: 국민과 함께하는 철도",
        "structure": {},
        "summary": "",
    }
    out = link_readings([result(data, partial)], {"alio:page-1": PAGE})
    assert out.documents == [] and out.skipped == {next(iter(out.skipped)): "body_wins"}

    out2 = link_readings([result(data, DIAGRAM_READING)], {"alio:page-1": PAGE})
    body = out2.documents[0].body
    assert (
        "비전: 국민과 함께하는 철도" not in body.splitlines()[0]
        or body.count("국민과 함께하는 철도") == 1
    )
    assert "목표: 안전 최우선" in body and "전략과제: 디지털 전환" in body


def test_personal_data_is_stripped_from_body_and_title():
    data = make_image(800, 400, ["글"])
    reading = {
        "image_type": "글자 이미지",
        "title": "담당자 김철수 안내",
        "text": "문의 042-615-1234 hong@korail.com\n담당자 경영연구처 박한균",
        "structure": {},
        "summary": "",
    }
    out = link_readings([result(data, reading)], {"alio:page-1": PAGE})
    doc = out.documents[0]
    assert "042" not in doc.body and "hong@" not in doc.body and "박한균" not in doc.body
    assert "경영연구처" in doc.body and "김철수" not in doc.title
    assert out.removed_personal == {"phone": 1, "email": 1, "name": 1}


def test_failed_argon_uses_ocr_text_only_and_no_text_is_skipped():
    data = make_image(800, 400, ["x"])
    ocr_only = result(data, None, status="failed", ocr_text="수송인원 1,234만명\n증가율 3.5%")
    empty = result(make_image(801, 400), None, status="ocr_only", path="img/b.png")
    out = link_readings([ocr_only, empty], {"alio:page-1": PAGE})
    assert len(out.documents) == 1 and out.documents[0].body == "수송인원 1,234만명\n증가율 3.5%"
    assert out.documents[0].raw["image"]["status"] == "failed"
    assert out.skipped == {empty.sha256: "no_text"}
    assert compose_text(empty) == ""


def test_unknown_source_without_page_is_skipped_not_raised():
    data = make_image(800, 400, ["x"])
    r = result(data, TABLE_READING, source="korail_web")
    out = link_readings([r], {})
    assert out.skipped == {r.sha256: "unknown_source"}
    out2 = link_readings([result(data, TABLE_READING, source="own")], {})
    assert out2.documents[0].source == "own" and out2.documents[0].orgs == ["korail"]
