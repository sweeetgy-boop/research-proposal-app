"""정부 R&D 사업공고 스냅샷 수집 (`rra crawl rnd-notice`, P2-7).

- KAIA(사업공고, GET 목록·상세·첨부 `/afile/fileDownload/<id>`)와 IRIS(사업공고, 공개 검색 폼 POST →
  JSON, 국토교통부
  필터, 상세 GET 본문). 네트워크는 GuardedClient 로만(허용목록·https·크기 상한), 요청 간격 2초, 동시
  1.
- robots.txt 는 사이트마다 확인한다(IRIS 는 /wklounge/… 만 금지, 사업공고 경로는 허용). 403·429·전송
  오류는
  2s → 5s → 10s 백오프, 연속 3회 실패면 보류(held) 하고 맨 끝에 10s 간격으로 한 번 더 시도한다.
- 최근 since_days(2년) 안의 공고만, 합산 상한 max_notices. 같은 공고가 두 사이트에
  있으면(제목+기관+공고일 키) 한
  레코드에 `also_in` 으로 합친다.
- 상세 본문은 개인정보 제거(strip_pii) 뒤 items/<site>/<id>.txt. 첨부(pdf·hwp·hwpx)는 받기만 하고
  열지 않는다
  (파싱은 적재 때 샌드박스). zip 등은 이름만. IRIS 첨부는 POST 다운로드라 이름만 기록한다(보류 사유
  post_download).
- 스냅샷 구조는 korail_web 과 같다:
  data/rnd_notice/snapshots/<날짜>/manifest.jsonl·snapshot.json·items·files.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient, strip_secrets
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.korail_web.robots import RobotsRules
from rra.adapters.sources.korail_web.snapshot import (
    SnapshotDir,
    content_path,
    latest_snapshot,
    read_manifest,
    safe_id,
    today_str,
)
from rra.adapters.sources.rnd_notice._html import (
    NoticeRow,
    parse_iris_detail,
    parse_iris_list,
    parse_kaia_detail,
    parse_kaia_list,
)
from rra.domain.rules.notices import notice_key, parse_date, parse_period

logger = logging.getLogger("rra.sources.rnd_notice")

BACKOFF_SEC = (2.0, 5.0, 10.0)
HELD_RETRY_GAP_SEC = 10.0
MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_ATTACHMENT_TYPES = ("pdf", "hwp", "hwpx")
TERMS = {
    "kaia": "KAIA 저작권정책: 공공누리 제3유형(출처표시·변경금지, 게시물별 확인)",
    "iris": "IRIS 사업공고(정부 공고문) — 출처 표시",
}
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")
_FILENAME = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", re.I)


@dataclass(frozen=True)
class SiteSpec:
    id: str
    base_url: str
    list_path: str
    view_path: str = ""
    agency: str | None = None
    max_pages: int = 60
    ministry_code: str | None = None
    statuses: tuple[str, ...] = ("ancmIng", "ancmPre", "ancmEnd")
    enabled: bool = True

    @property
    def list_url(self) -> str:
        return f"{self.base_url}{self.list_path}"

    @property
    def view_url(self) -> str:
        return f"{self.base_url}{self.view_path or self.list_path}"


@dataclass(frozen=True)
class NoticeConfig:
    user_agent: str = "RRA research-proposal-app (internal research use)"
    since_days: int = 730
    max_notices: int = 500
    sites: tuple[SiteSpec, ...] = ()
    attachment_types: tuple[str, ...] = DEFAULT_ATTACHMENT_TYPES
    max_file_bytes: int = 50 * 1024 * 1024

    @classmethod
    def from_config(cls, raw: Mapping[str, Any]) -> NoticeConfig:
        sites: list[SiteSpec] = []
        for sid, s in (raw.get("sites") or {}).items():
            s = s or {}
            sites.append(
                SiteSpec(
                    id=str(sid),
                    base_url=str(s.get("base_url") or "").rstrip("/"),
                    list_path=str(s.get("list_path") or ""),
                    view_path=str(s.get("view_path") or ""),
                    agency=str(s["agency"]) if s.get("agency") else None,
                    max_pages=int(s.get("max_pages", 60)),
                    ministry_code=str(s["ministry_code"]) if s.get("ministry_code") else None,
                    statuses=tuple(str(x) for x in s.get("statuses") or cls._default_statuses()),
                    enabled=bool(s.get("enabled", True)),
                )
            )
        return cls(
            user_agent=str(raw.get("user_agent") or cls.user_agent),
            since_days=int(raw.get("since_days", 730)),
            max_notices=int(raw.get("max_notices", 500)),
            sites=tuple(sites),
            attachment_types=tuple(
                str(t).lower() for t in raw.get("attachment_types") or DEFAULT_ATTACHMENT_TYPES
            ),
            max_file_bytes=int(float(raw.get("max_file_mb", 50)) * 1024 * 1024),
        )

    @staticmethod
    def _default_statuses() -> tuple[str, ...]:
        return ("ancmIng", "ancmPre", "ancmEnd")


@dataclass
class CrawlReport:
    snapshot: str
    since: str
    notices: dict[str, int] = field(default_factory=dict)  # site → 저장 공고 수
    duplicates: int = 0
    files: int = 0
    bytes: int = 0
    skipped_files: dict[str, int] = field(default_factory=dict)
    held: list[str] = field(default_factory=list)
    errors: int = 0
    robots_blocked: int = 0
    carried: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Held(Exception):
    """연속 실패 3회 — 이 항목은 보류."""


class RndNoticeCrawler:
    def __init__(
        self,
        client: GuardedClient,
        config: NoticeConfig,
        *,
        root: Path,
        today: date | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.client = client
        self.config = config
        self.root = Path(root)  # 스냅샷 뿌리는 조립(composition)이 데이터 폴더 기준으로 준다
        self.today = today or date.today()
        self._sleep = sleep
        self._robots_cache: dict[str, RobotsRules] = {}
        self._consecutive = 0

    async def aclose(self) -> None:
        await self.client.aclose()

    @property
    def since(self) -> date:
        return self.today - timedelta(days=self.config.since_days)

    # ── 네트워크 (robots + 백오프) ───────────────────────
    async def _robots(self, site: SiteSpec) -> RobotsRules:
        if site.id not in self._robots_cache:
            try:
                _h, body, _s = await self.client.get_raw(f"{site.base_url}/robots.txt")
                text = body.decode("utf-8", "replace")
            except (FetchError, BlockedURL) as exc:
                logger.warning(
                    "rnd_notice.robots_unavailable site=%s error=%s", site.id, type(exc).__name__
                )
                text = ""
            self._robots_cache[site.id] = RobotsRules(text, user_agent=self.config.user_agent)
        return self._robots_cache[site.id]

    async def _request(
        self, site: SiteSpec, url: str, data: dict[str, Any] | None = None
    ) -> tuple[dict[str, str], bytes]:
        robots = await self._robots(site)
        if not robots.allowed(url):
            raise BlockedURL(f"robots.txt 가 금지한 경로: {strip_secrets(url)}")
        for attempt in range(len(BACKOFF_SEC) + 1):
            try:
                if data is None:
                    headers, body, _safe = await self.client.get_raw(url)
                else:
                    headers, body, _safe = await self.client.post_form(
                        url, data, accept="application/json, text/html;q=0.9, */*;q=0.1"
                    )
                self._consecutive = 0
                return headers, body
            except FetchError as exc:
                self._consecutive += 1
                logger.warning(
                    "rnd_notice.fetch_failed site=%s error=%s url=%s",
                    site.id,
                    type(exc).__name__,
                    strip_secrets(url),
                )
                if self._consecutive >= MAX_CONSECUTIVE_FAILURES:
                    self._consecutive = 0
                    raise Held(strip_secrets(url)) from exc
                if attempt < len(BACKOFF_SEC):
                    await self._sleep(BACKOFF_SEC[attempt])
        raise Held(strip_secrets(url))

    # ── 목록 ─────────────────────────────────────────────
    async def _kaia_pages(self, site: SiteSpec):
        page = 1
        while page <= site.max_pages:
            _h, body = await self._request(site, f"{site.list_url}?page={page}")
            rows, _total, last = parse_kaia_list(body.decode("utf-8", "replace"), site.list_url)
            yield rows
            if not rows or page >= last:
                return
            page += 1

    async def _iris_pages(self, site: SiteSpec, status: str):
        """한 공고 상태(접수중·예정·마감)의 쪽들.

        상태마다 따로 돌려 2년 경계 정지가 다음 상태를 막지 않게 한다."""
        page = 1
        while page <= site.max_pages:
            # 빈 *Arr 필드를 보내면 IRIS 가 0건을 돌려준다 — 부처 필터만 보낸다
            form = {"pageIndex": page, "ancmPrg": status}
            if site.ministry_code:
                form["blngGovdSe"] = form["blngGovdSeArr"] = site.ministry_code
            _h, body = await self._request(site, site.list_url, form)
            try:
                data = json.loads(body.decode("utf-8", "replace"))
            except ValueError:
                logger.warning("rnd_notice.iris_bad_json status=%s page=%d", status, page)
                return
            rows, _total, pages = parse_iris_list(data, site.view_url)
            yield rows
            if not rows or page >= pages:
                break
            page += 1

    async def explore(self) -> dict[str, Any]:
        """사이트별 전체 건수·첫 쪽 표본·robots 상태만 (내려받기 없음)."""
        out: dict[str, Any] = {
            "date": today_str(self.today),
            "since": self.since.isoformat(),
            "sites": [],
        }
        for site in self.config.sites:
            if not site.enabled:
                continue
            entry: dict[str, Any] = {"site": site.id, "base_url": site.base_url}
            try:
                robots = await self._robots(site)
                entry["robots"] = (
                    "empty"
                    if robots.empty
                    else ("allowed" if robots.allowed(site.list_url) else "blocked")
                )
                if site.id == "kaia":
                    _h, body = await self._request(site, f"{site.list_url}?page=1")
                    rows, total, last = parse_kaia_list(
                        body.decode("utf-8", "replace"), site.list_url
                    )
                    entry.update(
                        {"total": total, "pages": last, "sample": [r.title for r in rows[:3]]}
                    )
                else:
                    totals: dict[str, int | None] = {}
                    sample: list[str] = []
                    for status in site.statuses:
                        form = {
                            "pageIndex": 1,
                            "ancmPrg": status,
                            "blngGovdSe": site.ministry_code or "",
                            "blngGovdSeArr": site.ministry_code or "",
                        }
                        _h, body = await self._request(site, site.list_url, form)
                        rows, total, _pages = parse_iris_list(
                            json.loads(body.decode("utf-8", "replace")), site.view_url
                        )
                        totals[status] = total
                        sample.extend(r.title for r in rows[:2])
                    entry.update({"total": totals, "sample": sample[:4]})
            except (Held, BlockedURL, FetchError, ValueError) as exc:
                entry["held"] = f"{type(exc).__name__}"
            out["sites"].append(entry)
        return out

    # ── 내려받기 ───────────────────────────────────────────
    async def download(self, *, limit: int | None = None, incremental: bool = False) -> CrawlReport:
        snap = SnapshotDir(self.root, today_str(self.today))
        snap.ensure()
        report = CrawlReport(snapshot=snap.day, since=self.since.isoformat())
        cap = min(limit or self.config.max_notices, self.config.max_notices)
        previous: dict[str, dict[str, Any]] = {}
        if incremental:
            prev = latest_snapshot(self.root, before=snap.day)
            previous = read_manifest(prev) if prev is not None else {}
        existing = read_manifest(snap) if snap.manifest.is_file() else {}
        keys: dict[str, str] = {
            str(r.get("key")): nid for nid, r in existing.items() if r.get("key")
        }
        held_rows: list[tuple[SiteSpec, NoticeRow]] = []
        stored = len(existing)
        for site in self.config.sites:
            if not site.enabled or stored >= cap:
                continue
            report.notices.setdefault(site.id, 0)
            listings = (
                [self._kaia_pages(site)]
                if site.id == "kaia"
                else [self._iris_pages(site, status) for status in site.statuses]
            )
            try:
                for pages in listings:
                    await self._consume(
                        site, pages, snap, report, keys, previous, existing, held_rows, cap
                    )
                    stored = len([r for r in existing.values() if not r.get("duplicate_of")])
                    if stored >= cap:
                        break
            except Held as exc:
                report.held.append(str(exc))
            except (BlockedURL, FetchError) as exc:
                report.errors += 1
                logger.warning(
                    "rnd_notice.list_failed site=%s error=%s", site.id, type(exc).__name__
                )
        stored = len([r for r in existing.values() if not r.get("duplicate_of")])
        # 보류 항목 1회 재시도
        for site, row in held_rows:
            if stored >= cap:
                break
            await self._sleep(HELD_RETRY_GAP_SEC)
            try:
                rec = await self._one(site, row, snap, report, keys, previous)
            except (Held, BlockedURL, FetchError):
                continue
            if rec is not None:
                existing[f"{site.id}:{row.id}"] = rec
                if not rec.get("duplicate_of"):
                    stored += 1
                    report.notices[site.id] = report.notices.get(site.id, 0) + 1
                report.held = [h for h in report.held if row.id not in h]
        snap.write_summary(
            {
                **report.to_dict(),
                "config": {
                    "since_days": self.config.since_days,
                    "max_notices": self.config.max_notices,
                    "sites": [s.id for s in self.config.sites if s.enabled],
                    "attachment_types": list(self.config.attachment_types),
                },
                "terms": TERMS,
            }
        )
        return report

    async def _consume(
        self,
        site: SiteSpec,
        pages,
        snap: SnapshotDir,
        report: CrawlReport,
        keys: dict[str, str],
        previous: Mapping[str, dict[str, Any]],
        existing: dict[str, dict[str, Any]],
        held_rows: list[tuple[SiteSpec, NoticeRow]],
        cap: int,
    ) -> None:
        """한 목록(쪽 묶음)을 끝까지 — 2년 경계·상한에서 멈춘다."""
        stored = len([r for r in existing.values() if not r.get("duplicate_of")])
        async for rows in pages:
            stop = False
            for row in rows:
                if stored >= cap:
                    stop = True
                    break
                posted = parse_date(row.posted)
                if posted is not None and posted < self.since:
                    stop = True  # 오래된 공고부터는 더 보지 않는다 (최신순 목록)
                    break
                native_id = f"{site.id}:{row.id}"
                if native_id in existing:
                    continue
                try:
                    rec = await self._one(site, row, snap, report, keys, previous)
                except Held as exc:
                    held_rows.append((site, row))
                    report.held.append(str(exc))
                    continue
                except BlockedURL:
                    report.robots_blocked += 1
                    continue
                if rec is None:
                    continue
                existing[native_id] = rec
                if not rec.get("duplicate_of"):
                    stored += 1
                    report.notices[site.id] += 1
            if stop:
                return

    async def _one(
        self,
        site: SiteSpec,
        row: NoticeRow,
        snap: SnapshotDir,
        report: CrawlReport,
        keys: dict[str, str],
        previous: Mapping[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        native_id = f"{site.id}:{row.id}"
        agency = row.agency or site.agency
        key = notice_key(row.title, agency, row.posted)
        if key in keys and keys[key] != native_id:
            rec = {
                "native_id": native_id,
                "site": site.id,
                "title": row.title,
                "posted": row.posted,
                "url": row.url,
                "key": key,
                "duplicate_of": keys[key],
            }
            snap.append_manifest(rec)
            report.duplicates += 1
            return rec
        prev = previous.get(native_id)
        if prev and prev.get("title") == row.title and prev.get("period") == row.period:
            rec = {**prev, "carried_from": prev.get("snapshot") or prev.get("carried_from")}
            rec["snapshot"] = snap.day
            snap.append_manifest(rec)
            keys[key] = native_id
            report.carried += 1
            return rec
        _h, body = await self._request(site, row.url)
        html = body.decode("utf-8", "replace")
        detail = parse_kaia_detail(html, row.url) if site.id == "kaia" else parse_iris_detail(html)
        text = strip_pii(detail.body).strip()
        text_file = None
        if text:
            text_file = f"items/{site.id}/{safe_id(row.id)}.txt"
            snap.write_text(text_file, text)
        start, deadline = parse_period(detail.period or row.period)
        attachments = [
            await self._attachment(site, att, snap, report) for att in detail.attachments
        ]
        rec: dict[str, Any] = {
            "native_id": native_id,
            "site": site.id,
            "title": detail.title or row.title,
            "posted": detail.posted or row.posted,
            "period": detail.period or row.period,
            "start": start.isoformat() if start else None,
            "deadline": deadline.isoformat() if deadline else None,
            "program": row.program,
            "agency": agency,
            "ministry": row.ministry or ("국토교통부" if site.id == "kaia" else None),
            "status": row.status,
            "notice_no": row.notice_no or detail.info.get("공고번호"),
            "url": row.url,
            "text_file": text_file,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None,
            "attachments": attachments,
            "terms": TERMS.get(site.id),
            "snapshot": snap.day,
            "key": key,
        }
        snap.append_manifest(rec)
        keys[key] = native_id
        return rec

    async def _attachment(
        self, site: SiteSpec, att: dict[str, Any], snap: SnapshotDir, report: CrawlReport
    ) -> dict[str, Any]:
        name = str(att.get("name") or "")
        m = _EXT.search(name)
        ext = m.group(1).lower() if m else ""
        out: dict[str, Any] = {
            "name": name,
            "ext": ext or None,
            "url": att.get("url"),
            "downloaded": False,
        }
        if ext not in self.config.attachment_types:
            out["reason"] = "type"
            report.skipped_files["type"] = report.skipped_files.get("type", 0) + 1
            return out
        if not att.get("url"):
            out["reason"] = "post_download"  # IRIS: 세션 POST 다운로드 — 보류
            report.skipped_files["post_download"] = report.skipped_files.get("post_download", 0) + 1
            return out
        size = att.get("size")
        if isinstance(size, int) and size > self.config.max_file_bytes:
            out["reason"] = "too_large"
            report.skipped_files["too_large"] = report.skipped_files.get("too_large", 0) + 1
            return out
        try:
            headers, body = await self._request(site, str(att["url"]))
        except (Held, BlockedURL, FetchError) as exc:
            out["reason"] = type(exc).__name__
            report.errors += 1
            return out
        if len(body) > self.config.max_file_bytes:
            out["reason"] = "too_large"
            report.skipped_files["too_large"] = report.skipped_files.get("too_large", 0) + 1
            return out
        served = _disposition_name(headers.get("content-disposition"))
        if served:
            m2 = _EXT.search(served)
            if m2 and m2.group(1).lower() in self.config.attachment_types:
                ext = m2.group(1).lower()
        sha = hashlib.sha256(body).hexdigest()
        rel = content_path("files", sha, ext)
        snap.write_bytes(rel, body)
        report.files += 1
        report.bytes += len(body)
        out.update(
            {
                "downloaded": True,
                "sha256": sha,
                "path": rel,
                "ext": ext,
                "bytes": len(body),
                "snapshot": snap.day,
            }
        )
        return out


def _disposition_name(value: str | None) -> str | None:
    m = _FILENAME.search(value or "")
    if not m:
        return None
    return unquote(m.group(1) or m.group(2) or "")
