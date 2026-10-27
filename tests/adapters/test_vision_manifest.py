"""스냅샷 manifest 읽기 — 별칭 허용, 깨진 줄 건너뜀, 경로 탈출·상한·해시 불일치 거부."""

import json

import pytest

from rra.adapters.vision.manifest import SnapshotImages, latest_snapshot, parse_item
from rra.application.ports.vision import ImageSnapshotPort
from tests.vision_helpers import make_image, sha


def write_snapshot(root, name, rows, files=None):
    snap = root / name
    snap.mkdir(parents=True)
    (snap / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r for r in rows)
        + "\n",
        encoding="utf-8",
    )
    for rel, data in (files or {}).items():
        path = snap / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return snap


def test_parse_item_accepts_aliases_and_rejects_non_images():
    it = parse_item(
        {
            "type": "image",
            "hash": "A" * 64,
            "file": "img/a.png",
            "src": "https://x/a.png",
            "page": "https://x/p",
            "title": "경영목표",
            "alt_text": "체계도",
            "w": "800",
            "h": 500,
            "size": 1234,
            "content_type": "image/png",
            "group": "strategy",
        }
    )
    assert it.sha256 == "a" * 64 and it.path == "img/a.png" and it.url == "https://x/a.png"
    assert it.page_url == "https://x/p" and it.page_title == "경영목표" and it.alt == "체계도"
    assert (it.width, it.height, it.bytes, it.mime) == (800, 500, 1234, "image/png")
    assert it.order_group == "strategy" and it.source == "korail_web"
    assert parse_item({"type": "page", "sha256": "a" * 64, "path": "p.html"}) is None
    assert parse_item({"sha256": "a" * 64, "path": "doc.pdf"}) is None  # type 없고 확장자도 아님
    assert parse_item({"sha256": "zz", "path": "a.png"}) is None
    assert parse_item({"sha256": "a" * 64, "path": "a.png", "group": "weird"}).order_group is None


def test_lists_images_from_latest_snapshot_and_counts_bad_lines(tmp_path):
    root = tmp_path / "snapshots"
    write_snapshot(root, "2026-10-20", [])
    rows = [
        {"type": "image", "sha256": "a" * 64, "path": "img/a.png"},
        "{broken",
        '"string"',
        {"type": "page", "sha256": "b" * 64, "path": "p.html"},
        {"sha256": "c" * 64, "path": "img/c.jpg"},
    ]
    write_snapshot(root, "2026-10-27", rows)
    assert latest_snapshot(root) == "2026-10-27"
    snap = SnapshotImages(root)
    assert isinstance(snap, ImageSnapshotPort) and snap.snapshot == "2026-10-27"
    items = snap.list_images()
    assert [i.path for i in items] == ["img/a.png", "img/c.jpg"]
    assert snap.bad_lines == 2 and snap.non_image == 1


def test_read_image_checks_hash_size_and_path_escape(tmp_path):
    root = tmp_path / "snapshots"
    png = make_image(200, 150, ["x"])
    other = make_image(201, 150, ["y"])
    rows = [
        {"type": "image", "sha256": sha(png), "path": "img/ok.png"},
        {"type": "image", "sha256": sha(png), "path": "img/tampered.png"},
        {"type": "image", "sha256": sha(other), "path": "../outside.png"},
    ]
    write_snapshot(root, "2026-10-27", rows, {"img/ok.png": png, "img/tampered.png": other})
    (root / "outside.png").write_bytes(other)
    snap = SnapshotImages(root, "2026-10-27", max_bytes=1_000_000)
    ok, tampered, outside = snap.list_images()
    assert snap.read_image(ok) == png
    with pytest.raises(ValueError, match="sha256"):
        snap.read_image(tampered)
    with pytest.raises(ValueError, match="밖"):
        snap.read_image(outside)
    small = SnapshotImages(root, "2026-10-27", max_bytes=10)
    with pytest.raises(ValueError, match="상한"):
        small.read_image(ok)


def test_missing_snapshot_or_manifest_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        SnapshotImages(tmp_path / "none")
    (tmp_path / "s" / "2026-10-27").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="manifest"):
        SnapshotImages(tmp_path / "s").list_images()
    with pytest.raises(ValueError):
        SnapshotImages(tmp_path / "s", "../x")
