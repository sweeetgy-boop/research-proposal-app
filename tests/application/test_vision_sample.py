"""P3 ⑦ 측정 harness — 종류별 표본 상한, 요약표(구조화·숫자 대조·시간·호출 수)."""

from rra.application.usecases.vision_sample import OCR_ONLY_TYPE, build_sample
from rra.domain.models.vision import ImageReadResult, OcrLine, OcrResult, VisionReading
from tests.vision_helpers import DIAGRAM_READING, TABLE_READING, item, make_image


def res(
    n: int,
    reading: dict | None,
    *,
    status="argon",
    cached=False,
    confirmed=(),
    unconfirmed=(),
    sec=1.0,
):
    data = make_image(300 + n, 200, [str(n)])
    return ImageReadResult(
        sha256=item(data, f"{n}.png").sha256,
        status=status,
        item=item(data, f"{n}.png"),
        ocr=OcrResult(lines=[OcrLine(text=f"줄 {n}", confidence=0.9)]),
        reading=VisionReading(**reading) if reading else None,
        confirmed_numbers=list(confirmed),
        unconfirmed_numbers=list(unconfirmed),
        cached=cached,
        elapsed_sec=sec,
    )


def test_summary_table_and_per_type_cap():
    results = [
        res(1, TABLE_READING, confirmed=["1,234만명", "3.5%"], unconfirmed=["5.3%"], sec=2.0),
        res(2, {**TABLE_READING, "structure": {}}, cached=True, sec=1.0),
        res(3, DIAGRAM_READING, confirmed=["2030년"], sec=3.0),
        res(4, None, status="failed", sec=0.5),
        res(5, None, status="ocr_only", sec=0.2),
    ]
    report = build_sample(results, per_type=1)
    rows = {r["image_type"]: r for r in report.table()}
    assert rows["표"] == {
        "image_type": "표",
        "count": 2,
        "structure_rate": 50.0,
        "number_rate": 66.7,
        "sec_per_image": 1.5,
        "calls": 1,
    }
    assert rows["체계도·조직도·흐름도"]["number_rate"] == 100.0
    assert rows[OCR_ONLY_TYPE] == {
        "image_type": OCR_ONLY_TYPE,
        "count": 2,
        "structure_rate": 0.0,  # failed 1건 시도, 구조화 0
        "number_rate": None,
        "sec_per_image": 0.35,
        "calls": 1,
    }
    assert len(report.entries["표"]) == 1 and report.entries["표"][0]["argon"]["image_type"] == "표"
    assert report.entries["표"][0]["ocr_text"] == "줄 1"
    files = report.files()
    assert set(files) == {
        "summary.md",
        "summary.json",
        "table.json",
        "diagram.json",
        "ocr_only.json",
    }
    assert "| 표 | 2 | 50.0 | 66.7 | 1.5 | 1 |" in files["summary.md"]
