"""알리오 공개 요약 — 원문 비공개 보고서의 상세 페이지 요약을 적재한다.

투입 위치: `data/inbox/alio_summary/<catalog_id>.txt`.

코레일 연구보고서 상당수는 원문이 비공개(정보공개법 제9조①7호)라 파일을 받을 수 없고,
상세 페이지에 구조화된 요약(연구목적·연구내용·기대효과·활용계획·연구기간·소요예산 …)만 공개된다.
사용자가 그 페이지 텍스트를 복사해 `<catalog_id>.txt` 로 저장하면 이 경로로 적재한다.

- 파일 처리는 원문 filedrop 과 같다: filecheck(txt, 크기·NUL) → 샌드박스(`txt` 파서, 디코드·줄 분리)
  → 재검증 → 실패하면 `_quarantine/`, upsert 뒤 `_done/`.
- 라벨 해석(`parse_labeled`)과 정규화(`normalize_summary`)는 본체의 순수 함수다.
- Document.text_basis = "summary". 같은 catalog_id 의 원문이 나중에 들어오면 원문이 대체한다
  (반대 방향은 ingest 가 막는다).
"""

from __future__ import annotations

import calendar
import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rra.adapters.sources._orgs import org_tags
from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._inbox import Inbox, error_name
from rra.adapters.sources.alio._models import TextLines
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.application.ports import CatalogPort
from rra.domain.models import CatalogEntry, Document

logger = logging.getLogger("rra.sources.alio_summary")

FILE_FORMATS = frozenset({"txt"})
DEFAULT_MAX_BYTES = 256 * 1024

# 필드 → 후보 라벨. 실제 복사본을 보고 config/sources.yaml 의 alio.summary.labels 로 확정한다.
# "목적"·"예산"처럼 짧은 단어는 본문 줄머리와 헷갈리므로 기본값에 넣지 않는다.
# `_` 로 시작하는 필드는 묶음 머리글(알리오 "* 내용", "1. 과제개요")이다: 값을 저장하지 않고,
# 앞 필드에 뒤 줄이 이어 붙지 않게 끊기만 한다.
DEFAULT_LABELS: dict[str, list[str]] = {
    "_group": ["내용", "과제개요"],
    "title": ["제목", "보고서명", "연구보고서명", "연구과제명", "과제명"],
    "institution": ["기관명", "공공기관명"],
    "published": ["발간일", "발간일자", "발행일"],
    "authors": ["저자", "연구진"],
    "project_type": ["과제유형", "연구유형"],
    "pi": ["연구책임자", "책임연구원"],
    "department": ["부서", "담당부서", "주관부서", "수행부서"],
    "period": ["연구기간", "과제기간"],
    "budget": ["소요예산", "연구비"],
    "purpose": ["연구목적"],
    "content": ["연구내용", "주요내용", "주요 연구내용"],
    "effect": ["기대효과"],
    "usage": ["활용계획", "활용방안"],
    "disclosure_status": ["원문공개 여부", "원문공개여부", "원문공개", "공개여부"],
    "disclosure_reason": ["비공개사유"],
    "open_date": ["공개예정일"],
}
# 본문에 절(節)로 넣는 필드와 절 제목
BODY_SECTIONS: tuple[tuple[str, str], ...] = (
    ("purpose", "연구목적"),
    ("content", "연구내용"),
    ("effect", "기대효과"),
    ("usage", "활용계획"),
)
MULTILINE_FIELDS = frozenset(f for f, _ in BODY_SECTIONS)
MAX_FIELD_CHARS = {"title": 300, "authors": 500, "pi": 200, "department": 200}
MAX_SCALAR_CHARS = 500
MAX_SECTION_CHARS = 20_000
MAX_AUTHORS = 30

_BULLET = r"[\s□■○●◦•▶·\-\*]*"
_NUMBER = r"(?:\d{1,2}\s*[.)]\s*)?"  # 번호 절 제목 "2. 연구목적"
_SEP = r"(?:\s*[:：]\s*|\t+\s*|\s{2,}|\s*$)"
_PAIR_SEP = r"\s*[·/]\s*"
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_DATE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})(?:\s*[-./월]\s*(\d{1,2}))?")
_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만|천)?")
_UNIT = {"억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3, None: 1}
_PAREN = re.compile(r"\(([^()]{1,100})\)")
_UNIT_SUFFIX = re.compile(r"(처|실|단|부|팀|과|원|센터|본부|연구소|사업소)$")
_JOB_TITLE = re.compile(
    r"(책임|선임|수석|주임|전임)?연구원|박사|(처|실|단|부|팀|과)장|부장|차장|과장"
)
_TILDES = str.maketrans({"∼": "~", "～": "~", "〜": "~", "∽": "~"})  # U+223C 등 → ~

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]


class MissingRequiredField(ValueError):
    """제목 또는 (연구목적·연구내용) 이 없다. 클래스명이 격리 사유로 로그에 남는다."""


# ── 라벨 해석 (순수) ─────────────────────────────────────
def _label_pattern(label: str) -> str:
    # 라벨 안 공백 유무를 가리지 않는다 ("원문공개 여부" == "원문공개여부")
    return r"\s*".join(re.escape(ch) for ch in label.replace(" ", ""))


def _compile(labels: Mapping[str, Sequence[str]]) -> tuple[re.Pattern[str], dict[str, str]]:
    """라벨 한 개 또는 `라벨A·라벨B` 쌍으로 시작하는 줄을 잡는 정규식."""
    by_key: dict[str, str] = {}
    for field, names in labels.items():
        for name in names:
            by_key.setdefault(name.replace(" ", ""), field)
    alts = "|".join(_label_pattern(n) for n in sorted(by_key, key=len, reverse=True))
    one = rf"(?:{alts})"
    rx = re.compile(rf"^{_BULLET}{_NUMBER}(?P<a>{one})(?:{_PAIR_SEP}(?P<b>{one}))?{_SEP}(?P<v>.*)$")
    return rx, by_key


def _key(label: str) -> str:
    return "".join(label.split())


def parse_labeled(
    lines: Sequence[str], labels: Mapping[str, Sequence[str]] | None = None
) -> dict[str, str]:
    """`라벨: 값`·`라벨<TAB>값`·라벨만 있는 줄 + 다음 줄들 → {필드: 값}.

    - 다음 라벨이 나올 때까지의 줄은 현재 필드에 이어 붙인다 (본문 절은 줄바꿈 유지).
    - 줄머리의 글머리표(`*`, `-`, `□` …)와 번호(`2.`, `3)`)는 건너뛴다.
    - `과제유형 / 연구책임자 : 수시연구과제 / 경영연구처 홍길동` → 라벨이 둘이면 값도 둘로 나눈다.
    - 첫 라벨 전의 줄(메뉴·머리글)은 버린다. 같은 필드가 다시 나오면 처음 값을 쓴다.
    - `_` 로 시작하는 필드(묶음 머리글)는 현재 필드를 끊기만 하고 저장하지 않는다.
    """
    rx, by_key = _compile(labels or DEFAULT_LABELS)
    parts: dict[str, list[str]] = {}
    current: str | None = None

    def start(field: str, value: str) -> str | None:
        if field.startswith("_") or field in parts:
            return None  # 두 번째 등장은 무시 (이어 붙이지도 않는다)
        parts[field] = [value] if value else []
        return field

    for raw in lines:
        line = _CONTROL.sub(" ", raw).rstrip()
        m = rx.match(line)
        if m is None:
            if current is not None and line.strip():
                parts[current].append(line.strip())
            continue
        value = m["v"].strip()
        first = by_key[_key(m["a"])]
        if m["b"]:
            left, right = _split_pair(value)
            start(first, left)
            current = start(by_key[_key(m["b"])], right)
        else:
            current = start(first, value)
    return {
        field: ("\n" if field in MULTILINE_FIELDS else " ").join(v).strip()
        for field, v in parts.items()
        if "".join(v).strip()
    }


def _split_pair(value: str) -> tuple[str, str]:
    """쌍 라벨의 값 `수시연구과제 / 경영연구처 홍길동` → 둘로. 구분자가 없으면 앞 필드에 전부.

    알리오는 ` / `(앞뒤 공백)로 짝짓는다. 값 안의 `/`·`·`(법규·제도 등)보다 먼저 찾는다.
    """
    if " / " in value:
        left, _, right = value.partition(" / ")
        return left.strip(), right.strip()
    m = re.search(r"\s*[/·]\s*", value)
    if not m:
        return value, ""
    return value[: m.start()].strip(), value[m.end() :].strip()


# ── 값 해석 (순수) ───────────────────────────────────────
def _clean(value: Any, limit: int = MAX_SCALAR_CHARS) -> str:
    return " ".join(_CONTROL.sub(" ", str(value or "")).split())[:limit]


def parse_date(value: str, *, end_of_month: bool = False) -> date | None:
    m = _DATE.search(value or "")
    return _date_from(m, end_of_month=end_of_month) if m else None


def _date_from(m: re.Match[str], *, end_of_month: bool) -> date | None:
    y, mo = int(m.group(1)), int(m.group(2))
    try:
        if m.group(3):
            return date(y, mo, int(m.group(3)))
        return date(y, mo, calendar.monthrange(y, mo)[1] if end_of_month else 1)
    except ValueError:
        return None


def parse_period(value: str) -> tuple[date, date] | None:
    """`2021.03.01 ~ 2021.12.31`·`2021.03~2021.12` → (시작, 종료). 일이 없으면 종료는 월말."""
    found = list(_DATE.finditer(value or ""))
    if len(found) < 2:
        return None
    start = _date_from(found[0], end_of_month=False)
    end = _date_from(found[1], end_of_month=True)
    return (start, end) if start and end and start <= end else None


def parse_budget_krw(value: str) -> int | None:
    """`120,000천원`·`1.2억원`·`12억 3,000만원`·`150백만원` → 원 단위 정수."""
    total = 0.0
    found = False
    main = _PAREN.sub(" ", value or "")  # "(국비 100,000천원)" 같은 내역은 합산하지 않는다
    for m in _MONEY.finditer(main):
        digits = m.group(1).replace(",", "")
        if not digits.strip("."):
            continue
        total += float(digits) * _UNIT[m.group(2)]
        found = True
    return round(total) if found and total > 0 else None


def split_names(value: str) -> list[str]:
    names = (_clean(n, 50) for n in re.split(r"[,，;/·]", value or ""))
    return list(dict.fromkeys(n for n in names if n))[:MAX_AUTHORS]


def _department(fields: Mapping[str, str]) -> str | None:
    """부서 라벨 → 연구책임자 괄호 안 소속("홍길동(경영연구처)") → 이름 앞부분("경영연구처 홍길동").

    마지막 형태는 이름 앞 토큰들이 조직 단위 접미사(처·실·단 …)로 끝날 때만 부서로 본다
    ("홍길동 외 2인" 같은 값을 부서로 오인하지 않게).
    """
    limit = MAX_FIELD_CHARS["department"]
    if dept := _clean(fields.get("department"), limit):
        return dept
    pi = _clean(fields.get("pi"))
    if m := _PAREN.search(pi):
        return _clean(m.group(1), limit)
    tokens = pi.split()[:-1]  # 마지막 토큰 = 이름
    while tokens and _JOB_TITLE.fullmatch(tokens[-1]):  # "경영연구처 책임연구원 홍길동"
        tokens.pop()
    head = " ".join(tokens)
    return head[:limit] if head and _UNIT_SUFFIX.search(head) else None


def missing_required(fields: Mapping[str, str], *, has_catalog_title: bool) -> bool:
    has_title = has_catalog_title or bool(_clean(fields.get("title")))
    return not has_title or not (fields.get("purpose") or fields.get("content"))


def summary_doc_id(entry: CatalogEntry | None, fields: Mapping[str, str], org: str) -> str:
    if entry:
        return f"alio:{entry.catalog_id}"  # 원문 filedrop 과 같은 id → 원문이 들어오면 대체
    basis = "\x1f".join(
        (org, _clean(fields.get("title")), _clean(fields.get("published")))
    ).encode()
    return "alio:sum-" + hashlib.sha256(basis).hexdigest()[:16]


def _orgs(
    entry: CatalogEntry | None,
    fields: Mapping[str, str],
    department: str | None,
    institutions: Sequence[Mapping[str, Any]],
    default_org: str | None,
) -> tuple[list[str], str | None]:
    if entry is not None:
        return [entry.institution_tag], "catalog"
    names = [fields.get("institution", ""), department or "", fields.get("pi", "")]
    if found := org_tags(names, institutions):
        return found, "text"
    if default_org:
        return [default_org], "default"
    return [], None


def normalize_summary(
    raw: Mapping[str, Any],
    *,
    labels: Mapping[str, Sequence[str]] | None = None,
    institutions: Sequence[Mapping[str, Any]] = (),
    default_org: str | None = None,
) -> Document:
    """순수 함수. raw = {sha256, lines, catalog?}.

    기관 태그(`raw.org_source` 에 출처를 남긴다):
    - catalog: 파일명 stem 이 catalog_id 와 매칭 → 카탈로그 행의 기관 (기관코드 우선, 없으면 기관명)
    - text:    매칭이 없으면 기관명·부서·연구책임자 텍스트에서 찾은 태그
    - default: 그것도 없으면 default_org. 추정이므로 ingest 경고(assumed_org)로 알린다
    카탈로그 매칭이 있으면 default_org 는 쓰지 않는다 (KRRI·공단 요약이 같은 inbox 에 들어온다).
    """
    lines = TextLines.model_validate({"lines": raw["lines"]}).lines
    entry = CatalogEntry.model_validate(raw["catalog"]) if raw.get("catalog") else None
    f = parse_labeled(lines, labels)
    if missing_required(f, has_catalog_title=bool(entry)):
        raise MissingRequiredField("required")

    title = _clean(entry.title if entry else f.get("title"), MAX_FIELD_CHARS["title"])
    department = _department(f)
    orgs, org_source = _orgs(entry, f, department, institutions, default_org)
    period_text = _clean(f.get("period")).translate(_TILDES)
    period = parse_period(period_text)
    budget_text = _clean(f.get("budget"))
    project_type = _clean(f.get("project_type"))

    sections = [
        (heading, f[field][:MAX_SECTION_CHARS]) for field, heading in BODY_SECTIONS if f.get(field)
    ]
    preface = " · ".join(
        p
        for p in (
            project_type,
            f"연구기간 {period_text}" if period_text else "",
            f"소요예산 {budget_text}" if budget_text else "",
            f"부서 {department}" if department else "",
        )
        if p
    )
    body = "\n\n".join(
        [f"[공개 요약] {preface}".rstrip(), *(f"■ {h}\n{text}" for h, text in sections)]
    )
    open_date = parse_date(f.get("open_date", ""))
    return Document(
        doc_id=summary_doc_id(entry, f, orgs[0] if orgs else ""),
        source="alio",
        doc_type="internal_report",
        title=title,
        body=body,
        pub_date=(entry.published if entry and entry.published else None)
        or parse_date(f.get("published", "")),
        orgs=orgs,
        authors=split_names(f.get("authors", "")),
        lang="ko",
        url=entry.url if entry else None,
        department=department,
        project_period=period,
        toc=[f"■ {h}" for h, _ in sections],
        text_basis="summary",
        raw={
            "sha256": str(raw["sha256"]),
            "fmt": "txt",
            "catalog_id": entry.catalog_id if entry else None,
            "catalog_matched": entry is not None,
            "org_source": org_source,
            "project_type": project_type or None,
            "pi": _clean(f.get("pi"), MAX_FIELD_CHARS["pi"]) or None,
            "budget_krw": parse_budget_krw(budget_text),
            "budget_text": budget_text or None,
            "disclosure": {
                "status": _clean(f.get("disclosure_status"), 50) or None,
                "reason": _clean(f.get("disclosure_reason")) or None,
                "open_date": open_date.isoformat() if open_date else None,
            },
        },
    )


# ── 소스 ─────────────────────────────────────────────────
class AlioSummarySource:
    """SourcePort + AcknowledgingSource. IngestReport 키는 alio_summary, Document.source 는 alio."""

    source = "alio_summary"

    def __init__(
        self,
        inbox: Path,
        *,
        limits: SandboxLimits,
        institutions: Sequence[Mapping[str, Any]] = (),
        catalog: CatalogPort | None = None,
        labels: Mapping[str, Sequence[str]] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        default_org: str | None = None,
        runner: Runner = run_parser,
    ):
        self.inbox = Path(inbox)
        self._box = Inbox(self.inbox, formats=FILE_FORMATS, logger=logger, event="alio_summary")
        self.limits = limits
        self.institutions = list(institutions)
        self.catalog = catalog
        self.labels = {**DEFAULT_LABELS, **(labels or {})}
        self.max_bytes = max_bytes
        self.default_org = default_org
        self._runner = runner

    def __repr__(self) -> str:
        return "AlioSummarySource()"

    async def aclose(self) -> None:
        return None

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """query 는 쓰지 않는다 (inbox 전체가 대상). 파일은 순차 처리 (동시성 1)."""
        files = self._box.pending() if limit > 0 else []
        if not files:
            return []
        index = await self._catalog_index()
        out: list[dict[str, Any]] = []
        for path in files:
            if len(out) >= limit:
                break
            if raw := await self._process(path, index):
                out.append(raw)
        return out

    async def _catalog_index(self) -> dict[str, CatalogEntry]:
        if self.catalog is None:
            return {}
        try:
            return {e.catalog_id: e for e in await self.catalog.entries()}
        except Exception as exc:  # 카탈로그가 깨져도 적재는 계속한다
            logger.warning("alio_summary.catalog_failed error=%s", error_name(exc))
            return {}

    async def _process(self, path: Path, index: dict[str, CatalogEntry]) -> dict[str, Any] | None:
        try:
            vf = open_validated(path, max_bytes=self.max_bytes, allowed=FILE_FORMATS)
        except FileRejected as exc:
            self._box.quarantine(path, exc, sha256=None)
            return None
        entry = index.get(path.stem)
        with vf:
            try:
                result = TextLines.model_validate(await self._runner(vf.fd, vf.fmt, self.limits))
                fields = parse_labeled(result.lines, self.labels)
                if missing_required(fields, has_catalog_title=entry is not None):
                    raise MissingRequiredField("required")
            except (SandboxError, ValidationError, MissingRequiredField) as exc:
                self._box.quarantine(path, exc, sha256=vf.sha256)
                return None
        return {
            "sha256": vf.sha256,
            "fmt": vf.fmt,
            "catalog": entry.model_dump(mode="json") if entry else None,
            "lines": result.lines,
            "_file": str(path),
        }

    def acknowledge(self, raws: list[dict[str, Any]]) -> None:
        self._box.acknowledge(raws)

    def ingest_warnings(self, doc: Document) -> list[tuple[str, str]]:
        """WarningSource. 카탈로그 매칭 없이 default_org 로 태깅한 문서는 확인이 필요하다."""
        if doc.raw.get("org_source") == "default":
            return [("assumed_org", ",".join(doc.orgs))]
        return []

    def normalize(self, raw: dict[str, Any]) -> Document:
        return normalize_summary(
            raw,
            labels=self.labels,
            institutions=self.institutions,
            default_org=self.default_org,
        )
