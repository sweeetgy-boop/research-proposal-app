"""molit 정책정보 게시판 해석 (순수).

목록 `td.bd_title a[href*=dtl.jsp]`·`td.bd_date`·`td.bd_category`,
상세 `.bd_view h4`, `ul.bd_view_ul_info`(담당부서·등록일·분류·첨부파일), 본문 `.bd_view_cont`,
첨부 `/portal/common/download/DownloadMltm2.jsp?FilePath=…&FileName=…`."""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urljoin, urlsplit

from rra.adapters.sources.korail_web._html import Node, parse_html

_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_TOTAL = re.compile(r"전체\s*([\d,]+)\s*건")


@dataclass(frozen=True)
class MolitRow:
    id: str
    url: str
    title: str
    posted: str | None
    category: str


@dataclass(frozen=True)
class MolitDetail:
    title: str
    posted: str | None
    department: str | None
    category: str | None
    body: str
    attachments: list[tuple[str, str]] = field(default_factory=list)  # (name, url)


def _id(url: str) -> str | None:
    vals = parse_qs(urlsplit(url).query).get("id")
    return vals[0] if vals and vals[0].isdigit() else None


def _clean(text: str) -> str:
    return " ".join(htmllib.unescape(text).split())


def parse_list(html: str, page_url: str) -> tuple[list[MolitRow], int | None, int]:
    """(행, 전체 건수, 마지막 쪽 번호)."""
    root = parse_html(html)
    rows: list[MolitRow] = []
    seen: set[str] = set()
    for tr in root.find_all("tr"):
        title_td = tr.find("td", cls="bd_title")
        if title_td is None:
            continue
        a = title_td.find("a")
        if a is None or "dtl.jsp" not in a.attrs.get("href", ""):
            continue
        url = urljoin(page_url, htmllib.unescape(a.attrs["href"]))
        rid = _id(url)
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        date_td = tr.find("td", cls="bd_date")
        cat_td = tr.find("td", cls="bd_category")
        m = _DATE.search(date_td.text()) if date_td is not None else None
        rows.append(
            MolitRow(
                id=rid,
                url=url,
                title=_clean(a.text())[:300],
                posted=m.group(0) if m else None,
                category=_clean(cat_td.text()) if cat_td is not None else "",
            )
        )
    total = _TOTAL.search(root.text())
    last = 1
    for a in root.find_all("a"):
        href = a.attrs.get("href", "")
        m = re.search(r"lcmspage=(\d+)", href)
        if m and "lst.jsp" in href:
            last = max(last, int(m.group(1)))
    return rows, (int(total.group(1).replace(",", "")) if total else None), last


def parse_detail(html: str, page_url: str) -> MolitDetail:
    root = parse_html(html)
    view = root.find(cls="bd_view") or root
    h4 = view.find("h4")
    info: dict[str, str] = {}
    attachments: list[tuple[str, str]] = []
    ul = view.find("ul", cls="bd_view_ul_info")
    if ul is not None:
        for li in ul.find_all("li"):
            strong = li.find("strong")
            if strong is None:
                continue
            key = _clean(strong.text())
            if key == "첨부파일":
                for a in li.find_all("a"):
                    href = a.attrs.get("href", "")
                    if "DownloadMltm2.jsp" not in href and "download" not in href.lower():
                        continue
                    url = urljoin(page_url, htmllib.unescape(href))
                    name = parse_qs(urlsplit(url).query).get("FileName", [_clean(a.text())])[0]
                    attachments.append((_clean(name)[:200], url))
                continue
            span = li.find("span")
            info[key] = _clean(span.text()) if span is not None else ""
    body_node: Node | None = view.find(cls="bd_view_cont")
    m = _DATE.search(info.get("등록일", ""))
    return MolitDetail(
        title=_clean(h4.text())[:300] if h4 is not None else "",
        posted=m.group(0) if m else None,
        department=info.get("담당부서") or None,
        category=info.get("분류") or None,
        body=body_node.text() if body_node is not None else "",
        attachments=attachments,
    )
