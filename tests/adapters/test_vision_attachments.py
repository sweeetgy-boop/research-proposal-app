"""첨부 속 내장 이미지 추출(P3 확장) — 자식 파서(zip·pptx·xlsx·pdf·hwp 스트림), 중첩 manifest 읽기,
추출기(가짜 러너·실제 격리 자식), 원본 위치 메타."""

import base64
import io
import json
import zipfile
import zlib

import pytest

from rra.adapters.sources._sandbox import SandboxLimits
from rra.adapters.vision._embedded_worker import extract
from rra.adapters.vision.attachments import ExtractAttachmentImages
from rra.adapters.vision.manifest import SnapshotImages
from tests.adapters.test_vision_manifest import write_snapshot
from tests.vision_helpers import make_image, sha

PNG = make_image(300, 200, ["표 1"])
PNG2 = make_image(320, 200, ["그림"])
TINY = make_image(40, 30)


def zipped(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def limits(ext: str, **extra) -> dict:
    return {
        "extra": {
            "ext": ext,
            "max_images": 10,
            "max_image_bytes": 1_000_000,
            "min_pixels": 5000,
            **extra,
        }
    }


def test_worker_hwpx_bindata_dedupes_and_filters_tiny():
    data = zipped(
        {
            "mimetype": b"application/hwp+zip",
            "BinData/image1.png": PNG,
            "BinData/image2.png": PNG,
            "BinData/tiny.png": TINY,
            "Contents/section0.xml": b"<a/>",
        }
    )
    out = extract(data, limits("hwpx"))
    assert [i["name"] for i in out["images"]] == ["BinData/image1.png"]
    assert out["images"][0]["width"] == 300 and out["images"][0]["sha256"] == sha(PNG)
    assert base64.b64decode(out["images"][0]["b64"]) == PNG
    assert out["skipped"] == {"duplicate": 1, "tiny": 1}


def test_worker_pptx_and_xlsx_record_slide_and_drawing():
    pptx = zipped(
        {
            "ppt/media/image1.png": PNG,
            "ppt/media/image2.png": PNG2,
            "ppt/slides/_rels/slide3.xml.rels": (
                b'<Relationships><Relationship Target="../media/image2.png"/></Relationships>'
            ),
        }
    )
    out = extract(pptx, limits("pptx"))
    where = {i["name"]: i["where"] for i in out["images"]}
    assert where == {"ppt/media/image1.png": None, "ppt/media/image2.png": "slide 3"}
    xlsx = zipped(
        {
            "xl/media/image1.png": PNG,
            "xl/drawings/_rels/drawing1.xml.rels": b'<R Target="../media/image1.png"/>',
        }
    )
    out = extract(xlsx, limits("xlsx"))
    assert out["images"][0]["where"] == "drawing1"


def test_worker_pdf_images_carry_page_numbers():
    import pymupdf

    doc = pymupdf.open()
    for n in range(2):
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(50, 50, 350, 250), stream=PNG if n == 0 else PNG2)
    data = doc.tobytes()
    out = extract(data, limits("pdf"))
    assert sorted(i["where"] for i in out["images"]) == ["page 1", "page 2"]
    assert all(i["width"] >= 300 for i in out["images"])


def test_worker_hwp_stream_is_inflated_and_unknown_ext_rejected():
    # hwp 는 OLE 파일을 만들 수 없어 압축 해제 규칙만 — _from_hwp 가 쓰는 raw deflate
    packed = zlib.compressobj(wbits=-15)
    raw = packed.compress(PNG) + packed.flush()
    assert zlib.decompressobj(-15).decompress(raw) == PNG
    with pytest.raises(ValueError):
        extract(b"PK", limits("docx"))


def test_manifest_expands_nested_images_and_attachment_records(tmp_path):
    root = tmp_path / "snapshots"
    page = {
        "url": "https://x/p1",
        "menu_path": "ESG경영 > 경영공시",
        "title": "중장기 경영목표",
        "images": [
            {
                "sha256": sha(PNG),
                "path": "images/aa/x.png",
                "src": "https://x/i.png",
                "alt": "전략체계도",
                "width": 300,
                "height": 200,
                "bytes": len(PNG),
                "ext": "png",
                "downloaded": True,
            },
            {"sha256": "b" * 64, "path": "images/bb/y.png", "downloaded": False},
        ],
        "attachments": [
            {
                "downloaded": True,
                "ext": "pptx",
                "path": "files/a.pptx",
                "sha256": "c" * 64,
                "name": "보고서",
            }
        ],
    }
    write_snapshot(root, "2026-10-27", [page], {"images/aa/x.png": PNG})
    (root / "2026-10-27" / "attachment_images.jsonl").write_text(
        json.dumps(
            {
                "type": "image",
                "sha256": sha(PNG2),
                "path": "images/attachments/z.png",
                "page_title": "ESG경영 > 경영공시 > 중장기 경영목표",
                "attachment": {"name": "보고서.pptx", "sha256": "c" * 64, "where": "slide 3"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    snap = SnapshotImages(root)
    items = snap.list_images()
    assert [i.path for i in items] == ["images/aa/x.png", "images/attachments/z.png"]
    assert (
        items[0].page_url == "https://x/p1"
        and items[0].page_title == "ESG경영 > 경영공시 > 중장기 경영목표"
    )
    assert (
        items[0].url == "https://x/i.png"
        and items[0].alt == "전략체계도"
        and items[0].mime == "image/png"
    )
    assert items[1].attachment == {"name": "보고서.pptx", "sha256": "c" * 64, "where": "slide 3"}
    assert snap.page_records()[0]["title"] == "중장기 경영목표" and snap.non_image == 0


async def test_extractor_writes_files_and_records_with_origin_meta(tmp_path):
    root = tmp_path / "snapshots"
    pptx = zipped(
        {
            "ppt/media/image1.png": PNG,
            "ppt/media/image2.png": PNG2,
            "ppt/slides/_rels/slide2.xml.rels": b'<R Target="../media/image2.png"/>',
        }
    )
    page = {
        "url": "https://x/p1",
        "menu_path": "홍보센터 > 기업브로슈어",
        "title": "2026 브로슈어",
        "images": [
            {
                "sha256": sha(PNG),
                "path": "images/aa/x.png",
                "downloaded": True,
                "width": 300,
                "height": 200,
            }
        ],
        "attachments": [
            {
                "downloaded": True,
                "ext": "pptx",
                "path": "files/a.pptx",
                "sha256": sha(pptx),
                "name": "브로슈어",
                "served_name": "brochure.pptx",
                "url": "https://x/f.pptx",
            },
            {"downloaded": True, "ext": "zip", "path": "files/b.zip", "sha256": "d" * 64},
            {"downloaded": False, "ext": "pdf", "path": "files/c.pdf", "sha256": "e" * 64},
        ],
    }
    write_snapshot(root, "2026-10-27", [page], {"images/aa/x.png": PNG, "files/a.pptx": pptx})
    snap = SnapshotImages(root)
    use = ExtractAttachmentImages(snap, SandboxLimits(timeout_sec=60, mem_mb=1024), min_pixels=5000)
    report = await use()  # 실제 격리 자식
    assert report.attachments == 1 and report.parsed == 1
    assert report.images == 1 and report.duplicates == 1  # PNG 는 페이지 이미지와 같은 해시
    assert report.by_ext == {"pptx": 1}
    items = snap.list_images()
    added = [i for i in items if i.attachment]
    assert len(added) == 1 and added[0].sha256 == sha(PNG2)
    assert (
        added[0].attachment["name"] == "brochure.pptx" and added[0].attachment["where"] == "slide 2"
    )
    assert (
        added[0].page_title == "홍보센터 > 기업브로슈어 > 2026 브로슈어"
        and added[0].url == "https://x/f.pptx"
    )
    assert snap.read_image(added[0]) == PNG2
    again = await ExtractAttachmentImages(
        snap, SandboxLimits(timeout_sec=60, mem_mb=1024), min_pixels=5000
    )()
    assert again.attachments == 0  # 증분: 처리한 첨부는 다시 열지 않는다


def test_brochure_group_orders_between_statistics_and_press():
    from rra.domain.models.vision import ORDER_GROUPS
    from rra.domain.rules.vision_plan import classify_group
    from tests.vision_helpers import item

    assert ORDER_GROUPS.index("brochure") == ORDER_GROUPS.index("statistics") + 1
    assert ORDER_GROUPS.index("brochure") < ORDER_GROUPS.index("press")
    it = item(
        PNG, "x.png", page_url="https://x/b", page_title="홍보센터 > 홍보 > 기업브로슈어 > 2026"
    )
    assert classify_group(it) == "brochure"
    assert (
        classify_group(item(PNG, "y.png", page_title="정보공개 > 사전정보공표 > 경영목표"))
        == "strategy"
    )
