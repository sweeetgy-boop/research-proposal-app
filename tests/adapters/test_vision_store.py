"""해시별 파일 캐시·기록 — 경로 탈출 차단, 권한 600, 로그에 키·본문 금지."""

import json
import stat

import pytest

from rra.adapters.vision.store import FileVisionStore
from rra.application.ports.vision import VisionStorePort

SHA = "ab" * 32


def test_roundtrip_and_cached_hashes(tmp_path):
    store = FileVisionStore(tmp_path / "korail_web")
    assert isinstance(store, VisionStorePort)
    assert store.get_reading(SHA) is None and store.cached_hashes() == set()
    store.put_reading(SHA, {"ok": True, "reading": {"image_type": "표"}})
    store.put_ocr(SHA, {"ok": True, "result": {"lines": []}})
    assert store.get_reading(SHA)["reading"] == {"image_type": "표"}
    assert store.get_ocr(SHA)["ok"] is True
    assert store.cached_hashes() == {SHA}
    path = tmp_path / "korail_web" / "vision_cache" / f"{SHA}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not path.with_suffix(".tmp").exists()


def test_failed_reading_counts_as_cached_hash(tmp_path):
    store = FileVisionStore(tmp_path)
    store.put_reading(SHA, {"ok": False, "error": "LLMError"})
    assert store.cached_hashes() == {SHA}


@pytest.mark.parametrize("bad", ["../etc/passwd", "ABCD", "", "ab" * 31 + "zz", "a" * 64 + "/x"])
def test_rejects_non_sha_keys(tmp_path, bad):
    store = FileVisionStore(tmp_path)
    with pytest.raises(ValueError):
        store.get_reading(bad)
    with pytest.raises(ValueError):
        store.put_ocr(bad, {})


def test_log_appends_jsonl_without_secrets_or_bodies(tmp_path):
    store = FileVisionStore(tmp_path)
    store.log(
        {
            "sha256": SHA,
            "url": "https://x/a.png",
            "status": "argon",
            "api_key": "sk-x",
            "text": "본문",
        }
    )
    store.log({"sha256": SHA, "status": "failed", "authorization": "Bearer x"})
    lines = [json.loads(ln) for ln in (tmp_path / "vision_log.jsonl").read_text().splitlines()]
    assert lines[0] == {"sha256": SHA, "url": "https://x/a.png", "status": "argon"}
    assert lines[1] == {"sha256": SHA, "status": "failed"}
    assert stat.S_IMODE((tmp_path / "vision_log.jsonl").stat().st_mode) == 0o600


def test_corrupt_cache_file_is_treated_as_missing(tmp_path):
    store = FileVisionStore(tmp_path)
    store.cache_dir.mkdir(parents=True)
    (store.cache_dir / f"{SHA}.json").write_text("{not json")
    assert store.get_reading(SHA) is None
