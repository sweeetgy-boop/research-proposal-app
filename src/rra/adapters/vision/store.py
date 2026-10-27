"""VisionStorePort 구현 — 해시별 파일 캐시와 호출 기록.

    <root>/ocr/<sha256>.json            OCR 결과 (성공·실패)
    <root>/vision_cache/<sha256>.json   Argon 판독 JSON (성공·실패 — 같은 해시는 다시 부르지 않는다)
    <root>/vision_log.jsonl             호출 기록 한 줄씩 (hash·url·time·status·provider·model —
                                        키·본문 없음)

해시는 64자 16진수만 받는다 (경로 탈출 차단). 쓰기는 임시 파일 → rename, 권한 600.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
OCR_DIR = "ocr"
CACHE_DIR = "vision_cache"
LOG_NAME = "vision_log.jsonl"
FORBIDDEN_LOG_KEYS = frozenset(
    {"api_key", "authorization", "key", "token", "text", "reading", "image"}
)


class FileVisionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.ocr_dir = self.root / OCR_DIR
        self.cache_dir = self.root / CACHE_DIR
        self.log_path = self.root / LOG_NAME

    @staticmethod
    def _check(sha256: str) -> str:
        sha = (sha256 or "").lower()
        if not _SHA.match(sha):
            raise ValueError("sha256 형식이 아닙니다")
        return sha

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)

    # ── VisionStorePort ───────────────────────────────────
    def get_reading(self, sha256: str) -> dict[str, Any] | None:
        return self._read(self.cache_dir / f"{self._check(sha256)}.json")

    def put_reading(self, sha256: str, payload: dict[str, Any]) -> None:
        self._write(self.cache_dir / f"{self._check(sha256)}.json", payload)

    def get_ocr(self, sha256: str) -> dict[str, Any] | None:
        return self._read(self.ocr_dir / f"{self._check(sha256)}.json")

    def put_ocr(self, sha256: str, payload: dict[str, Any]) -> None:
        self._write(self.ocr_dir / f"{self._check(sha256)}.json", payload)

    def cached_hashes(self) -> set[str]:
        if not self.cache_dir.is_dir():
            return set()
        return {p.stem for p in self.cache_dir.glob("*.json") if _SHA.match(p.stem)}

    def log(self, record: dict[str, Any]) -> None:
        safe = {k: v for k, v in record.items() if k not in FORBIDDEN_LOG_KEYS}
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")


class MemoryVisionStore:
    """테스트·dry-run 용. 같은 인터페이스, 파일 없음."""

    def __init__(self) -> None:
        self.readings: dict[str, dict[str, Any]] = {}
        self.ocr: dict[str, dict[str, Any]] = {}
        self.records: list[dict[str, Any]] = []

    def get_reading(self, sha256: str) -> dict[str, Any] | None:
        return self.readings.get(sha256)

    def put_reading(self, sha256: str, payload: dict[str, Any]) -> None:
        self.readings[sha256] = payload

    def get_ocr(self, sha256: str) -> dict[str, Any] | None:
        return self.ocr.get(sha256)

    def put_ocr(self, sha256: str, payload: dict[str, Any]) -> None:
        self.ocr[sha256] = payload

    def cached_hashes(self) -> set[str]:
        return set(self.readings)

    def log(self, record: dict[str, Any]) -> None:
        self.records.append({k: v for k, v in record.items() if k not in FORBIDDEN_LOG_KEYS})
