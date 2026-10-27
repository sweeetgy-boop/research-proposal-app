"""이미지 판독 파이프라인 (P3 ②③④⑤) — 거르기 → 순서·예산 계획 → OCR → Argon → 수치 대조.

- 거르기·순서·예산·대조는 도메인 규칙. 여기서는 포트를 순서대로 부르고 캐시·기록을 남긴다.
- 같은 해시는 다시 부르지 않는다: 판독 캐시(성공·실패 모두)가 있으면 호출 없이 캐시를 쓴다.
- OCR 엔진이 없으면(OcrUnavailable) "OCR 없음" 으로 계속하고 모든 수치는 미확인으로 남는다.
- Argon 실패(LLM 오류·JSON 아님)는 OCR 텍스트만 남기고 status=failed. 예외 클래스명만 기록한다.
- 상한(cap)을 넘는 항목은 OCR 만 하고 목록에 남긴다. dry_run 은 계획만 돌려준다 (호출 0).
- 호출 기록(vision_log)에는 hash·url·시간·status·provider·model 만. 키·본문은 넣지 않는다 (보안 D).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from rra.application.ports.vision import (
    ImageSnapshotPort,
    OcrPort,
    OcrUnavailable,
    VisionReaderPort,
    VisionStorePort,
)
from rra.domain.models.vision import ImageItem, ImageReadResult, OcrResult, VisionReading
from rra.domain.rules.image_filter import FilterReport, ImageFilterConfig, filter_images
from rra.domain.rules.photo_filter import PhotoRule, is_photo, ocr_signals, photo_meta
from rra.domain.rules.vision_plan import DEFAULT_CAP, VisionPlan, plan
from rra.domain.rules.vision_trust import VisionParseError, parse_reading, verify_numbers

logger = logging.getLogger("rra.vision")
MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
MAX_LOG_URL_CHARS = 300


@dataclass
class ReadReport:
    snapshot: str
    filter: FilterReport
    plan: VisionPlan
    results: list[ImageReadResult] = field(default_factory=list)
    calls: int = 0  # 이번 실행에서 실제로 보낸 Argon 호출 수
    dry_run: bool = False
    elapsed_sec: float = 0.0

    @property
    def status_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    @property
    def ocr_only_hashes(self) -> list[str]:
        """상한 때문에 OCR 만 한 해시 — 다음 실행에서 이어서 판독할 목록."""
        return [it.sha256 for it in self.plan.ocr_only]

    def summary(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot,
            "dry_run": self.dry_run,
            "filter": self.filter.counts,
            "plan": self.plan.summary(),
            "status": self.status_counts,
            "calls": self.calls,
            "unconfirmed_numbers": sum(len(r.unconfirmed_numbers) for r in self.results),
            "elapsed_sec": round(self.elapsed_sec, 2),
        }


class ReadImages:
    def __init__(
        self,
        snapshot: ImageSnapshotPort,
        store: VisionStorePort,
        *,
        ocr: OcrPort | None,
        reader: VisionReaderPort | None,
        prompt: str,
        system: str | None = None,
        filter_config: ImageFilterConfig | None = None,
        cap: int = DEFAULT_CAP,
        keywords: dict | None = None,
        max_tokens: int | None = None,
        photo_rule: PhotoRule | None = None,
        concurrency: int = 1,  # 동시에 처리할 이미지 수 — Gemini 제한기(동시 4·분당 60)와 맞춘다
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.snapshot, self.store = snapshot, store
        self.ocr, self.reader = ocr, reader
        self.prompt, self.system, self.max_tokens = prompt, system, max_tokens
        self.filter_config = filter_config or ImageFilterConfig()
        self.cap, self.keywords = cap, keywords
        self.photo_rule = photo_rule or PhotoRule(enabled=False)
        self.concurrency = max(1, int(concurrency))
        self._clock, self._now = clock, now
        self.calls = 0
        self._ocr_unavailable = False

    # ── 계획 ──────────────────────────────────────────────
    def make_plan(self, *, limit: int | None = None) -> tuple[FilterReport, VisionPlan]:
        items = self.snapshot.list_images()
        report = filter_images(items, self.filter_config)
        cached = self.store.cached_hashes()
        planned = plan(
            report.kept,
            cached_hashes=cached,
            cap=self.cap,
            keywords=self.keywords,
            limit=limit,
            is_photo=self._is_photo if self.photo_rule.enabled else None,
        )
        if self.reader is None:  # 판독기가 없으면(키 없음) 전부 OCR 만
            planned.ocr_only = planned.to_call + planned.ocr_only
            planned.to_call = []
        return report, planned

    def _is_photo(self, item: ImageItem, group: str) -> bool:
        """OCR 캐시가 있을 때만 판정 — OCR 전(캐시 없음)에는 사진으로 보지 않는다."""
        return is_photo(ocr_signals(self.store.get_ocr(item.sha256)), group, self.photo_rule)

    # ── 실행 ──────────────────────────────────────────────
    async def __call__(
        self,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        on_result: Callable[[ImageReadResult], None] | None = None,
    ) -> ReadReport:
        started = self._clock()
        filter_report, planned = self.make_plan(limit=limit)
        report = ReadReport(self.snapshot.snapshot, filter_report, planned, dry_run=dry_run)
        if dry_run:
            report.elapsed_sec = self._clock() - started
            return report
        call_set = {it.sha256 for it in planned.to_call}
        photo_set = {it.sha256 for it in planned.photos}
        if self.concurrency <= 1:
            for item in planned.ordered:
                result = await self._process(
                    item, may_call=item.sha256 in call_set, photo=item.sha256 in photo_set
                )
                report.results.append(result)
                if on_result is not None:
                    on_result(result)
        else:
            # 병렬: 세마포어로 동시 수를 막고, 결과는 우선순위 순서대로 모은다 (2026-10-27 — 순차는
            # 분당 8장이라 2,000장에 4시간). 호출 수 상한은 _vision 의 self.calls 가 await 없이
            # 지킨다.
            sem = asyncio.Semaphore(self.concurrency)

            async def run(item: ImageItem) -> ImageReadResult:
                async with sem:
                    return await self._process(
                        item, may_call=item.sha256 in call_set, photo=item.sha256 in photo_set
                    )

            for result in await asyncio.gather(*(run(it) for it in planned.ordered)):
                report.results.append(result)
                if on_result is not None:
                    on_result(result)
        report.calls = self.calls
        report.elapsed_sec = self._clock() - started
        return report

    async def _process(
        self, item: ImageItem, *, may_call: bool, photo: bool = False
    ) -> ImageReadResult:
        t0 = self._clock()
        if photo:  # 사진: 이미지를 다시 읽지 않고 OCR 캐시 신호와 메타만 남긴다 (Argon 없음)
            signals = ocr_signals(self.store.get_ocr(item.sha256))
            if self.reader is not None:  # 적재(reader=None) 재실행 때는 로그를 겹쳐 쓰지 않는다
                self.store.log(
                    {
                        "sha256": item.sha256,
                        "url": (item.url or item.path)[:MAX_LOG_URL_CHARS],
                        "time": self._stamp(),
                        "status": "photo",
                        **photo_meta(item, signals),
                    }
                )
            return ImageReadResult(
                sha256=item.sha256, status="photo", item=item, elapsed_sec=self._clock() - t0
            )
        try:
            image = self.snapshot.read_image(item)
        except (ValueError, OSError) as exc:
            return ImageReadResult(
                sha256=item.sha256,
                status="failed",
                item=item,
                vision_error=type(exc).__name__,
                elapsed_sec=self._clock() - t0,
            )
        mime = item.mime or MIME_BY_EXT.get(_ext(item), "image/png")
        ocr, ocr_error = await self._ocr(item, image, mime)
        reading, vision_error, cached, status, took = await self._vision(
            item, image, mime, may_call
        )
        confirmed: list[str] = []
        unconfirmed: list[str] = []
        if reading is not None:
            confirmed, unconfirmed = verify_numbers(reading, ocr)
        # 캐시 적중이면 처음 판독한 시간을 쓴다 (harness 가 재실행에서도 장당 시간을 보도록)
        elapsed = took if cached and took is not None else self._clock() - t0
        return ImageReadResult(
            sha256=item.sha256,
            status=status,
            item=item,
            ocr=ocr,
            ocr_error=ocr_error,
            reading=reading,
            vision_error=vision_error,
            confirmed_numbers=confirmed,
            unconfirmed_numbers=unconfirmed,
            cached=cached,
            elapsed_sec=elapsed,
        )

    async def _ocr(
        self, item: ImageItem, image: bytes, mime: str
    ) -> tuple[OcrResult | None, str | None]:
        cached = self.store.get_ocr(item.sha256)
        if isinstance(cached, dict) and cached.get("ok"):
            try:
                return OcrResult.model_validate(cached.get("result") or {}), None
            except ValueError:
                pass
        if self.ocr is None or self._ocr_unavailable:
            return None, "OcrUnavailable"
        try:
            result = await self.ocr.recognize(image, mime=mime)
        except OcrUnavailable:
            self._ocr_unavailable = True  # 한 번 없으면 계속 없다 — 매번 시도하지 않는다
            return None, "OcrUnavailable"
        except Exception as exc:  # SandboxError 계열 등 — 클래스명만
            name = type(exc).__name__
            self.store.put_ocr(item.sha256, {"ok": False, "error": name, "time": self._stamp()})
            return None, name
        self.store.put_ocr(
            item.sha256,
            {
                "ok": True,
                "engine": result.engine,
                "time": self._stamp(),
                "result": result.model_dump(),
            },
        )
        return result, None

    async def _vision(
        self, item: ImageItem, image: bytes, mime: str, may_call: bool
    ) -> tuple[VisionReading | None, str | None, bool, str, float | None]:
        """(판독, 오류, 캐시 여부, status, 캐시된 처리 시간)."""
        cached = self.store.get_reading(item.sha256)
        if isinstance(cached, dict):
            took = cached.get("elapsed_sec")
            took = float(took) if isinstance(took, int | float) else None
            if cached.get("ok") and isinstance(cached.get("reading"), dict):
                try:
                    reading = VisionReading.model_validate(cached["reading"])
                except ValueError:
                    return None, "CachedReadingInvalid", True, "failed", took
                return reading, None, True, "argon", took
            return None, str(cached.get("error") or "CachedFailure"), True, "failed", took
        if not may_call or self.reader is None:
            return None, None, False, "ocr_only", None
        if self.calls >= self.cap:  # 계획과 별개의 안전장치
            return None, None, False, "ocr_only", None
        self.calls += 1
        t0 = self._clock()
        record = {
            "sha256": item.sha256,
            "url": (item.url or item.path)[:MAX_LOG_URL_CHARS],
            "time": self._stamp(),
            "provider": self.reader.provider,
            "model": self.reader.model,
        }
        try:
            text = await self.reader.read_image(
                self.prompt,
                image,
                mime=mime,
                system=self.system,
                max_tokens=self.max_tokens,
                json_mode=True,
            )
        except Exception as exc:  # LLMError 계열 — 클래스명만 남긴다 (본문·키 금지)
            name = type(exc).__name__
            self._cache_failure(item, name, record, t0)
            logger.warning("vision failed sha=%s error=%s", item.sha256[:12], name)
            return None, name, False, "failed", None
        try:
            reading = parse_reading(text)
        except VisionParseError as exc:
            name = f"VisionParseError:{exc}"
            self._cache_failure(item, name, record, t0)
            return None, name, False, "failed", None
        self.store.put_reading(
            item.sha256,
            {
                "ok": True,
                "time": record["time"],
                "provider": record["provider"],
                "model": record["model"],
                "elapsed_sec": round(self._clock() - t0, 3),
                "reading": reading.model_dump(),
            },
        )
        self.store.log({**record, "status": "argon", "image_type": reading.image_type})
        return reading, None, False, "argon", None

    def _cache_failure(self, item: ImageItem, name: str, record: dict, t0: float) -> None:
        self.store.put_reading(
            item.sha256,
            {
                "ok": False,
                "error": name,
                "time": record["time"],
                "elapsed_sec": round(self._clock() - t0, 3),
            },
        )
        self.store.log({**record, "status": "failed", "error": name})

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")


def _ext(item: ImageItem) -> str:
    name = (item.url or item.path).split("?", 1)[0].rsplit("/", 1)[-1].lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""
