"""info.korail.com 페이지 해석 — 순수 함수 (표준 라이브러리 html.parser 만).

페이지 텍스트는 비신뢰 데이터다(보안 A). 구조만 뽑고, 저장 전 개인정보 제거는 `_pii` 가 한다.
게시판 구조(2026-10-27 확인):
- 목록 `selectBbsNttList.do?bbsNo=&key=&pageIndex=` — "총게시물 : N 건",
  행마다 `selectBbsNttView.do?…nttNo=`,
  파일 아이콘 `p-icon__<ext>`, 작성일 YYYY-MM-DD.
- 상세 `selectBbsNttView.do` — `.detail_title`, `.detail_info .date`, `.detail_content`,
  `.attach_file`
  (`.file_name` + `downloadBbsFile.do?atchmnflNo=`).
- 콘텐츠 `contents.do?key=` — `#contents`, 파일 `downloadContentsFile.do?key=&fileNo=`,
  하단 `.kogl_open`
  이용조건.
- 사전정보공표 `selectInfoRelWebList.do` / `selectInfoRelWebDetail.do` — 첨부
  `downloadInfoRelFile.do?infoRelAtchNo=`.
"""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_BLOCK = frozenset(
    {
        "p",
        "div",
        "li",
        "tr",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "ul",
        "ol",
        "section",
        "article",
    }
)
_DATE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_TOTAL = re.compile(r"총게시물\s*:\s*([\d,]+)\s*건")
_PAGES = re.compile(r"페이지\s*:\s*\d+\s*/\s*([\d,]+)")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_TEXT_CHARS = 2_000_000
MAX_ATTACHMENTS = 100
MAX_IMAGES = 200


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []
        self.parent = parent

    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def iter(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def find(self, tag: str | None = None, *, id: str | None = None, cls: str | None = None):
        for n in self.iter():
            if tag and n.tag != tag:
                continue
            if id is not None and n.attrs.get("id") != id:
                continue
            if cls is not None and cls not in n.classes():
                continue
            return n
        return None

    def find_all(self, tag: str | None = None, *, cls: str | None = None) -> list[Node]:
        return [
            n
            for n in self.iter()
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes())
        ]

    def text(self) -> str:
        """태그를 떼고 블록 경계에 줄바꿈을 넣은 텍스트. script·style 은 뺀다."""
        parts: list[str] = []
        self._collect(parts)
        text = htmllib.unescape("".join(parts))
        text = _CONTROL.sub(" ", text)
        lines = [" ".join(line.split()) for line in text.split("\n")]
        out: list[str] = []
        for line in lines:
            if line or (out and out[-1]):
                out.append(line)
        return "\n".join(out).strip()[:MAX_TEXT_CHARS]

    def _collect(self, parts: list[str]) -> None:
        if self.tag in ("script", "style", "noscript"):
            return
        if self.tag in _BLOCK:
            parts.append("\n")
        for c in self.children:
            if isinstance(c, str):
                parts.append(c)
            else:
                c._collect(parts)
        if self.tag in _BLOCK:
            parts.append("\n")


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(text: str) -> Node:
    b = _Builder()
    b.feed(text)
    b.close()
    return b.root


# ── 결과 구조 ─────────────────────────────────────────────
@dataclass(frozen=True)
class ListRow:
    # "bbs:<bbsNo>:<nttNo>" / "bbs:<bbsNo>:file:<atchmnflNo>"(갤러리) / "preinfo:<rel>:<detail>"
    native_id: str
    url: str
    title: str
    posted: str | None  # YYYY-MM-DD
    file_kinds: tuple[str, ...] = ()  # 목록 아이콘 (hwp·pdf·folder …)
    direct_file: str | None = None  # 갤러리형 게시판: 상세 페이지 없이 바로 받는 파일 URL
    cover: str | None = None  # 갤러리형: 표지 이미지 URL


@dataclass(frozen=True)
class ListPage:
    rows: list[ListRow]
    total: int | None
    pages: int | None


@dataclass(frozen=True)
class Attachment:
    name: str
    url: str


@dataclass(frozen=True)
class Image:
    src: str
    alt: str
    caption: str  # title 속성 또는 figcaption
    context: str  # 둘러싼 단락 텍스트 (200자)


@dataclass(frozen=True)
class PageItem:
    title: str
    posted: str | None
    text: str
    attachments: list[Attachment] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    terms: str | None = None  # 공공누리 유형 등 이용조건 문구
    department: str | None = None


def _norm_date(text: str | None) -> str | None:
    m = _DATE.search(text or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _query(url: str, key: str) -> str | None:
    vals = parse_qs(urlsplit(url).query).get(key)
    return vals[0] if vals else None


def _clean_title(text: str) -> str:
    return " ".join(_CONTROL.sub(" ", htmllib.unescape(text)).split())[:300]


def _container(root: Node) -> Node:
    return root.find(id="container") or root.find("body") or root


def head_title(root: Node) -> tuple[str, str]:
    """<title> "A>B>C - 한국철도공사" → ("A > B > C", "C"). 없으면 ("", "")."""
    t = root.find("title")
    if t is None:
        return "", ""
    raw = _clean_title(t.text()).split(" - ")[0]
    parts = [p.strip() for p in raw.split(">") if p.strip()]
    return " > ".join(parts), (parts[-1] if parts else "")


def _cell_text(node: Node) -> str:
    return " / ".join(line for line in node.text().split("\n") if line.strip())


def parse_tables(html: str) -> list[list[list[str]]]:
    """본문의 표를 rowspan·colspan 을 펼친 격자(행 → 셀 텍스트)로. 셀 안 줄바꿈은 " / "."""
    root = parse_html(html)
    out: list[list[list[str]]] = []
    for table in _container(root).find_all("table"):
        grid: list[list[str | None]] = []
        pending: dict[tuple[int, int], str] = {}  # (row, col) → rowspan 으로 내려온 값
        rows = [tr for tr in table.find_all("tr")]
        for r, tr in enumerate(rows):
            cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ("td", "th")]
            row: list[str | None] = []
            c = 0
            ci = 0
            while ci < len(cells) or (r, c) in pending:
                if (r, c) in pending:
                    row.append(pending.pop((r, c)))
                    c += 1
                    continue
                cell = cells[ci]
                ci += 1
                text = _cell_text(cell)
                try:
                    rs = max(1, int(cell.attrs.get("rowspan", "1") or 1))
                    cs = max(1, int(cell.attrs.get("colspan", "1") or 1))
                except ValueError:
                    rs, cs = 1, 1
                for k in range(cs):
                    row.append(text)
                    for dr in range(1, rs):
                        pending[(r + dr, c + k)] = text
                c += cs
            grid.append(row)
        out.append([[cell or "" for cell in row] for row in grid if any(row)])
    return out


# ── 게시판 목록 ─────────────────────────────────────────────
def parse_board_list(html: str, page_url: str) -> ListPage:
    root = parse_html(html)
    cont = _container(root)
    flat = cont.text()
    total = _TOTAL.search(flat)
    pages = _PAGES.search(flat)
    rows: list[ListRow] = []
    seen: set[str] = set()
    for tr in cont.find_all("tr"):
        link = next(
            (a for a in tr.find_all("a") if "selectBbsNttView.do" in a.attrs.get("href", "")),
            None,
        )
        if link is None:
            continue
        href = urljoin(page_url, htmllib.unescape(link.attrs["href"]))
        bbs, ntt = _query(href, "bbsNo"), _query(href, "nttNo")
        if not (bbs and ntt) or not ntt.isdigit():
            continue
        key = f"bbs:{bbs}:{ntt}"
        if key in seen:
            continue
        seen.add(key)
        title = re.sub(r"\s*새글$", "", _clean_title(link.text()))
        kinds = tuple(
            sorted(
                {
                    c.removeprefix("p-icon__")
                    for sp in tr.find_all("span")
                    for c in sp.classes()
                    if c.startswith("p-icon__") and c != "p-icon__new"
                }
            )
        )
        rows.append(
            ListRow(
                native_id=key, url=href, title=title, posted=_norm_date(tr.text()), file_kinds=kinds
            )
        )
    if not rows:
        rows = _gallery_rows(cont, page_url)
    return ListPage(
        rows=rows,
        total=int(total.group(1).replace(",", "")) if total else None,
        pages=int(pages.group(1).replace(",", "")) if pages else None,
    )


_PDF_BTN = re.compile(r"pdfDownload\('?(\d+)'?\)")


def _gallery_rows(cont: Node, page_url: str) -> list[ListRow]:
    """갤러리형(지속가능경영보고서 등): 상세 없이 `pdfDownload('<번호>')` 버튼 + 표지 이미지."""
    bbs = _query(page_url, "bbsNo") or "0"
    rows: list[ListRow] = []
    seen: set[str] = set()
    for li in cont.find_all("li", cls="p-media"):
        btn = next(
            (b for b in li.find_all("button") if _PDF_BTN.search(b.attrs.get("onclick") or "")),
            None,
        )
        if btn is None:
            continue
        no = _PDF_BTN.search(btn.attrs["onclick"]).group(1)
        key = f"bbs:{bbs}:file:{no}"
        if key in seen:
            continue
        seen.add(key)
        head = li.find(cls="p-media__heading-text") or li.find(cls="p-media__heading")
        title = _clean_title(head.text()) if head is not None else _clean_title(li.text())[:120]
        img = li.find("img")
        cover = (
            urljoin(page_url, htmllib.unescape(img.attrs["src"]))
            if img is not None and img.attrs.get("src")
            else None
        )
        url = urljoin(page_url, f"./downloadBbsFile.do?atchmnflNo={no}")
        rows.append(
            ListRow(
                native_id=key,
                url=url,
                title=title,
                posted=_norm_date(li.text()),
                file_kinds=("pdf",),
                direct_file=url,
                cover=cover,
            )
        )
    return rows


# ── 게시글 상세 ─────────────────────────────────────────────
def _terms(cont: Node) -> str | None:
    box = cont.find(cls="kogl_open")
    if box is None:
        return None
    text = " ".join(box.text().split())
    m = re.search(r"공공누리\s*제\s*(\d)\s*유형[^\"”]*", text)
    return (m.group(0) if m else text)[:200] or None


def _images(node: Node, page_url: str) -> list[Image]:
    out: list[Image] = []
    for img in node.find_all("img"):
        src = (img.attrs.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        alt = _clean_title(img.attrs.get("alt") or "")
        caption = _clean_title(img.attrs.get("title") or "")
        if not caption:
            fig = img.parent
            while fig is not None and fig.tag != "figure":
                fig = fig.parent
            cap = fig.find("figcaption") if fig is not None else None
            caption = _clean_title(cap.text()) if cap is not None else ""
        ctx_node = img.parent
        while ctx_node is not None and ctx_node.tag not in ("p", "div", "td", "li", "figure"):
            ctx_node = ctx_node.parent
        context = " ".join((ctx_node.text() if ctx_node is not None else "").split())[:200]
        out.append(
            Image(
                src=urljoin(page_url, htmllib.unescape(src)),
                alt=alt,
                caption=caption,
                context=context,
            )
        )
        if len(out) >= MAX_IMAGES:
            break
    return out


def _attachments(node: Node, page_url: str, marker: str) -> list[Attachment]:
    out: list[Attachment] = []
    seen: set[str] = set()
    for a in node.find_all("a"):
        href = a.attrs.get("href") or ""
        if marker not in href:
            continue
        url = urljoin(page_url, htmllib.unescape(href))
        if url in seen:
            continue
        seen.add(url)
        name = ""
        box = a.parent
        if box is not None:
            fn = box.find("span", cls="file_name")
            if fn is not None:
                name = _clean_title(fn.text())
        if not name:
            name = _clean_title(a.text())
        if name in ("다운로드", "미리보기", ""):
            name = _clean_title(a.attrs.get("title") or "") or url.rsplit("=", 1)[-1]
        out.append(Attachment(name=name, url=url))
        if len(out) >= MAX_ATTACHMENTS:
            break
    return out


def parse_board_view(html: str, page_url: str) -> PageItem:
    root = parse_html(html)
    cont = _container(root)
    inner = cont.find(cls="bbs_detail_inner") or cont
    title_node = inner.find(cls="detail_title")
    title = _clean_title(title_node.text()) if title_node is not None else ""
    date_node = inner.find(cls="date")
    posted = _norm_date(date_node.text()) if date_node is not None else None
    body = inner.find(cls="detail_content") or inner
    return PageItem(
        title=title,
        posted=posted,
        text=body.text(),
        attachments=_attachments(inner, page_url, "downloadBbsFile.do"),
        images=_images(body, page_url),
        terms=_terms(cont),
    )


# ── 콘텐츠 페이지 ───────────────────────────────────────────
def parse_contents(html: str, page_url: str) -> PageItem:
    root = parse_html(html)
    cont = _container(root)
    body = cont.find(id="contents") or cont
    _path, title = head_title(root)
    return PageItem(
        title=title,
        posted=None,
        text=body.text(),
        attachments=_attachments(body, page_url, "downloadContentsFile.do"),
        images=_images(body, page_url),
        terms=_terms(cont),
    )


# ── 사전정보공표 ────────────────────────────────────────────
def parse_preinfo_list(html: str, page_url: str) -> ListPage:
    root = parse_html(html)
    cont = _container(root)
    flat = cont.text()
    total = _TOTAL.search(flat)
    pages = _PAGES.search(flat)
    rows: list[ListRow] = []
    seen: set[str] = set()
    for a in cont.find_all("a"):
        href = a.attrs.get("href") or ""
        if "selectInfoRelWebDetail.do" not in href:
            continue
        url = urljoin(page_url, htmllib.unescape(href))
        rel, det = _query(url, "infoRelNo"), _query(url, "infoRelDetailNo")
        if not (rel and det):
            continue
        key = f"preinfo:{rel}:{det}"
        if key in seen:
            continue
        seen.add(key)
        block = a.parent
        while block is not None and not (block.tag == "li" and "publicity_item" in block.classes()):
            block = block.parent
        head = block.find(cls="item_title") if block is not None else None
        text = block.text() if block is not None else a.text()
        title = _clean_title(head.text()) if head is not None else _clean_title(a.text())
        rows.append(ListRow(native_id=key, url=url, title=title, posted=_norm_date(text)))
    return ListPage(
        rows=rows,
        total=int(total.group(1).replace(",", "")) if total else None,
        pages=int(pages.group(1).replace(",", "")) if pages else None,
    )


def parse_preinfo_detail(html: str, page_url: str) -> PageItem:
    root = parse_html(html)
    cont = _container(root)
    flat = cont.text()
    m = re.search(r"자료게시 상세\s*\n?\s*(.+)", flat)
    title = _clean_title(m.group(1)) if m else ""
    posted = (
        _norm_date(re.search(r"등록일\s*([\d.-]+)", flat).group(1)) if "등록일" in flat else None
    )
    dept = re.search(r"담당부서\s*([^\s\n]+)", flat)
    body_node = cont.find(cls="detail_content") or cont.find(cls="bbs_detail_inner") or cont
    return PageItem(
        title=title,
        posted=posted,
        text=body_node.text(),
        attachments=_attachments(cont, page_url, "downloadInfoRelFile.do"),
        images=_images(body_node, page_url),
        terms=_terms(cont),
        department=dept.group(1) if dept else None,
    )


def filename_from_disposition(value: str | None) -> str | None:
    """Content-Disposition 의 filename (URL 인코딩·따옴표 해제). 경로 구분자는 뺀다."""
    if not value:
        return None
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", value, flags=re.I)
    if not m:
        return None
    from urllib.parse import unquote

    name = unquote(m.group(1).strip())
    name = name.replace("/", "_").replace("\\", "_")
    return _clean_title(name) or None
