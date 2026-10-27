"""P3 ReadImages — 거르기·캐시·JSON 실패→OCR 대체·수치 거부·상한·OCR 없음·dry-run. 페이크만."""

import json

from rra.adapters.vision.store import MemoryVisionStore
from rra.application.usecases.read_images import ReadImages
from rra.domain.rules.image_filter import ImageFilterConfig
from tests.vision_helpers import (
    DIAGRAM_READING,
    TABLE_READING,
    FakeOcr,
    FakeReader,
    banner_image,
    diagram_image,
    icon_image,
    item,
    sha,
    snapshot_of,
    table_image,
)

TABLE_OCR = "구분 | 2023 | 2024\n수송인원 | 1,234만명 | 1,300만명\n증가율 | 3.5% | 5.3%"


def build(snapshot, *, reader, ocr, store=None, cap=2000, **kw):
    return ReadImages(
        snapshot,
        store or MemoryVisionStore(),
        ocr=ocr,
        reader=reader,
        prompt="VISION",
        system="SYSTEM",
        filter_config=ImageFilterConfig(),
        cap=cap,
        clock=iter(range(0, 10_000)).__next__,
        **kw,
    )


async def test_decorations_are_filtered_and_only_content_images_reach_argon():
    table, diagram, icon, banner = table_image(), diagram_image(), icon_image(), banner_image()
    snap = snapshot_of(
        (
            table,
            item(
                table,
                "stat/table.png",
                page_url="https://info.korail.com/stats",
                page_title="수송 통계",
            ),
        ),
        (diagram, item(diagram, "vision/diagram.png", page_title="경영목표")),
        (icon, item(icon, "common/ico_a.png")),
        (banner, item(banner, "main/banner.png")),
    )
    reader = FakeReader([DIAGRAM_READING, TABLE_READING])
    uc = build(snap, reader=reader, ocr=FakeOcr({sha(table): TABLE_OCR}))
    report = await uc()

    assert report.filter.counts == {"kept": 2, "excluded": 2, "name_pattern": 2}
    # 순서: 경영목표(strategy) 가 통계보다 먼저
    assert [c["sha"] for c in reader.calls] == [sha(diagram), sha(table)]
    assert all(c["json_mode"] and c["mime"] == "image/png" for c in reader.calls)
    assert report.status_counts == {"argon": 2} and report.calls == 2
    assert report.summary()["plan"]["expected_calls"] == 2


async def test_same_hash_is_never_called_twice_even_across_runs():
    table = table_image()
    snap = snapshot_of((table, item(table, "a.png")))
    store = MemoryVisionStore()
    reader = FakeReader([TABLE_READING, TABLE_READING])
    uc = build(snap, reader=reader, ocr=FakeOcr(), store=store)
    first = await uc()
    second = await build(snap, reader=reader, ocr=FakeOcr(), store=store)()

    assert len(reader.calls) == 1
    assert first.results[0].cached is False and second.results[0].cached is True
    assert second.results[0].reading.image_type == "표" and second.calls == 0
    assert second.results[0].elapsed_sec == store.readings[sha(table)]["elapsed_sec"]  # 캐시된 시간
    assert second.plan.summary()["cached"] == 1 and second.plan.expected_calls == 0
    assert [r["status"] for r in store.records] == ["argon"]


async def test_argon_failure_or_non_json_falls_back_to_ocr_text_and_logs_class_only():
    table, diagram = table_image(), diagram_image()
    snap = snapshot_of((table, item(table, "a.png")), (diagram, item(diagram, "b.png")))
    reader = FakeReader(["여기 표가 있습니다 (JSON 아님)"], fail_at={1})
    store = MemoryVisionStore()
    uc = build(snap, reader=reader, ocr=FakeOcr({sha(table): TABLE_OCR}), store=store)
    report = await uc()

    by = {r.sha256: r for r in report.results}
    assert by[sha(table)].status == "failed" and by[sha(table)].reading is None
    assert by[sha(table)].ocr.text == TABLE_OCR  # OCR 텍스트는 남는다
    assert by[sha(table)].vision_error.startswith("VisionParseError")
    assert by[sha(diagram)].vision_error == "RuntimeError"
    dumped = json.dumps(store.records + list(store.readings.values()), ensure_ascii=False)
    assert "sk-secret" not in dumped and "upstream" not in dumped
    # 실패도 캐시된다 — 다시 부르지 않는다
    again = await build(snap, reader=FakeReader([TABLE_READING]), ocr=FakeOcr(), store=store)()
    assert again.calls == 0 and {r.status for r in again.results} == {"failed"}


async def test_numbers_missing_from_ocr_are_marked_unconfirmed():
    table = table_image()
    snap = snapshot_of((table, item(table, "a.png")))
    reading = {**TABLE_READING, "summary": "매출 5,600억원 증가"}  # OCR 에 없는 수치
    uc = build(snap, reader=FakeReader([reading]), ocr=FakeOcr({sha(table): TABLE_OCR}))
    report = await uc()
    r = report.results[0]
    assert r.unconfirmed_numbers == ["5,600억원"]
    assert set(r.confirmed_numbers) >= {"1,234", "3.5%", "2023", "2024"}
    assert r.needs_check and report.summary()["unconfirmed_numbers"] == 1


async def test_cap_reached_leaves_rest_as_ocr_only_with_list():
    imgs = [table_image(), diagram_image(), make_variant(3), make_variant(4)]
    snap = snapshot_of(*((d, item(d, f"{i}.png", page_title="비전")) for i, d in enumerate(imgs)))
    reader = FakeReader([TABLE_READING, DIAGRAM_READING, TABLE_READING, TABLE_READING])
    uc = build(snap, reader=reader, ocr=FakeOcr(), cap=2)
    dry = await uc(dry_run=True)
    assert dry.plan.summary() == {
        "planned": 4,
        "cached": 0,
        "expected_calls": 2,
        "ocr_only": 2,
        "photos": 0,
        "cap": 2,
        "groups": {"strategy": 4},
    }
    assert dry.results == [] and reader.calls == []  # dry-run 은 호출 0

    report = await uc()
    assert report.calls == 2 and report.status_counts == {"argon": 2, "ocr_only": 2}
    assert report.ocr_only_hashes == [sha(imgs[2]), sha(imgs[3])]


async def test_without_ocr_engine_pipeline_continues_with_ocr_none():
    table = table_image()
    snap = snapshot_of((table, item(table, "a.png")))
    ocr = FakeOcr(unavailable=True)
    uc = build(snap, reader=FakeReader([TABLE_READING]), ocr=ocr)
    report = await uc()
    r = report.results[0]
    assert r.ocr is None and r.ocr_error == "OcrUnavailable" and r.status == "argon"
    assert r.confirmed_numbers == [] and "1,234" in r.unconfirmed_numbers
    assert ocr.calls == 1  # 한 번 없으면 다시 시도하지 않는다 (두 번째 이미지가 있어도)


async def test_without_reader_everything_is_ocr_only():
    table = table_image()
    snap = snapshot_of((table, item(table, "a.png")))
    uc = build(snap, reader=None, ocr=FakeOcr({sha(table): TABLE_OCR}))
    report = await uc()
    assert report.plan.expected_calls == 0 and report.results[0].status == "ocr_only"
    assert report.results[0].ocr.text == TABLE_OCR


async def test_ocr_results_are_cached_and_reused():
    table = table_image()
    snap = snapshot_of((table, item(table, "a.png")))
    store = MemoryVisionStore()
    ocr = FakeOcr({sha(table): TABLE_OCR})
    await build(snap, reader=None, ocr=ocr, store=store)()
    await build(snap, reader=None, ocr=ocr, store=store)()
    assert ocr.calls == 1 and store.ocr[sha(table)]["ok"] is True


def make_variant(n: int) -> bytes:
    from tests.vision_helpers import make_image

    return make_image(700, 500, [f"표 {n}", f"항목 {n} | {n}00건"])


async def test_photo_by_ocr_cache_skips_argon_and_logs_meta_only():
    """OCR 캐시가 '글자 거의 없음·숫자 없음' 이면 사진 — Argon 호출 0, status photo, 로그는 메타만.
    캐시가 없는 첫 실행에서는 사진으로 보지 않는다(OCR 뒤 판정)."""
    from rra.domain.rules.photo_filter import PhotoRule

    photo = table_image()  # 바이트는 아무거나 — 판정은 OCR 캐시 신호로만
    it = item(
        photo,
        "p.jpg",
        page_url="https://info.korail.com/press",
        page_title="홍보센터 > 보도자료",
        alt="행사 장면",
    )
    snap = snapshot_of((photo, it))
    store = MemoryVisionStore()
    ocr = FakeOcr({sha(photo): "코레일"})
    first = await build(
        snap, reader=FakeReader([TABLE_READING]), ocr=ocr, store=store, photo_rule=PhotoRule()
    )()
    assert first.plan.expected_calls == 1 and first.results[0].status == "argon"
    # OCR 캐시가 생긴 뒤 다른 저장소(판독 캐시 없음)로 다시 계획하면 사진으로 빠진다
    store2 = MemoryVisionStore()
    store2.put_ocr(sha(photo), store.ocr[sha(photo)])
    reader = FakeReader([TABLE_READING])
    second = await build(snap, reader=reader, ocr=ocr, store=store2, photo_rule=PhotoRule())()
    assert second.plan.expected_calls == 0 and second.plan.summary()["photos"] == 1
    assert second.results[0].status == "photo" and reader.calls == []
    logged = [r for r in store2.records if r.get("status") == "photo"]
    assert logged and logged[0]["alt"] == "행사 장면" and "text" not in logged[0]
    # 전략 그룹은 같은 신호라도 사진으로 보지 않는다
    it_s = item(photo, "s.png", page_title="경영목표", page_url="https://info.korail.com/vision")
    third = await build(
        snapshot_of((photo, it_s)),
        reader=FakeReader([TABLE_READING]),
        ocr=ocr,
        store=store2,
        photo_rule=PhotoRule(),
    )()
    assert third.plan.expected_calls == 1


async def test_concurrency_limits_parallel_calls_and_keeps_priority_order():
    """concurrency=3: 동시에 진행되는 판독이 3을 넘지 않고, 결과는 우선순위 순서 그대로."""
    import asyncio as _asyncio

    from tests.vision_helpers import make_image

    class SlowReader(FakeReader):
        def __init__(self):
            super().__init__([TABLE_READING] * 8)
            self.active = self.max_active = 0

        async def read_image(self, *a, **kw):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await _asyncio.sleep(0.01)
            self.active -= 1
            return await super().read_image(*a, **kw)

    imgs = [make_image(700, 500, [f"표 {n}", f"항목 {n} | {n}00건"]) for n in range(8)]
    pairs = [(b, item(b, f"t{n}.png", page_title="경영목표")) for n, b in enumerate(imgs)]
    reader = SlowReader()
    uc = build(snapshot_of(*pairs), reader=reader, ocr=FakeOcr(), concurrency=3)
    report = await uc()
    assert 1 < reader.max_active <= 3
    assert [r.sha256 for r in report.results] == [p[1].sha256 for p in pairs]
    assert report.calls == 8 and all(r.status == "argon" for r in report.results)
