"""공사 홈페이지(info.korail.com) 탐색·내려받기 (`rra crawl korail`).

- 네트워크는 GuardedClient 로만 (허용목록·https·크기 상한). 같은 호스트에 2초 간격, 동시 1.
- robots.txt 의 Disallow 는 지킨다 (비어 있으면 모두 허용). User-Agent 는 설정의 user_agent.
- 403·429·전송 오류는 2s → 5s → 10s 로 물러난다. 한 항목이 연속 3회 실패하면 "보류" 로 두고 계속,
  맨 끝에 보류 항목을 10s 간격으로 한 번 더 시도한다.
- 증분(incremental): 이전 스냅샷의 항목 서명(제목·게시일·첨부 이름)이 같으면 다시 받지 않고
  레코드를 이어 적는다(carried_from). 목록에서 사라진 항목은 "원본 삭제됨"(removed) 으로 표시만
  한다 — 지우지 않는다.
- 본문·첨부는 비신뢰. 본문은 개인정보 제거 뒤 저장. 첨부 파일은 저장만 하고 열지 않는다(파싱은
  샌드박스). PDF 텍스트 레이어 여부만 선택적 probe(샌드박스)로 표시한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit, urlunsplit

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient
from rra.adapters.sources.korail_web import _html
from rra.adapters.sources.korail_web._media import IMAGE_EXTS, IMAGE_TYPES, image_dims, image_kind
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.adapters.sources.korail_web.robots import RobotsRules
from rra.adapters.sources.korail_web.snapshot import (
    SnapshotDir,
    content_path,
    item_signature,
    latest_snapshot,
    load_index,
    read_manifest,
    safe_id,
    save_index,
    today_str,
)

logger = logging.getLogger("rra.sources.korail_web")

MenuKind = Literal["contents", "board", "preinfo"]
BACKOFF_SEC = (2.0, 5.0, 10.0)
HELD_RETRY_GAP_SEC = 10.0
MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_ATTACHMENT_TYPES = ("pdf", "hwp", "hwpx", "xlsx", "xls", "docx", "pptx")
MIN_PDF_CHARS_PER_PAGE = 20
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")


@dataclass(frozen=True)
class MenuSpec:
    id: str
    path: str  # "홍보센터 > 홍보 > 보도자료"
    kind: MenuKind
    key: str
    doc_type: str = "policy"
    bbs_no: str | None = None
    since: str | None = None  # YYYY-MM-DD — 이 날짜 이전 게시글은 받지 않는다 (board 만)
    attachments: bool = True
    attachment_images: bool = True  # jpg·png 첨부를 내려받을지 (false: 메타데이터만)
    body_images: bool = True
    max_pages: int | None = None

    @classmethod
    def from_config(cls, raw: Mapping[str, Any]) -> MenuSpec:
        kind = str(raw.get("kind") or "contents")
        if kind not in ("contents", "board", "preinfo"):
            raise ValueError(f"korail_web.yaml menus[{raw.get('id')}].kind 가 잘못됨: {kind}")
        since = raw.get("since")
        return cls(
            id=str(raw["id"]),
            path=str(raw.get("path") or raw["id"]),
            kind=kind,  # type: ignore[arg-type]
            key=str(raw["key"]),
            doc_type=str(raw.get("doc_type") or "policy"),
            bbs_no=str(raw["bbs_no"]) if raw.get("bbs_no") is not None else None,
            since=str(since) if since else None,
            attachments=bool(raw.get("attachments", True)),
            attachment_images=bool(raw.get("attachment_images", True)),
            body_images=bool(raw.get("body_images", True)),
            max_pages=int(raw["max_pages"]) if raw.get("max_pages") else None,
        )


@dataclass(frozen=True)
class CrawlConfig:
    base_url: str = "https://info.korail.com"
    site_path: str = "/info"
    user_agent: str = "RRA research-proposal-app (internal research use)"
    menus: tuple[MenuSpec, ...] = ()
    attachment_types: tuple[str, ...] = DEFAULT_ATTACHMENT_TYPES
    max_file_bytes: int = 50 * 1024 * 1024
    max_pages_per_board: int = 700

    @classmethod
    def from_config(cls, raw: Mapping[str, Any]) -> CrawlConfig:
        return cls(
            base_url=str(raw.get("base_url") or "https://info.korail.com").rstrip("/"),
            site_path="/" + str(raw.get("site_path") or "/info").strip("/"),
            user_agent=str(raw.get("user_agent") or cls.user_agent),
            menus=tuple(MenuSpec.from_config(m) for m in raw.get("menus") or []),
            attachment_types=tuple(
                str(t).lower() for t in raw.get("attachment_types") or DEFAULT_ATTACHMENT_TYPES
            ),
            max_file_bytes=int(float(raw.get("max_file_mb", 50)) * 1024 * 1024),
            max_pages_per_board=int(raw.get("max_pages_per_board", 700)),
        )

    def url(self, page: str, **params: Any) -> str:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        return f"{self.base_url}{self.site_path}/{page}" + (f"?{query}" if query else "")


@dataclass
class CrawlReport:
    snapshot: str
    incremental: bool
    items: dict[str, int] = field(default_factory=dict)  # menu → 저장 항목 수 (carried 포함)
    carried: dict[str, int] = field(default_factory=dict)
    files: int = 0
    images: int = 0
    bytes: int = 0
    skipped_files: dict[str, int] = field(default_factory=dict)  # reason → count
    held: list[str] = field(default_factory=list)  # 보류 (URL, 비밀 제거)
    removed: int = 0
    errors: int = 0
    robots_blocked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Held(Exception):
    """연속 실패 3회 — 이 항목은 보류."""


PdfProbe = Callable[[Path], Awaitable[dict[str, Any] | None]]


def strip_secrets(url: str) -> str:
    """기록용 URL — userinfo 만 뗀다. 이 사이트의 `key`·`bbsNo` 는 메뉴 번호이지 비밀이 아니다
    (_base.strip_secrets 는 `key` 를 비밀 파라미터로 보고 지운다)."""
    p = urlsplit(url)
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    return urlunsplit((p.scheme, host, p.path, p.query, ""))


class KorailWebCrawler:
    def __init__(
        self,
        client: GuardedClient,
        config: CrawlConfig,
        root: Path,
        *,
        today: Callable[[], date] = date.today,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        pdf_probe: PdfProbe | None = None,
    ):
        self.client = client
        self.config = config
        self.root = Path(root)
        self._today = today
        self._sleep = sleep
        self._pdf_probe = pdf_probe
        self.robots: RobotsRules | None = None
        self._consecutive = 0
        self._probed: dict[str, dict[str, Any] | None] = {}  # sha256 → PDF probe 결과 (한 번만)

    async def aclose(self) -> None:
        await self.client.aclose()

    # ── robots ───────────────────────────────────────────
    async def load_robots(self) -> RobotsRules:
        if self.robots is None:
            url = f"{self.config.base_url}/robots.txt"
            try:
                _h, body, _s = await self.client.get_raw(url)
                text = body.decode("utf-8", "replace")
            except (FetchError, BlockedURL) as exc:
                logger.warning("korail_web.robots_unavailable error=%s", type(exc).__name__)
                text = ""
            self.robots = RobotsRules(text, user_agent=self.config.user_agent)
        return self.robots

    async def _fetch(self, url: str) -> tuple[dict[str, str], bytes]:
        """robots 확인 + 백오프 재시도. 연속 3회 실패면 Held."""
        robots = await self.load_robots()
        if not robots.allowed(url):
            raise BlockedURL(f"robots.txt 가 금지한 경로: {strip_secrets(url)}")
        for attempt in range(len(BACKOFF_SEC) + 1):
            try:
                headers, body, _safe = await self.client.get_raw(url)
                self._consecutive = 0
                return headers, body
            except FetchError as exc:
                self._consecutive += 1
                logger.warning(
                    "korail_web.fetch_failed error=%s url=%s",
                    type(exc).__name__,
                    strip_secrets(url),
                )
                if self._consecutive >= MAX_CONSECUTIVE_FAILURES:
                    self._consecutive = 0
                    raise Held(strip_secrets(url)) from exc
                if attempt < len(BACKOFF_SEC):
                    await self._sleep(BACKOFF_SEC[attempt])
        raise Held(strip_secrets(url))

    async def _fetch_html(self, url: str) -> str:
        _headers, body = await self._fetch(url)
        return body.decode("utf-8", "replace")

    # ── 목록 ─────────────────────────────────────────────
    def _list_url(self, menu: MenuSpec, page: int) -> str:
        if menu.kind == "board":
            return self.config.url(
                "selectBbsNttList.do", bbsNo=menu.bbs_no, key=menu.key, pageIndex=page
            )
        return self.config.url("selectInfoRelWebList.do", key=menu.key, pageIndex=page)

    def _parse_list(self, menu: MenuSpec, html: str, url: str) -> _html.ListPage:
        if menu.kind == "board":
            return _html.parse_board_list(html, url)
        return _html.parse_preinfo_list(html, url)

    def _parse_item(self, menu: MenuSpec, html: str, url: str) -> _html.PageItem:
        if menu.kind == "board":
            return _html.parse_board_view(html, url)
        if menu.kind == "preinfo":
            return _html.parse_preinfo_detail(html, url)
        return _html.parse_contents(html, url)

    async def _list_rows(
        self, menu: MenuSpec, report: CrawlReport | None = None
    ) -> list[_html.ListRow]:
        """게시판·사전정보공표 목록 전체 (since·max_pages 로 자른다)."""
        rows: list[_html.ListRow] = []
        seen: set[str] = set()
        pages_total: int | None = None
        limit = menu.max_pages or self.config.max_pages_per_board
        page = 1
        while page <= limit:
            url = self._list_url(menu, page)
            try:
                listing = self._parse_list(menu, await self._fetch_html(url), url)
            except Held:
                if report is not None:
                    report.held.append(url)
                break
            except BlockedURL as exc:  # robots.txt 가 목록 경로를 막음 — 이 메뉴는 건너뛴다
                if report is not None:
                    report.robots_blocked += 1
                logger.warning("korail_web.blocked %s", exc)
                break
            if pages_total is None:
                pages_total = listing.pages
            fresh = [r for r in listing.rows if r.native_id not in seen]
            if not fresh:
                break
            stop = False
            for r in fresh:
                if menu.since and r.posted and r.posted < menu.since:
                    stop = True
                    continue
                seen.add(r.native_id)
                rows.append(r)
            if stop or (pages_total is not None and page >= pages_total):
                break
            page += 1
        return rows

    # ── 탐색 ─────────────────────────────────────────────
    async def explore(self) -> dict[str, Any]:
        robots = await self.load_robots()
        out: dict[str, Any] = {
            "date": today_str(self._today()),
            "base_url": self.config.base_url,
            "robots_empty": robots.empty,
            "robots_text": robots.text[:2000],
            "menus": [],
        }
        for menu in self.config.menus:
            row: dict[str, Any] = {
                "id": menu.id,
                "path": menu.path,
                "kind": menu.kind,
                "doc_type": menu.doc_type,
            }
            try:
                if menu.kind == "contents":
                    url = self.config.url("contents.do", key=menu.key)
                    item = self._parse_item(menu, await self._fetch_html(url), url)
                    row.update(
                        posts=1,
                        chars=len(item.text),
                        attachments=len(item.attachments),
                        attachment_kinds=_kinds([a.name for a in item.attachments]),
                        images=len(item.images),
                        terms=item.terms,
                    )
                else:
                    url = self._list_url(menu, 1)
                    first = self._parse_list(menu, await self._fetch_html(url), url)
                    row.update(posts=first.total, pages=first.pages)
                    dates = [r.posted for r in first.rows if r.posted]
                    row["latest"] = max(dates) if dates else None
                    kinds: dict[str, int] = {}
                    for r in first.rows:
                        for k in r.file_kinds:
                            kinds[k] = kinds.get(k, 0) + 1
                    row["attachment_kinds_page1"] = kinds
                    if first.pages and first.pages > 1:
                        last_url = self._list_url(menu, first.pages)
                        last = self._parse_list(menu, await self._fetch_html(last_url), last_url)
                        dates = [r.posted for r in last.rows if r.posted]
                        row["earliest"] = min(dates) if dates else None
                    else:
                        row["earliest"] = min(dates) if dates else None
                    if menu.since:
                        row["since"] = menu.since
            except Held as exc:
                row["held"] = str(exc)
            except BlockedURL as exc:
                row["blocked"] = str(exc)
            out["menus"].append(row)
        return out

    # ── 내려받기 ─────────────────────────────────────────
    async def download(self, *, incremental: bool = False) -> CrawlReport:
        day = today_str(self._today())
        snap = SnapshotDir(self.root, day)
        snap.ensure()
        prev = latest_snapshot(self.root, before=day) if incremental else None
        prev_items = read_manifest(prev) if prev is not None else {}
        index = load_index(self.root)
        report = CrawlReport(snapshot=day, incremental=incremental)
        held_items: list[tuple[MenuSpec, _html.ListRow]] = []
        seen_ids: set[str] = set()

        for menu in self.config.menus:
            report.items.setdefault(menu.id, 0)
            if menu.kind == "contents":
                url = self.config.url("contents.do", key=menu.key)
                row = _html.ListRow(
                    native_id=f"contents:{menu.key}",
                    url=url,
                    title=menu.path.split(" > ")[-1],
                    posted=None,
                )
                rows = [row]
            else:
                rows = await self._list_rows(menu, report)
            for row in rows:
                seen_ids.add(row.native_id)
                try:
                    await self._process(menu, row, snap, prev_items, index, report, incremental)
                except Held:
                    held_items.append((menu, row))
                    report.held.append(strip_secrets(row.url))
                except BlockedURL as exc:
                    report.robots_blocked += 1
                    logger.warning("korail_web.blocked %s", exc)

        # 사라진 항목 — 이전 스냅샷에는 있었고 이번 목록에는 없다 (지우지 않고 표시만)
        for native_id, rec in prev_items.items():
            if native_id in seen_ids or rec.get("removed"):
                continue
            menu = next((m for m in self.config.menus if m.id == rec.get("menu")), None)
            if menu is None:
                continue
            if menu.since and rec.get("posted") and str(rec["posted"]) < menu.since:
                continue  # 수집 범위 밖이라 안 본 것 — 삭제로 보지 않는다
            snap.append_manifest(
                {**rec, "removed": True, "removed_noted": day, "note": "원본 삭제됨"}
            )
            report.removed += 1

        # 보류 항목 1회 재시도 (10초 간격)
        if held_items:
            retry = list(held_items)
            report.held = []
            for menu, row in retry:
                await self._sleep(HELD_RETRY_GAP_SEC)
                try:
                    await self._process(menu, row, snap, prev_items, index, report, incremental)
                except (Held, BlockedURL):
                    report.held.append(strip_secrets(row.url))

        save_index(self.root, index)
        snap.write_summary(
            {
                **report.to_dict(),
                "finished": datetime.now(UTC).isoformat(timespec="seconds"),
                "base_url": self.config.base_url,
                "user_agent": self.config.user_agent,
                "menus": [m.id for m in self.config.menus],
            }
        )
        return report

    async def _process(
        self,
        menu: MenuSpec,
        row: _html.ListRow,
        snap: SnapshotDir,
        prev_items: Mapping[str, dict[str, Any]],
        index: dict[str, dict[str, Any]],
        report: CrawlReport,
        incremental: bool,
    ) -> None:
        prev = prev_items.get(row.native_id)
        if incremental and prev is not None and menu.kind != "contents":
            names = [a.get("name", "") for a in prev.get("attachments", [])]
            # 목록만으로 아는 서명: 제목·게시일·파일 종류. 같으면 상세를 다시 받지 않는다
            if prev.get("list_signature") == _list_sig(row) and not prev.get("removed"):
                snap.append_manifest(
                    {**prev, "carried_from": prev.get("snapshot", ""), "snapshot": snap.day}
                )
                report.items[menu.id] += 1
                report.carried[menu.id] = report.carried.get(menu.id, 0) + 1
                _ = names
                return
        if row.direct_file:  # 갤러리형 — 상세 페이지 없음. 제목 + 파일 + 표지
            item = _html.PageItem(
                title=row.title,
                posted=row.posted,
                text=row.title,
                attachments=[_html.Attachment(name=f"{row.title}.pdf", url=row.direct_file)],
                images=[_html.Image(src=row.cover, alt=row.title, caption="", context="")]
                if row.cover
                else [],
            )
        else:
            html = await self._fetch_html(row.url)
            item = self._parse_item(menu, html, row.url)
        title = item.title or row.title
        text = strip_pii(item.text)
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rel_text = f"items/{menu.id}/{safe_id(row.native_id)}.txt"
        snap.write_text(rel_text, text)
        attachments: list[dict[str, Any]] = []
        for att in item.attachments:
            attachments.append(await self._attachment(menu, att, snap, index, report))
        images: list[dict[str, Any]] = []
        if menu.body_images:
            for img in item.images:
                images.append(await self._image(menu, img, snap, index, report))
        else:
            images = [
                {
                    "src": i.src,
                    "alt": i.alt,
                    "caption": i.caption,
                    "context": strip_pii(i.context),
                    "downloaded": False,
                    "reason": "policy",
                }
                for i in item.images
            ]
        record = {
            "native_id": row.native_id,
            "menu": menu.id,
            "menu_path": menu.path,
            "doc_type": menu.doc_type,
            "url": strip_secrets(row.url),
            "title": title,
            "posted": item.posted or row.posted,
            "department": strip_pii(item.department) if item.department else None,
            "text_file": rel_text,
            "text_sha256": text_sha,
            "text_chars": len(text),
            "attachments": attachments,
            "images": images,
            "terms": item.terms,
            "list_signature": _list_sig(row),
            "signature": item_signature(
                title, item.posted or row.posted, [a.name for a in item.attachments]
            ),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "snapshot": snap.day,
            "removed": False,
        }
        snap.append_manifest(record)
        report.items[menu.id] += 1

    async def _attachment(
        self,
        menu: MenuSpec,
        att: _html.Attachment,
        snap: SnapshotDir,
        index: dict[str, dict[str, Any]],
        report: CrawlReport,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {"name": att.name, "url": strip_secrets(att.url), "downloaded": False}
        ext = _ext_of(att.name)
        rec["ext"] = ext
        is_image = ext in IMAGE_EXTS
        if not menu.attachments:
            return _skip(rec, report, "policy")
        if is_image and not menu.attachment_images:
            return _skip(rec, report, "policy_images")
        if ext and not is_image and ext not in self.config.attachment_types:
            return _skip(rec, report, "type")
        known = index.get(att.url)
        if known and (self.root / "snapshots" / known["snapshot"] / known["path"]).is_file():
            # 같은 URL 을 이미 받았다 — 내용은 내용 주소 경로에 있다 (다시 받지 않는다)
            rec.update(
                sha256=known["sha256"],
                bytes=known["bytes"],
                path=known["path"],
                snapshot=known["snapshot"],
                downloaded=True,
                reused=True,
            )
            for k in ("text_layer", "pages", "served_name", "ext"):
                if k in known:
                    rec[k] = known[k]
            return rec
        headers, body = await self._fetch(att.url)
        if len(body) > self.config.max_file_bytes:
            return _skip(rec, report, "too_large")
        served = _html.filename_from_disposition(headers.get("content-disposition"))
        if served:
            rec["served_name"] = served
        ext2 = (
            _ext_of(served or "") or _ext_from_type(headers.get("content-type")) or image_kind(body)
        )
        if ext2 and ext2 != ext:
            if (ext2 in IMAGE_EXTS and not menu.attachment_images) or (
                ext2 not in IMAGE_EXTS and ext2 not in self.config.attachment_types
            ):
                return _skip(rec, report, "type")
            ext = ext2
            rec["ext"] = ext
        if not ext:
            return _skip(rec, report, "type")
        sha = hashlib.sha256(body).hexdigest()
        kind = "images" if ext in IMAGE_EXTS else "files"
        rel = content_path(kind, sha, ext)
        snap.write_bytes(rel, body)
        rec.update(
            sha256=sha,
            bytes=len(body),
            path=rel,
            snapshot=snap.day,
            downloaded=True,
            content_type=(headers.get("content-type") or "")[:60],
        )
        report.files += 1
        report.bytes += len(body)
        if ext == "pdf" and self._pdf_probe is not None:
            if sha not in self._probed:
                self._probed[sha] = await self._pdf_probe(snap.path / rel)
            probe = self._probed[sha]
            if probe is not None:
                pages = int(probe.get("pages") or 0)
                chars = int(probe.get("text_chars") or 0)
                rec["pages"] = pages
                rec["text_layer"] = bool(pages) and chars >= MIN_PDF_CHARS_PER_PAGE * pages
        index[att.url] = {
            k: rec[k]
            for k in (
                "sha256",
                "bytes",
                "path",
                "snapshot",
                "text_layer",
                "pages",
                "served_name",
                "ext",
            )
            if k in rec
        }
        return rec

    async def _image(
        self,
        menu: MenuSpec,
        img: _html.Image,
        snap: SnapshotDir,
        index: dict[str, dict[str, Any]],
        report: CrawlReport,
    ) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "src": strip_secrets(img.src),
            "alt": img.alt,
            "caption": img.caption,
            "context": strip_pii(img.context),
            "downloaded": False,
        }
        host = urlsplit(img.src).hostname or ""
        if host not in self.client.allowed:
            return _skip(rec, report, "host")
        known = index.get(img.src)
        if known and (self.root / "snapshots" / known["snapshot"] / known["path"]).is_file():
            rec.update(
                {
                    k: known[k]
                    for k in ("sha256", "bytes", "path", "snapshot", "width", "height")
                    if k in known
                }
            )
            rec.update(downloaded=True, reused=True)
            return rec
        try:
            headers, body = await self._fetch(img.src)
        except Held:
            report.held.append(strip_secrets(img.src))
            return _skip(rec, report, "held")
        except BlockedURL:
            return _skip(rec, report, "blocked")
        ctype = (headers.get("content-type") or "").split(";")[0].strip().lower()
        ext = image_kind(body) or IMAGE_TYPES.get(ctype) or _ext_of(urlsplit(img.src).path)
        if ext not in IMAGE_EXTS or len(body) > self.config.max_file_bytes:
            return _skip(rec, report, "type" if ext not in IMAGE_EXTS else "too_large")
        sha = hashlib.sha256(body).hexdigest()
        rel = content_path("images", sha, ext)
        snap.write_bytes(rel, body)
        dims = image_dims(body)
        rec.update(
            sha256=sha, bytes=len(body), path=rel, snapshot=snap.day, downloaded=True, ext=ext
        )
        if dims:
            rec["width"], rec["height"] = dims
        report.images += 1
        report.bytes += len(body)
        index[img.src] = {
            k: rec[k]
            for k in ("sha256", "bytes", "path", "snapshot", "width", "height")
            if k in rec
        }
        return rec


def _skip(rec: dict[str, Any], report: CrawlReport, reason: str) -> dict[str, Any]:
    rec["reason"] = reason
    report.skipped_files[reason] = report.skipped_files.get(reason, 0) + 1
    return rec


_TYPE_EXT = {
    "application/pdf": "pdf",
    "application/x-hwp": "hwp",
    "application/haansofthwp": "hwp",
    "application/vnd.hancom.hwpx": "hwpx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def _ext_from_type(content_type: str | None) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    return _TYPE_EXT.get(ctype) or IMAGE_TYPES.get(ctype, "")


def _ext_of(name: str) -> str:
    m = _EXT.search(name or "")
    ext = m.group(1).lower() if m else ""
    return "jpg" if ext == "jpeg" else ext


def _kinds(names: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in names:
        k = _ext_of(n) or "?"
        out[k] = out.get(k, 0) + 1
    return out


def _list_sig(row: _html.ListRow) -> str:
    return item_signature(row.title, row.posted, list(row.file_kinds))
