"""감사원 감사결과 스냅샷 크롤러 (Playwright, `rra crawl bai`).

- 공개 화면만 조작한다: 목록 페이지 열기 → `#searchText` 에 질의 → 행의 제목 클릭(상세
  `detail?srno=`) → 파일 링크 클릭
  (blob 다운로드). 페이지가 스스로 부르는 `/api/…` 는 브라우저 동작이고, 우리는 `/api/` URL 을
  만들어
  요청하지
  않는다
  (robots Disallow /api/ 준수). 목록 JSON 응답은 "페이지가 받은 것"을 읽어 srno 만 뽑는다.
- 같은 호스트 동시 1, 페이지 이동 사이 ≥ min_interval_sec(2s). 실패는 2s→5s→10s 백오프, 연속 3회면
  보류 후 끝에 10s 간격 1회 재시도.
- 저장 구조는 korail_web 스냅샷과 같다 (snapshot.py 재사용): manifest.jsonl 1줄 = 감사결과 1건,
  files/<sha[:2]>/<sha>.pdf.
- playwright 는 이 모듈 안에서만 import 한다(선택 의존성: `uv pip install playwright && playwright
  install chromium`).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from rra.adapters.sources.audit._common import ext_of, strip_size
from rra.adapters.sources.korail_web.robots import RobotsRules
from rra.adapters.sources.korail_web.snapshot import (
    SnapshotDir,
    content_path,
    read_manifest,
    today_str,
)

logger = logging.getLogger("rra.sources.bai")

BACKOFF_SEC = (2.0, 5.0, 10.0)
MAX_CONSECUTIVE_FAILURES = 3
TERMS = "공공누리 제4유형(출처표시·상업적 이용금지·변경금지)"
_TOTAL = re.compile(r"전체\s*:\s*([\d,]+)\s*건")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class BaiConfig:
    base_url: str = "https://www.bai.go.kr"
    list_path: str = "/bai/result/branch/list/"
    queries: tuple[str, ...] = ("철도",)
    user_agent: str = "RRA research-proposal-app (internal research use)"
    min_interval_sec: float = 2.0
    max_pages: int = 10
    max_items: int = 200
    max_file_bytes: int = 50 * 1024 * 1024
    attachment_types: frozenset[str] = frozenset({"pdf"})
    headless: bool = True

    @classmethod
    def from_config(cls, raw: dict[str, Any]) -> BaiConfig:
        return cls(
            base_url=str(raw.get("base_url") or cls.base_url).rstrip("/"),
            list_path=str(raw.get("list_path") or cls.list_path),
            queries=tuple(str(q) for q in (raw.get("queries") or ["철도"])),
            user_agent=str(raw.get("user_agent") or cls.user_agent),
            min_interval_sec=float(raw.get("min_interval_sec", 2) or 2),
            max_pages=int(raw.get("max_pages", 10)),
            max_items=int(raw.get("max_items", 200)),
            max_file_bytes=int(float(raw.get("max_file_mb", 50)) * 1024 * 1024),
            attachment_types=frozenset(
                str(t).lower() for t in (raw.get("attachment_types") or ["pdf"])
            ),
            headless=bool(raw.get("headless", True)),
        )


@dataclass
class BaiReport:
    snapshot: str
    queries: list[str] = field(default_factory=list)
    total_by_query: dict[str, int | None] = field(default_factory=dict)
    items: int = 0
    skipped_existing: int = 0
    files: int = 0
    bytes: int = 0
    held: list[str] = field(default_factory=list)
    errors: int = 0


class Held(Exception):
    """연속 실패 3회 — 이 항목은 보류."""


def srno_values(payload: Any) -> list[str]:
    """목록 JSON(페이지가 받은 응답)에서 srno 로 보이는 값들 — 키 이름이 바뀌어도 'srno' 를 포함하면
    찾는다."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if "srno" in str(k).lower() and isinstance(v, int | str) and str(v).isdigit():
                    if str(v) not in found:
                        found.append(str(v))
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return found


def parse_row_cells(cells: Sequence[str]) -> dict[str, Any]:
    """목록 한 행의 셀 텍스트 → {title, kind, field, posted}. 열:
    감사사항·감사종류·감사분야·전문·보도자료·등록일자."""
    texts = [str(c).strip() for c in cells]
    posted = next((t for t in reversed(texts) if _DATE.fullmatch(t)), None)
    return {
        "title": texts[0] if texts else "",
        "kind": texts[1] if len(texts) > 1 else "",
        "field": texts[2] if len(texts) > 2 else "",
        "posted": posted,
    }


class BaiCrawler:
    def __init__(
        self,
        config: BaiConfig,
        root: Path,
        *,
        robots_text: Callable[[], Awaitable[str]] | None = None,
        today: Callable[[], date] = date.today,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.config = config
        self.root = Path(root)
        self._robots_text = robots_text
        self._today = today
        self._sleep = sleep
        self._consecutive = 0
        self.robots: RobotsRules | None = None

    async def load_robots(self) -> RobotsRules:
        if self.robots is None:
            text = ""
            if self._robots_text is not None:
                try:
                    text = await self._robots_text()
                except Exception as exc:  # noqa: BLE001 — robots 못 읽으면 빈 규칙(허용)로
                    logger.warning("bai.robots_unavailable error=%s", type(exc).__name__)
            self.robots = RobotsRules(text, user_agent=self.config.user_agent)
        return self.robots

    def _check(self, url: str) -> None:
        if self.robots is None:
            raise RuntimeError("load_robots() 먼저")
        if not self.robots.allowed(url):
            raise PermissionError(f"robots.txt 가 금지한 경로: {url}")
        if "/api/" in url:
            raise PermissionError(f"/api/ 는 직접 요청하지 않는다: {url}")

    async def _pace(self) -> None:
        await self._sleep(self.config.min_interval_sec)

    async def download(self, *, incremental: bool = False) -> BaiReport:
        from playwright.async_api import async_playwright

        await self.load_robots()
        snap = SnapshotDir(self.root, today_str(self._today()))
        snap.ensure()
        existing = read_manifest(snap) if incremental else {}
        report = BaiReport(snapshot=snap.day, queries=list(self.config.queries))
        held: list[dict[str, Any]] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.headless)
            ctx = await browser.new_context(
                user_agent=self.config.user_agent, accept_downloads=True
            )
            page = await ctx.new_page()
            try:
                rows = await self._collect_rows(page, report)
                for row in rows:
                    if row["native_id"] in existing:
                        report.skipped_existing += 1
                        continue
                    try:
                        rec = await self._with_backoff(self._detail, page, snap, row, report)
                    except Held:
                        held.append(row)
                        report.held.append(row["native_id"])
                        continue
                    snap.append_manifest(rec)
                    report.items += 1
                if held:  # 보류 1회 재시도 (10초 간격)
                    retry, report.held = list(held), []
                    for row in retry:
                        await self._sleep(10.0)
                        try:
                            rec = await self._detail(page, snap, row, report)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("bai.held error=%s", type(exc).__name__)
                            report.held.append(row["native_id"])
                            continue
                        snap.append_manifest(rec)
                        report.items += 1
            finally:
                await browser.close()
        snap.write_summary(
            {
                "snapshot": snap.day,
                "queries": report.queries,
                "total_by_query": report.total_by_query,
                "items": report.items,
                "files": report.files,
                "bytes": report.bytes,
                "held": report.held,
                "errors": report.errors,
                "terms": TERMS,
            }
        )
        return report

    async def _with_backoff(self, fn, *args):
        for attempt in range(len(BACKOFF_SEC) + 1):
            try:
                result = await fn(*args)
                self._consecutive = 0
                return result
            except PermissionError:
                raise
            except Exception as exc:  # noqa: BLE001 — Playwright 오류·시간 초과
                self._consecutive += 1
                logger.warning("bai.fetch_failed error=%s", type(exc).__name__)
                if self._consecutive >= MAX_CONSECUTIVE_FAILURES:
                    self._consecutive = 0
                    raise Held() from exc
                if attempt < len(BACKOFF_SEC):
                    await self._sleep(BACKOFF_SEC[attempt])
        raise Held()

    async def _collect_rows(self, page: Any, report: BaiReport) -> list[dict[str, Any]]:
        """질의마다 목록을 넘기며 (srno, 제목, 종류, 분야, 등록일) 를 모은다."""
        rows: dict[str, dict[str, Any]] = {}
        list_url = f"{self.config.base_url}{self.config.list_path}"
        self._check(list_url)
        for query in self.config.queries:
            captured: list[Any] = []

            async def on_response(resp: Any, _cap=captured) -> None:
                if "AWUBAKDAR001E?" in resp.url and resp.status == 200:
                    try:
                        _cap.append(await resp.json())
                    except Exception as exc:  # noqa: BLE001 — JSON 이 아니면 무시
                        logger.debug("bai.list_json_skipped error=%s", type(exc).__name__)

            page.on("response", on_response)
            try:
                await page.goto(list_url, wait_until="networkidle")
                await self._pace()
                box = page.locator("input#searchText")
                await box.fill(query)
                captured.clear()
                await box.press("Enter")
                await page.wait_for_load_state("networkidle")
                await self._pace()
                text = await page.inner_text("body")
                m = _TOTAL.search(text)
                report.total_by_query[query] = int(m.group(1).replace(",", "")) if m else None
                for page_no in range(1, self.config.max_pages + 1):
                    if page_no > 1:
                        link = page.locator("li > a", has_text=re.compile(rf"^{page_no}$"))
                        if await link.count() == 0:
                            break
                        captured.clear()
                        await link.first.click()
                        await page.wait_for_load_state("networkidle")
                        await self._pace()
                    cells = await page.eval_on_selector_all(
                        "table tbody tr",
                        "trs=>trs.map(tr=>[...tr.querySelectorAll('td')].map(td=>td.innerText))",
                    )
                    ids: list[str] = []
                    for payload in captured:
                        ids.extend(v for v in srno_values(payload) if v not in ids)
                    if len(ids) != len(cells):
                        logger.warning(
                            "bai.row_mismatch ids=%d cells=%d query=%s", len(ids), len(cells), query
                        )
                    for srno, cell in zip(ids, cells, strict=False):
                        if srno in rows or len(rows) >= self.config.max_items:
                            continue
                        rows[srno] = {"native_id": srno, "query": query, **parse_row_cells(cell)}
                    if len(cells) < 10 or len(rows) >= self.config.max_items:
                        break
            finally:
                page.remove_listener("response", on_response)
        return list(rows.values())

    async def _detail(
        self, page: Any, snap: SnapshotDir, row: dict[str, Any], report: BaiReport
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}/bai/result/branch/detail?srno={row['native_id']}"
        self._check(url)
        await page.goto(url, wait_until="networkidle")
        await self._pace()
        info = await page.eval_on_selector_all(
            "dt, th",
            "els=>els.map(e=>[e.innerText.trim(), (e.nextElementSibling||{}).innerText||''])",
        )
        meta = {str(k): str(v).strip() for k, v in info if k}
        names = await page.eval_on_selector_all(
            "a, button",
            "els=>els.map(e=>e.innerText.trim()).filter(t=>/\\.(pdf|hwp|hwpx)\\s*\\(/i.test(t))",
        )
        files: list[dict[str, Any]] = []
        for name in names:
            clean = strip_size(name)
            ext = ext_of(clean)
            if ext not in self.config.attachment_types:
                files.append({"name": clean, "ext": ext, "downloaded": False, "reason": "type"})
                continue
            async with page.expect_download(timeout=120_000) as dl_info:
                await page.locator("a, button", has_text=clean).first.click()
            dl = await dl_info.value
            path = await dl.path()
            data = Path(path).read_bytes() if path else b""
            if not data or len(data) > self.config.max_file_bytes:
                files.append({"name": clean, "ext": ext, "downloaded": False, "reason": "size"})
                continue
            sha = hashlib.sha256(data).hexdigest()
            rel = content_path("files", sha, ext)
            snap.write_bytes(rel, data)
            files.append(
                {
                    "name": clean,
                    "ext": ext,
                    "downloaded": True,
                    "sha256": sha,
                    "bytes": len(data),
                    "path": rel,
                }
            )
            report.files += 1
            report.bytes += len(data)
            await self._pace()
        posted = row.get("posted") or next(
            (v for k, v in meta.items() if "공개일" in k and _DATE.search(v)), None
        )
        return {
            "native_id": row["native_id"],
            "source": "bai",
            "doc_type": "audit",
            "title": row.get("title") or "",
            "kind": row.get("kind"),
            "field": row.get("field"),
            "posted": _DATE.search(posted).group(0) if posted and _DATE.search(posted) else None,
            "bai_department": meta.get("부서명") or None,
            "query": row.get("query"),
            "url": url,
            "terms": TERMS,
            "snapshot": snap.day,
            "files": files,
        }


def summary_json(snap: SnapshotDir) -> str:
    return json.dumps({"snapshot": snap.day}, ensure_ascii=False)
