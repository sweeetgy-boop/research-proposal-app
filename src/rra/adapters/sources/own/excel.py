"""사내 과제 현황 엑셀 적재 (`own_projects`) — `data/inbox/own/*.xls|xlsx`.

시트 종류는 머리글로 판별한다 (열 이름은 2026-10-23 확인한 실물 기준, `KINDS`):
- proposal   연구과제 제안 현황: 구분·연구분류·연구과제 접수명·부서·제출일자·진행단계·위원회 결과.
             진행단계 "미채택" → status rejected, 그 밖은 proposed. visibility internal
- status     연구과제 현황: 구분·연구분류·연구과제명·시작/종료·책임연구원 부서·연구비·진행상태.
             14번째 열 이후(공정 세부)는 버린다. visibility internal
- history    2006~2024 과제목록(국가연구·자체연구 시트): 연구과제명·연구분류·부서명·기간·총연구비.
             status completed. visibility public
- performance 자체 및 국가과제 수행현황: 과제명·담당부서·추진구분·시작일·종료일·수행비용·비고.
             비고 "중단" → stopped, 종료일 지남 → completed, 아니면 ongoing. visibility public
이름 열(제안자·책임연구원·담당자)은 읽지 않는다.

같은 과제명이 여러 파일에 있으면 수행 기록(status > performance > history) > 제안 기록 순으로 하나만
남기고, 제안 기록의 진행단계·위원회 결과는 `raw.proposal` 로 붙인다 (`merge_records`).
Document: source own, doc_type rnd_project, text_basis abstract, doc_id own:<과제명 해시>.
파일은 샌드박스(xlsx·xls 파서)로 읽고, 처리 뒤에도 옮기지 않는다 (갱신 파일을 다시 적재한다).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from rra.adapters.sources._sandbox import SandboxError, SandboxLimits, run_parser
from rra.adapters.sources.alio._inbox import error_name
from rra.adapters.sources.alio.filecheck import FileRejected, open_validated
from rra.adapters.sources.own._names import nfc
from rra.domain.models import Document

logger = logging.getLogger("rra.sources.own_projects")

FILE_FORMATS = frozenset({"xls", "xlsx"})
MAX_HEADER_SCAN = 8
MAX_TITLE_CHARS = 300
MAX_FIELD_CHARS = 120

KIND_PROPOSAL = "proposal"
KIND_STATUS = "status"
KIND_HISTORY = "history"
KIND_PERFORMANCE = "performance"
PRIORITY = {KIND_STATUS: 0, KIND_PERFORMANCE: 1, KIND_HISTORY: 2, KIND_PROPOSAL: 3}
INTERNAL_KINDS = frozenset({KIND_PROPOSAL, KIND_STATUS})
KIND_LABEL = {
    KIND_PROPOSAL: "연구과제 제안 현황",
    KIND_STATUS: "연구과제 현황",
    KIND_HISTORY: "철도연구원 과제목록(2006~2024)",
    KIND_PERFORMANCE: "자체·국가과제 수행현황",
}
STATUS_LABEL = {
    "completed": "완료",
    "ongoing": "진행중",
    "stopped": "중단",
    "rejected": "미채택",
    "proposed": "제안·검토",
}
# 종류 판별: 머리글에 모두 있어야 하는 열 이름 (공백 제거 비교)
KINDS: dict[str, tuple[str, ...]] = {
    KIND_PROPOSAL: ("연구과제접수명", "진행단계"),
    KIND_STATUS: ("연구과제명", "책임연구원부서", "연구과제진행상태"),
    KIND_HISTORY: ("연구과제명", "책임연구원부서명"),
    KIND_PERFORMANCE: ("과제명", "담당부서", "추진구분"),
}
# 종류별 열 이름 → 필드 (공백 제거 비교)
COLUMNS: dict[str, dict[str, str]] = {
    KIND_PROPOSAL: {
        "구분": "program",
        "연구분류": "category",
        "연구과제접수명": "title",
        "부서": "department",
        "제출일자": "submitted",
        "진행단계": "stage",
        "위원회결과": "committee",
    },
    KIND_STATUS: {
        "구분": "program",
        "연구분류": "category",
        "연구과제명": "title",
        "연구시작일자": "start",
        "연구종료일자": "end",
        "책임연구원부서": "department",
        "총연구비": "budget",
        "연구과제진행상태": "remark",  # 완료·진행중
    },
    KIND_HISTORY: {
        "구분": "program",
        "연구과제명": "title",
        "연구분류": "category",
        "책임연구원부서명": "department",
        "연구시작일자": "start",
        "연구종료일자": "end",
        "총연구비": "budget",
    },
    KIND_PERFORMANCE: {
        "과제명": "title",
        "담당부서": "department",
        "추진구분": "program",
        "시작일": "start",
        "종료일": "end",
        "수행비용": "budget",
        "비고": "remark",
    },
}
_NORM = re.compile(r"[^0-9a-z가-힣]+")
_DATE = re.compile(r"(\d{4})[-./년]\s*(\d{1,2})(?:[-./월]\s*(\d{1,2}))?")

Runner = Callable[[int, str, SandboxLimits], Awaitable[dict[str, Any]]]


class Sheets(BaseModel):
    """샌드박스 자식 출력 재검증."""

    model_config = ConfigDict(extra="ignore")

    class Sheet(BaseModel):
        model_config = ConfigDict(extra="ignore")
        name: str = Field(max_length=100)
        rows: list[list[str | None]] = Field(max_length=200_000)

    sheets: list[Sheet] = Field(max_length=50)


@dataclass
class Record:
    kind: str
    title: str
    file: str
    sheet: str
    program: str | None = None  # 구분: 정기·수시·자체·국가
    category: str | None = None  # 연구분류: 기초·응용·개발
    department: str | None = None
    start: date | None = None
    end: date | None = None
    budget_krw: int | None = None
    status: str | None = None  # completed | ongoing | stopped | rejected | proposed
    stage: str | None = None  # 제안: 진행단계
    committee: str | None = None  # 제안: 위원회 결과
    submitted: date | None = None  # 제안: 제출일자
    remark: str | None = None
    proposal: dict[str, Any] | None = None  # 같은 과제의 제안 기록 (merge_records)
    row: int = 0

    def key(self) -> str:
        return norm_title(self.title)


def norm_title(title: str) -> str:
    return _NORM.sub("", nfc(title).lower())


def _squash(text: Any) -> str:
    return "".join(str(text or "").split())


def _clean(value: Any, limit: int = MAX_FIELD_CHARS) -> str | None:
    text = " ".join(str(value or "").split())
    return nfc(text)[:limit] or None


def parse_date(value: Any) -> date | None:
    m = _DATE.search(str(value or ""))
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_budget(value: Any) -> int | None:
    digits = re.sub(r"[^\d]", "", str(value or "").split(".")[0])
    return int(digits) if digits else None


def detect_kind(header: Sequence[str | None]) -> str | None:
    names = {_squash(h) for h in header if h}
    for kind, required in KINDS.items():
        if all(r in names for r in required):
            return kind
    return None


def parse_sheet(name: str, rows: Sequence[Sequence[str | None]], *, file: str) -> list[Record]:
    """머리글 행을 찾아 종류를 정하고 행마다 Record. 제목이 빈 행은 버린다."""
    for i, row in enumerate(rows[:MAX_HEADER_SCAN]):
        kind = detect_kind(row)
        if kind is None:
            continue
        columns = COLUMNS[kind]
        index = {columns[_squash(h)]: c for c, h in enumerate(row) if _squash(h) in columns}
        out: list[Record] = []
        for r, data in enumerate(rows[i + 1 :], start=i + 2):

            def get(
                f: str, _row: Sequence[str | None] = data, _index: Mapping[str, int] = index
            ) -> str | None:
                col = _index.get(f)
                return _row[col] if col is not None and col < len(_row) else None

            title = _clean(get("title"), MAX_TITLE_CHARS)
            if not title:
                continue
            program = _clean(get("program"))
            if kind == KIND_HISTORY and not program:
                program = "국가" if "국가" in name else ("자체" if "자체" in name else None)
            out.append(
                Record(
                    kind=kind,
                    title=title,
                    file=file,
                    sheet=nfc(name),
                    program=program,
                    category=_clean(get("category")),
                    department=_clean(get("department")),
                    start=parse_date(get("start")),
                    end=parse_date(get("end")),
                    budget_krw=parse_budget(get("budget")),
                    stage=_clean(get("stage")),
                    committee=_clean(get("committee")),
                    submitted=parse_date(get("submitted")),
                    remark=_clean(get("remark")),
                    row=r,
                )
            )
        return out
    return []


def assign_status(rec: Record, today: date) -> Record:
    if rec.kind == KIND_PROPOSAL:
        rec.status = "rejected" if "미채택" in (rec.stage or "") else "proposed"
    elif rec.kind == KIND_STATUS:
        state = rec.remark or ""
        rec.status = "completed" if "완료" in state else "ongoing" if "진행" in state else None
    elif rec.kind == KIND_HISTORY:
        rec.status = "completed"
    elif rec.kind == KIND_PERFORMANCE:
        if "중단" in (rec.remark or ""):
            rec.status = "stopped"
        elif rec.end and rec.end < today:
            rec.status = "completed"
        else:
            rec.status = "ongoing"
    return rec


def merge_records(records: Sequence[Record]) -> list[Record]:
    """같은 과제명 → 수행 기록 우선 하나. 제안 기록은 raw.proposal 로 붙인다."""
    groups: dict[str, list[Record]] = {}
    for rec in records:
        groups.setdefault(rec.key(), []).append(rec)
    out: list[Record] = []
    for key, recs in groups.items():
        if not key:
            continue
        best = min(recs, key=lambda r: (PRIORITY[r.kind], r.file, r.row))
        proposals = [r for r in recs if r.kind == KIND_PROPOSAL and r is not best]
        if proposals:
            p = min(proposals, key=lambda r: (r.submitted or date.min, r.row))
            best.proposal = {
                "stage": p.stage,
                "committee": p.committee,
                "submitted": p.submitted.isoformat() if p.submitted else None,
                "status": p.status,
                "department": p.department,
            }
        out.append(best)
    return out


def record_document(rec: Record) -> Document:
    """순수 함수. 본문은 과제명·구분·부서·기간·상태를 한국어로 적은 짧은 요약이다."""
    period = _period_text(rec.start, rec.end)
    parts = [
        p
        for p in (
            KIND_LABEL.get(rec.kind, rec.kind),
            rec.program,
            rec.category,
            f"부서 {rec.department}" if rec.department else None,
            f"기간 {period}" if period else None,
            f"상태 {STATUS_LABEL.get(rec.status or '', rec.status)}" if rec.status else None,
            f"총연구비 {rec.budget_krw:,}원" if rec.budget_krw else None,
            f"제출 {rec.submitted.isoformat()}" if rec.submitted else None,
            f"진행단계 {rec.stage}" if rec.stage else None,
            f"위원회 {rec.committee}" if rec.committee else None,
            f"비고 {rec.remark}" if rec.remark and rec.kind == KIND_PERFORMANCE else None,
        )
        if p
    ]
    lines = [f"과제명: {rec.title}", "[사내 과제] " + " · ".join(parts)]
    if rec.proposal:
        p = rec.proposal
        lines.append(
            "제안 기록: "
            + " · ".join(
                x
                for x in (
                    f"제출 {p['submitted']}" if p.get("submitted") else None,
                    f"진행단계 {p['stage']}" if p.get("stage") else None,
                    f"위원회 {p['committee']}" if p.get("committee") else None,
                )
                if x
            )
        )
    visibility = "internal" if rec.kind in INTERNAL_KINDS else "public"
    raw = {k: v for k, v in asdict(rec).items() if k not in ("title", "row")}
    for k in ("start", "end", "submitted"):
        raw[k] = raw[k].isoformat() if raw[k] else None
    return Document(
        doc_id="own:" + hashlib.sha256(rec.key().encode()).hexdigest()[:16],
        source="own",
        doc_type="rnd_project",
        title=rec.title,
        abstract="\n".join(lines),
        pub_date=rec.start or rec.submitted,
        orgs=["korail"],
        lang="ko",
        department=rec.department,
        project_period=(rec.start, rec.end) if rec.start and rec.end else None,
        text_basis="abstract",
        visibility=visibility,
        raw=raw,
    )


def _period_text(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{start.isoformat()} ~ {end.isoformat()}"
    return start.isoformat() if start else (end.isoformat() if end else "")


class OwnProjectsSource:
    """SourcePort + InboxSource. IngestReport 키·Document.source 모두 own."""

    source = "own_projects"

    def __init__(
        self,
        inbox: Path,
        *,
        limits: SandboxLimits,
        today: Callable[[], date] = date.today,
        runner: Runner = run_parser,
    ):
        self.inbox = Path(inbox)
        self.limits = limits
        self._today = today
        self._runner = runner

    def __repr__(self) -> str:
        return "OwnProjectsSource()"

    async def aclose(self) -> None:
        return None

    def pending(self) -> list[Path]:
        if not self.inbox.is_dir():
            return []
        return sorted(
            p
            for p in self.inbox.iterdir()
            if p.is_file()
            and not p.name.startswith((".", "_", "~$"))
            and p.suffix.lower().lstrip(".") in FILE_FORMATS
        )

    def inbox_status(self) -> dict[str, int]:
        return {"pending": len(self.pending()), "done": 0, "quarantine": 0}

    async def search(self, query: str | None, limit: int) -> list[dict[str, Any]]:
        """query 는 쓰지 않는다. 파일 전부를 읽어 과제명으로 합친 뒤 limit 만큼."""
        records: list[Record] = []
        today = self._today()
        for path in self.pending():
            sheets = await self._read(path)
            if sheets is None:
                continue
            for sheet in sheets.sheets:
                for rec in parse_sheet(sheet.name, sheet.rows, file=nfc(path.name)):
                    records.append(assign_status(rec, today))
        merged = merge_records(records)
        logger.info(
            "own_projects.records files=%d rows=%d merged=%d",
            len(self.pending()),
            len(records),
            len(merged),
        )
        return [_record_raw(r) for r in merged[: max(0, limit)]]

    async def _read(self, path: Path) -> Sheets | None:
        max_bytes = int(self.limits.max_input_mb * 1024 * 1024)
        try:
            vf = open_validated(path, max_bytes=max_bytes, allowed=FILE_FORMATS)
        except FileRejected as exc:
            logger.warning("own_projects.rejected error=%s", error_name(exc))
            return None
        with vf:
            try:
                return Sheets.model_validate(await self._runner(vf.fd, vf.fmt, self.limits))
            except (SandboxError, ValidationError) as exc:
                logger.warning(
                    "own_projects.rejected error=%s file=sha256:%s", error_name(exc), vf.sha256[:8]
                )
                return None

    def normalize(self, raw: Mapping[str, Any]) -> Document:
        return record_document(_record_from_raw(raw))


def _record_raw(rec: Record) -> dict[str, Any]:
    out = asdict(rec)
    for k in ("start", "end", "submitted"):
        out[k] = out[k].isoformat() if out[k] else None
    return out


def _record_from_raw(raw: Mapping[str, Any]) -> Record:
    data = dict(raw)
    for k in ("start", "end", "submitted"):
        data[k] = parse_date(data.get(k)) if data.get(k) else None
    return Record(**{k: v for k, v in data.items() if k in Record.__dataclass_fields__})
