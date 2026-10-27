"""MofeEvaluationSource — 기획재정부 보도자료 게시판에서 "공공기관 경영실적 평가 결과" (P2-5).

목록 `nw/nes/nesdta.do?searchBbsId1=<bbs>&menuNo=&searchCondition=1&searchKeyword1=<질의>`
(egov 게시판, GET),
행 `<h3><a href="javascript:fn_egov_select('MOSF_…')">제목</a></h3>` + `.date`·`.depart`,
상세 `nw/nes/detailNesDtaView.do?searchNttId=&menuNo=&bbsId=&searchBbsId1=` 의 첨부
`/com/cmm/fms/FileDown.do?atchFileId=&fileSn=` (zip 전체받기 `AtchZipFileDown.do` 는 쓰지 않는다 —
보안 B).
해석은 순수 함수(parse_list·parse_detail), 파일은 샌드박스에서 텍스트로.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

from pydantic import ValidationError

from rra.adapters.sources._base import BlockedURL, FetchError, GuardedClient
from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._models import ExtractResult
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.audit._common import ext_of, strip_size
from rra.adapters.sources.korail_web._pii import strip_pii
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.mofe")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]
PARSEABLE = frozenset({"pdf", "hwpx", "hwp"})
PREFER = ("pdf", "hwpx", "hwp")
MIN_CHARS = 80
_ROW = re.compile(
    r"<h3>\s*<a href=\"javascript:fn_egov_select\('([^']+)'\);\">(.*?)</a>\s*</h3>(.*?)</li>", re.S
)
_DATE_DOT = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
_DEPART = re.compile(r'class="depart">([^<]*)<')
_FILE = re.compile(r'href="([^"]*?/com/cmm/fms/FileDown\.do[^"]*)"[^>]*>(.*?)</a>', re.S)
_YEAR = re.compile(r"(\d{4})년도")
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class MofeRow:
    ntt_id: str
    title: str
    posted: str | None
    department: str | None


@dataclass(frozen=True)
class MofeDetail:
    title: str
    posted: str | None
    files: list[tuple[str, str]] = field(default_factory=list)  # (name, url)


def _clean(s: str) -> str:
    return " ".join(htmllib.unescape(_TAG.sub(" ", s)).split())


def _date_of(text: str) -> str | None:
    m = _DATE_DOT.search(text)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_list(html: str) -> list[MofeRow]:
    rows: list[MofeRow] = []
    for m in _ROW.finditer(html):
        tail = m.group(3)
        dep = _DEPART.search(tail)
        rows.append(
            MofeRow(
                ntt_id=m.group(1),
                title=_clean(m.group(2))[:300],
                posted=_date_of(tail),
                department=_clean(dep.group(1)) if dep else None,
            )
        )
    return rows


def parse_detail(html: str, page_url: str) -> MofeDetail:
    """첨부 (이름, URL) — 같은 fileSn 은 한 번. 이름 옆 용량 표기는 뗀다. jsessionid 는 URL 에서
    뺀다."""
    title_m = re.search(
        r"<h3(?![^>]*<a)[^>]*>(?!\s*<a)(.*?)</h3>", html, re.S
    )  # 첫 제목 (목록 h3 는 <a> 포함)
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _FILE.finditer(html):
        url = re.sub(r";jsessionid=[^?]*", "", htmllib.unescape(m.group(1)))
        url = urljoin(page_url, url)
        name = strip_size(_clean(m.group(2)))
        if not ext_of(name) or url in seen:
            continue
        seen.add(url)
        files.append((name[:200], url))
    start = title_m.end() if title_m else 0
    end = html.find("FileDown.do", start)
    return MofeDetail(
        title=_clean(title_m.group(1))[:300] if title_m else "",
        posted=_date_of(
            html[start : end if end > 0 else len(html)]
        ),  # 제목 뒤 ~ 첫 첨부 사이의 날짜만
        files=files,
    )


class MofeEvaluationSource:
    """SourcePort + ProbingSource. source='mofe', doc_type='audit'."""

    source = "mofe"

    def __init__(
        self,
        client: GuardedClient,
        *,
        base_url: str = "https://mofe.go.kr",
        list_path: str = "/nw/nes/nesdta.do",
        detail_path: str = "/nw/nes/detailNesDtaView.do",
        bbs_id: str = "MOSFBBS_000000000028",
        menu_no: str = "4010100",
        queries: Sequence[str] = ("경영실적 평가 결과",),
        title_filter: Sequence[str] = ("경영실적 평가",),
        store_dir: Path,
        limits: SandboxLimits,
        max_file_bytes: int = 50 * 1024 * 1024,
        runner: Runner = run_parser,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.list_path = list_path
        self.detail_path = detail_path
        self.bbs_id = bbs_id
        self.menu_no = menu_no
        self.queries = list(queries)
        self.title_filter = [t for t in title_filter if t]
        self.store_dir = Path(store_dir)
        self.limits = limits
        self.max_file_bytes = max_file_bytes
        self._runner = runner

    def __repr__(self) -> str:
        return f"MofeEvaluationSource(queries={len(self.queries)})"

    async def aclose(self) -> None:
        await self.client.aclose()

    def _list_url(self, query: str, page: int = 1) -> str:
        q = urlencode(
            {
                "searchBbsId1": self.bbs_id,
                "menuNo": self.menu_no,
                "bbsId": self.bbs_id,
                "searchMenu": self.menu_no,
                "listType": 1,
                "searchSort": 1,
                "pageIndex": page,
                "searchCondition": 1,
                "searchKeyword1": query,
            }
        )
        return f"{self.base_url}{self.list_path}?{q}"

    def _detail_url(self, ntt_id: str) -> str:
        q = urlencode(
            {
                "searchNttId": ntt_id,
                "menuNo": self.menu_no,
                "bbsId": self.bbs_id,
                "searchBbsId1": self.bbs_id,
            }
        )
        return f"{self.base_url}{self.detail_path}?{q}"

    async def probe(self) -> dict[str, Any]:
        _h, body, _s = await self.client.get_raw(self._list_url(self.queries[0]))
        rows = parse_list(body.decode("utf-8", "replace"))
        return {"rows": len(rows), "titles": [r.title for r in rows[:3]]}

    def _wanted(self, row: MofeRow) -> bool:
        squashed = row.title.replace(" ", "")
        return not self.title_filter or any(
            t.replace(" ", "") in squashed for t in self.title_filter
        )

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        rows: dict[str, MofeRow] = {}
        for q in [query] if query else self.queries:
            try:
                _h, body, _s = await self.client.get_raw(self._list_url(q))
            except (FetchError, BlockedURL) as exc:
                logger.warning("mofe.list_failed error=%s", type(exc).__name__)
                continue
            for r in parse_list(body.decode("utf-8", "replace")):
                if self._wanted(r):
                    rows.setdefault(r.ntt_id, r)
        out: list[dict[str, Any]] = []
        for r in rows.values():
            if len(out) >= limit:
                break
            url = self._detail_url(r.ntt_id)
            try:
                _h, body, _s = await self.client.get_raw(url)
            except (FetchError, BlockedURL) as exc:
                logger.warning("mofe.detail_failed error=%s id=%s", type(exc).__name__, r.ntt_id)
                continue
            detail = parse_detail(body.decode("utf-8", "replace"), url)
            picked = sorted(
                (f for f in detail.files if ext_of(f[0]) in PARSEABLE),
                key=lambda f: PREFER.index(ext_of(f[0])),
            )
            for name, file_url in picked[:1]:  # 같은 보도자료의 pdf·hwpx 중 하나만
                raw = await self._attachment(name, file_url)
                if raw is not None:
                    out.append(
                        {
                            "id": r.ntt_id,
                            "url": url,
                            "title": detail.title or r.title,
                            "posted": r.posted or detail.posted,  # 목록 등록일이 확실하다
                            "department": r.department,
                            **raw,
                        }
                    )
        return out

    async def _attachment(self, name: str, url: str) -> dict[str, Any] | None:
        ext = ext_of(name)
        try:
            _h, body, _s = await self.client.get_raw(url)
        except (FetchError, BlockedURL) as exc:
            logger.warning("mofe.file_failed error=%s", type(exc).__name__)
            return None
        if len(body) > self.max_file_bytes:
            return None
        sha = hashlib.sha256(body).hexdigest()
        self.store_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.store_dir / f"{sha}.{ext}"
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(body)
        try:
            vf = open_validated(path, max_bytes=self.max_file_bytes, allowed=PARSEABLE)
        except FileRejected as exc:
            logger.warning("mofe.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
            return None
        with vf:
            try:
                result = ExtractResult.model_validate(
                    await self._runner(vf.fd, vf.fmt, self.limits)
                )
            except (SandboxError, ValidationError) as exc:
                logger.warning("mofe.rejected error=%s sha=%s", type(exc).__name__, sha[:8])
                return None
        if len(result.text.strip()) < MIN_CHARS:
            return None
        return {
            "sha256": sha,
            "fmt": vf.fmt,
            "file_name": name,
            "file_url": url,
            "text": result.text,
            "toc": list(result.toc),
            "pages": result.pages,
        }

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_mofe_item(raw)


def normalize_mofe_item(raw: dict[str, Any]) -> Document:
    text = strip_pii(str(raw["text"])).strip()
    if not text:
        raise ValueError("본문 없음")
    title = str(raw.get("title") or "")[:300] or text.splitlines()[0][:120]
    posted = raw.get("posted")
    pub = date.fromisoformat(str(posted)[:10]) if isinstance(posted, str) and posted else None
    year = _YEAR.search(title)
    return Document(
        doc_id=f"mofe:{raw['id']}",
        source="mofe",
        doc_type="audit",
        title=title,
        body=text,
        pub_date=pub,
        orgs=[],
        lang="ko",
        url=str(raw.get("file_url") or raw.get("url") or "") or None,
        toc=[str(t) for t in (raw.get("toc") or [])][:200] or None,
        text_basis="full_text",
        visibility="public",
        raw={
            "kind": "management_evaluation",
            "evaluation_year": int(year.group(1)) if year else None,
            "mofe_department": raw.get("department"),
            "file_name": raw.get("file_name"),
            "fmt": raw.get("fmt"),
            "pages": raw.get("pages"),
            "page_url": raw.get("url"),
            "sha256": raw.get("sha256"),
        },
    )
