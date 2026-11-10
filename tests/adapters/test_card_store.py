"""문제 정의 카드 재사용 저장소 (계약 problem-card.md 4.4절) — 권한·보관 기간·파일 이름."""

from __future__ import annotations

import json
import stat

from rra.adapters.persistence.card_store import MemoryCache, PrivateFileCache
from rra.application.ports import CachePort


def mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_file_cache_sets_modes_and_hashes_names(tmp_path):
    root = tmp_path / "cache" / "problem_cards"
    cache = PrivateFileCache(root, ttl_sec=60)
    assert isinstance(cache, CachePort)
    assert cache.get("k") is None and not root.exists()  # 읽기는 폴더를 만들지 않는다
    cache.set("staff:aaaaaaaaaaaa 비둘기", {"function_ko": {"value": "막는다"}})
    files = list(root.iterdir())
    assert mode(root) == 0o700 and [mode(f) for f in files] == [0o600]
    name = files[0].name
    assert len(name) == 64 + len(".json") and "staff" not in name and "비둘기" not in name
    assert cache.get("staff:aaaaaaaaaaaa 비둘기") == {"function_ko": {"value": "막는다"}}
    cache.set("staff:aaaaaaaaaaaa 비둘기", {"v": 2})  # 같은 키는 갈아 끼운다
    assert cache.get("staff:aaaaaaaaaaaa 비둘기") == {"v": 2} and len(list(root.iterdir())) == 1
    assert mode(next(root.iterdir())) == 0o600


def test_ttl_expires_and_none_never_expires(tmp_path):
    now = [1000.0]
    cache = PrivateFileCache(tmp_path / "c", ttl_sec=30 * 86400, clock=lambda: now[0])
    pins = PrivateFileCache(
        tmp_path / "c" / "pinned", ttl_sec=None, secure_parent=True, clock=lambda: now[0]
    )
    cache.set("k", {"a": 1})
    pins.set("k", {"a": 2})
    now[0] += 30 * 86400 - 1
    assert cache.get("k") == {"a": 1}
    now[0] += 2
    assert cache.get("k") is None  # 보관 기간이 지남
    now[0] += 10 * 365 * 86400
    assert pins.get("k") == {"a": 2}  # 고정 카드는 만료 없음
    assert mode(tmp_path / "c" / "pinned") == 0o700


def test_pinned_first_write_secures_parent_folder(tmp_path):
    root = tmp_path / "cache" / "problem_cards"
    PrivateFileCache(root / "pinned", ttl_sec=None, secure_parent=True).set("k", {})
    assert mode(root) == 0o700 and mode(root / "pinned") == 0o700


def test_broken_file_reads_as_missing(tmp_path):
    cache = PrivateFileCache(tmp_path, ttl_sec=60)
    cache.set("k", {"a": 1})
    next(p for p in tmp_path.iterdir() if p.suffix == ".json").write_text("{", encoding="utf-8")
    assert cache.get("k") is None


def test_memory_cache_copies_values():
    cache = MemoryCache()
    assert isinstance(cache, CachePort) and cache.get("k") is None
    value = {"a": [1]}
    cache.set("k", value)
    value["a"].append(2)
    got = cache.get("k")
    assert got == {"a": [1]} and json.dumps(got)
    got["a"].append(3)
    assert cache.get("k") == {"a": [1]}
