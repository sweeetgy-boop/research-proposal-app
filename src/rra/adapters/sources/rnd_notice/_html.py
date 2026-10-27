"""정부 R&D 사업공고 목록·상세 해석 (순수, P2-7).

KAIA 사업공고(`/KAIA/contents/K30101000000.do`): 목록 `table.board_table tr`(제목
a[href*=schM=view&id=], 사업명·공고기간·
등록일 td[data-content]), 전체 건수 `.blt_count b`, 쪽 `?page=N`. 상세 `.bbs_viewbox .subject
strong`, 표 "공고기간",
첨부 `ul.attach_list li`(em 이름, i 크기, a.attach_btn.down 내려받기 `/afile/fileDownload/<id>`).
IRIS 사업공고: 목록은 JSON(`listBsnsAncmBtinSitu`, `paginationInfo`), 상세 `li.write strong/span`,
본문 `.se-contents`,
첨부 `f_bsnsAncm_downloadAtchFile('docId','fileId','이름','크기')` (POST 다운로드 — 이름만 기록).
"""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from rra.adapters.sources.korail_web._html import Node, parse_html

_PAGE = re.compile(r"[?&]page=(\d+)")
_SIZE = re.compile(r"\(\s*([\d.,]+)\s*(KB|MB|GB|B)\s*\)", re.I)
_IRIS_ATCH = re.compile(
    r"f_bsnsAncm_downloadAtchFile\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
)
_DOTDATE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")


def _clean(text: str) -> str:
    return " ".join(htmllib.unescape(text).split())


def _iso(text: str | None) -> str | None:
    m = _DOTDATE.search(text or "") or re.search(r"\d{4}-\d{2}-\d{2}", text or "")
    if not m:
        return None
    return "-".join(m.groups()) if m.lastindex else m.group(0)


@dataclass(frozen=True)
class NoticeRow:
    site: str
    id: str
    url: str
    title: str
    posted: str | None  # YYYY-MM-DD
    period: str | None  # "YYYY-MM-DD ~ YYYY-MM-DD"
    program: str | None
    agency: str | None = None
    ministry: str | None = None
    status: str | None = None
    notice_no: str | None = None


@dataclass(frozen=True)
class NoticeDetail:
    title: str
    posted: str | None
    period: str | None
    body: str
    info: dict[str, str] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)  # name, url|None, size


# ── KAIA ──────────────────────────────────────────────────
def parse_kaia_list(html: str, page_url: str) -> tuple[list[NoticeRow], int | None, int]:
    """(행, 전체 건수, 마지막 쪽 번호)."""
    root = parse_html(html)
    rows: list[NoticeRow] = []
    seen: set[str] = set()
    for tr in root.find_all("tr"):
        cells = {td.attrs.get("data-content", ""): td for td in tr.find_all("td")}
        title_td = cells.get("제목")
        if title_td is None:
            continue
        a = title_td.find("a")
        if a is None or "schM=view" not in a.attrs.get("href", ""):
            continue
        url = urljoin(page_url, htmllib.unescape(a.attrs["href"]))
        vals = parse_qs(urlsplit(url).query).get("id")
        if not vals or not vals[0].isdigit() or vals[0] in seen:
            continue
        seen.add(vals[0])
        rows.append(
            NoticeRow(
                site="kaia",
                id=vals[0],
                url=url,
                title=_clean(a.text())[:300],
                posted=_iso(cells["등록일"].text() if "등록일" in cells else None),
                period=_clean(cells["공고기간"].text()) if "공고기간" in cells else None,
                program=_clean(cells["사업명"].text())[:200] if "사업명" in cells else None,
            )
        )
    total = None
    count = root.find(cls="blt_count")
    if count is not None:
        m = re.search(r"([\d,]+)", count.text())
        total = int(m.group(1).replace(",", "")) if m else None
    last = 1
    for a in root.find_all("a"):
        m = _PAGE.search(a.attrs.get("href", ""))
        if m:
            last = max(last, int(m.group(1)))
    return rows, total, last


def parse_kaia_detail(html: str, page_url: str) -> NoticeDetail:
    root = parse_html(html)
    view = root.find(cls="bbs_viewbox") or root
    subject = view.find(cls="subject")
    strong = subject.find("strong") if subject is not None else None
    info: dict[str, str] = {}
    for item in view.find_all(cls="field_item"):
        t, v = item.find(cls="title"), item.find(cls="text")
        if t is not None and v is not None:
            info[_clean(t.text())] = _clean(v.text())
    for tr in view.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th is not None and td is not None:
            info[_clean(th.text())] = _clean(td.text())
    attachments: list[dict[str, Any]] = []
    lst = view.find("ul", cls="attach_list")
    for li in lst.find_all("li") if lst is not None else []:
        em = li.find("em")
        if em is None:
            continue
        name = _clean(em.text())[:200]
        url = None
        for a in li.find_all("a"):
            if "down" in a.classes() and "fileDownload" in a.attrs.get("href", ""):
                url = urljoin(page_url, htmllib.unescape(a.attrs["href"]))
        size_el = li.find("i")
        attachments.append({"name": name, "url": url, "size": _size_bytes(size_el)})
    body_node = view.find(cls="viewcontent")
    return NoticeDetail(
        title=_clean(strong.text())[:300] if strong is not None else "",
        posted=_iso(info.get("등록일")),
        period=info.get("공고기간") or None,
        body=body_node.text() if body_node is not None else "",
        info=info,
        attachments=attachments,
    )


def _size_bytes(node: Node | None) -> int | None:
    m = _SIZE.search(node.text()) if node is not None else None
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    return int(num * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}[m.group(2).upper()])


# ── IRIS ──────────────────────────────────────────────────
def parse_iris_list(data: dict[str, Any], view_url: str) -> tuple[list[NoticeRow], int | None, int]:
    """목록 JSON → (행, 전체 건수, 전체 쪽 수)."""
    rows: list[NoticeRow] = []
    for r in data.get("listBsnsAncmBtinSitu") or []:
        if not isinstance(r, dict):
            continue
        ancm = str(r.get("ancmId") or "")
        if not ancm.isdigit():
            continue
        start, end = _iso(str(r.get("rcveStrDe") or "")), _iso(str(r.get("rcveEndDe") or ""))
        period = f"{start} ~ {end}" if start and end else (start or end)
        rows.append(
            NoticeRow(
                site="iris",
                id=ancm,
                url=f"{view_url}?ancmId={ancm}",
                title=_clean(str(r.get("ancmTl") or ""))[:300],
                posted=_iso(str(r.get("ancmDe") or "")),
                period=period,
                program=_clean(str(r.get("pbofrTpSeNmLst") or ""))[:200] or None,
                agency=_clean(str(r.get("sorgnNm") or ""))[:120] or None,
                ministry=_clean(str(r.get("blngGovdSeNm") or ""))[:120] or None,
                status=_clean(str(r.get("rcveStt") or ""))[:40] or None,
                notice_no=_clean(str(r.get("ancmNo") or ""))[:120] or None,
            )
        )
    page = data.get("paginationInfo") or {}
    total = page.get("totalRecordCount")
    pages = page.get("totalPageCount")
    return (
        rows,
        int(total) if isinstance(total, int) else None,
        int(pages) if isinstance(pages, int) and pages > 0 else 1,
    )


def parse_iris_detail(html: str) -> NoticeDetail:
    root = parse_html(html)
    info: dict[str, str] = {}
    for li in root.find_all("li", cls="write"):
        strong, span = li.find("strong"), li.find("span")
        if strong is None or span is None:
            continue
        key = _clean(strong.text())
        if key not in info:
            info[key] = _clean(span.text())[:500]
    body_node = root.find(cls="se-contents")
    attachments = [
        {
            "name": _clean(name)[:200],
            "url": None,
            "size": int(size) if size.isdigit() else None,
            "doc_id": doc,
            "file_id": fid,
        }
        for doc, fid, name, size in _IRIS_ATCH.findall(html)
    ]
    return NoticeDetail(
        title=info.get("공고명", ""),
        posted=_iso(info.get("공고일자")),
        period=info.get("접수기간") or None,
        body=body_node.text() if body_node is not None else "",
        info={k: v for k, v in info.items() if not k.startswith("사업담당자")},  # 연락처 칸 제외
        attachments=attachments,
    )
