"""별지 제2호서식(2024.02.19.) HWPX 렌더러 — python-hwpx.

두 모드:
- 템플릿 모드: config/templates/proposal_korail.hwpx 가 있으면 그 파일을 열어 slots.yaml 에 선언된
  자리표시자({{…}})만 치환한다. 섹션 XML 의 문자열만 바꾸므로 템플릿 구조는 그대로다.
  자리표시자는 한 run(<hp:t>) 안에 있어야 한다 — 글자 속성이 중간에 바뀌어 run 이 갈라지면
  치환되지 않고 TemplateSlotUnfilled 로 거부한다 (양식 파일에서 자리표시자를 한 글자체로 다시 입력).
- 생성 모드: 템플릿이 없으면 양식 구조(1 과제 개요 / 2 가·나·다 / 3 기대효과 / 4 활용계획 /
  5 특이사항)를 표로 직접 만든다.

보안 F:
- 치환 텍스트는 sanitize(XML 1.0 금지 문자 제거) 뒤 xml.sax.saxutils.escape 를 거쳐 XML 문자열에
  들어간다 (템플릿 모드). 생성 모드는 python-hwpx 가 XML 노드로 넣어 직렬화하므로 escape 가
  라이브러리 안에서 일어난다.
- 결과 zip 의 모든 섹션 XML 을 defusedxml 로 다시 파싱해 well-formed 가 아니면 출력을 거부한다.
- 체크 칸은 confirmed(Confirmation)로만 채운다. 과제유형·활용계획이 확정되지 않았으면 거부한다.
- 제안자 정보(ProposerInfo)는 render() 인자로만 받는다. 이 모듈은 파일을 쓰지 않는다 (bytes 반환).
- slots.yaml 에 없는 자리표시자·선택지 id 를 요구하면 UnknownSlot.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from rra.application.ports.renderer import RenderRejected
from rra.domain.models import Confirmation, Draft, ProposerInfo, StrategyCatalog
from rra.domain.models.selection import TASK_TYPES, UTILIZATION

FORM_TITLE = "연구과제 제안서"
FORM_NOTE = "한국철도공사 연구개발 규정 시행세칙 별지 제2호서식 (개정 2024.02.19.)"
CHECKED, UNCHECKED = "■", "□"
_PLACEHOLDER = re.compile(r"\{\{[^{}]{1,40}\}\}")
# XML 1.0 에서 허용되지 않는 문자 (탭·개행·CR 은 허용)
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
MAX_SLOT_CHARS = 20_000
MAX_SECTION_XML_BYTES = 50 * 1024 * 1024


class UnknownSlot(RenderRejected):
    """slots.yaml 에 선언되지 않은 자리표시자·선택지를 요구했다."""


class ConfirmationRequired(RenderRejected):
    """체크 칸(과제유형·활용계획)은 사용자가 확정한 값으로만 채운다 — 확정 전엔 렌더하지 않는다."""


class TemplateSlotUnfilled(RenderRejected):
    """템플릿 모드: 치환되지 않은 자리표시자가 남았다."""


class RenderedXmlInvalid(RenderRejected):
    """결과 섹션 XML 이 well-formed 가 아니다 — 출력을 내보내지 않는다."""


def sanitize(value: object, *, limit: int = MAX_SLOT_CHARS) -> str:
    """XML 에 넣을 수 없는 문자 제거 + 길이 상한. escape 는 하지 않는다 (넣는 자리에서 한다)."""
    text = _FORBIDDEN.sub("", "" if value is None else str(value)).replace("\r\n", "\n")
    return text[:limit]


# ── slots.yaml ────────────────────────────────────────────
@dataclass(frozen=True)
class SlotMap:
    """config/templates/proposal_korail.slots.yaml 의 자리표시자 선언."""

    text: dict[str, str] = field(default_factory=dict)  # 섹션 키 → {{…}}
    choice: dict[str, dict[str, str]] = field(default_factory=dict)  # 섹션 → 선택지 id → {{…}}
    input: dict[str, str] = field(default_factory=dict)  # request 경로(budget.account) → {{…}}
    render_only: dict[str, str] = field(default_factory=dict)  # proposer 경로 → {{…}}

    @classmethod
    def from_config(cls, data: Mapping[str, Any]) -> SlotMap:
        def flat(section: str) -> dict[str, str]:
            raw = data.get(section) or {}
            return {str(k): _placeholder(v) for k, v in raw.items()}

        choice = {
            str(key): {str(i): _placeholder(p) for i, p in (opts or {}).items()}
            for key, opts in (data.get("choice") or {}).items()
        }
        return cls(
            text=flat("text"), choice=choice, input=flat("input"), render_only=flat("render_only")
        )

    def placeholders(self) -> frozenset[str]:
        out = set(self.text.values()) | set(self.input.values()) | set(self.render_only.values())
        for opts in self.choice.values():
            out |= set(opts.values())
        return frozenset(out)


def _placeholder(value: Any) -> str:
    text = str(value).strip()
    if not _PLACEHOLDER.fullmatch(text):
        raise ValueError(f"slots.yaml 자리표시자 형식이 올바르지 않습니다: {text!r}")
    return text


# ── 값 조립 (순수 함수) ───────────────────────────────────
def slot_values(
    draft: Draft,
    slots: SlotMap,
    *,
    confirmation: Confirmation | None,
    proposer: ProposerInfo | None,
    strategy: StrategyCatalog,
    required_choices: tuple[str, ...] = ("task_type", "utilization"),
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """{{자리표시자}} → 치환 문자열. 체크 칸은 확정값으로만, 개인정보는 proposer 인자로만."""
    confirmed = dict(confirmation.choices) if confirmation else {}
    missing = [k for k in required_choices if k in slots.choice and not confirmed.get(k)]
    if missing:
        raise ConfirmationRequired(f"확정되지 않은 선택형 항목: {', '.join(missing)}")

    values: dict[str, str] = {}
    req = draft.request
    for key, ph in slots.text.items():
        section = draft.section(key)
        text = "\n".join(s.text for s in section.sentences) if section else ""
        if key == "overlap_review" and req.remarks:
            text = f"{text}\n{req.remarks}".strip()
        values[ph] = sanitize(text)

    for key, options in slots.choice.items():
        picked = list(confirmed.get(key) or [])
        if key == "strategy_alignment":
            values.update(_strategy_values(options, picked, strategy))
            continue
        unknown = [i for i in picked if i not in options]
        if unknown:
            raise UnknownSlot(f"{key}: slots.yaml 에 없는 선택지 {unknown}")
        for option_id, ph in options.items():
            values[ph] = CHECKED if option_id in picked else UNCHECKED

    budget = req.budget
    inputs = {
        "budget.account": budget.account if budget else "",
        "budget.amount_thousand_krw": (
            f"{budget.amount_thousand_krw:,}"
            if budget and budget.amount_thousand_krw is not None
            else ""
        ),
        "department": req.department,
    }
    for path, ph in slots.input.items():
        if path not in inputs:
            raise UnknownSlot(f"input 슬롯을 채울 수 없습니다: {path}")
        values[ph] = sanitize(inputs[path])

    person = proposer or ProposerInfo()
    render_only = {
        "proposed_on": person.proposed_on,
        "proposer.rank": person.proposer.rank,
        "proposer.name": person.proposer.name,
        "proposer.phone": person.proposer.phone,
        "head.rank": person.head.rank,
        "head.name": person.head.name,
        "head.phone": person.head.phone,
    }
    for path, ph in slots.render_only.items():
        if path not in render_only:
            raise UnknownSlot(f"render_only 슬롯을 채울 수 없습니다: {path}")
        values[ph] = sanitize(render_only[path])

    declared = slots.placeholders()
    for ph, value in (extra or {}).items():
        if ph not in declared:
            raise UnknownSlot(f"slots.yaml 에 선언되지 않은 자리표시자: {ph}")
        values[ph] = sanitize(value)
    return values


def _strategy_values(
    options: Mapping[str, str], picked: list[str], strategy: StrategyCatalog
) -> dict[str, str]:
    directions: list[str] = []
    tasks: list[str] = []
    for task_id in picked:
        direction = strategy.direction_of(task_id)
        if direction is None:
            raise UnknownSlot(f"strategy_alignment: 전략 목록에 없는 id {task_id!r}")
        if direction.name not in directions:
            directions.append(direction.name)
        tasks.append(next(t.name for t in direction.tasks if t.id == task_id))
    out: dict[str, str] = {}
    for key, ph in options.items():
        if key == "direction":
            out[ph] = sanitize(", ".join(directions))
        elif key == "task":
            out[ph] = sanitize(", ".join(tasks))
        else:
            raise UnknownSlot(f"strategy_alignment 슬롯은 direction·task 만 가능: {key}")
    return out


# ── 렌더러 ────────────────────────────────────────────────
class HwpxRenderer:
    def __init__(
        self,
        slots: SlotMap,
        *,
        titles: Mapping[str, str] | None = None,
        strategy: StrategyCatalog | None = None,
        template_path: Path | None = None,
        required_choices: tuple[str, ...] = ("task_type", "utilization"),
    ):
        self.slots = slots
        self.titles = dict(titles or {})
        self.strategy = strategy or StrategyCatalog()
        self.template_path = Path(template_path) if template_path else None
        self.required_choices = required_choices

    def __repr__(self) -> str:
        mode = "template" if self.template_path else "generate"
        return f"HwpxRenderer(mode={mode})"

    @property
    def mode(self) -> str:
        return "template" if self.template_path and self.template_path.is_file() else "generate"

    def render(
        self,
        draft: Draft,
        *,
        confirmation: Confirmation | None = None,
        proposer: ProposerInfo | None = None,
        extra: Mapping[str, str] | None = None,
    ) -> bytes:
        values = slot_values(
            draft,
            self.slots,
            confirmation=confirmation,
            proposer=proposer,
            strategy=self.strategy,
            required_choices=self.required_choices,
            extra=extra,
        )
        if self.mode == "template":
            data = self._fill_template(self.template_path.read_bytes(), values)  # type: ignore[union-attr]
        else:
            data = self._generate(values, confirmation)
        verify_hwpx(data)
        return data

    # ── 템플릿 모드 ───────────────────────────────────────
    def _fill_template(self, template: bytes, values: Mapping[str, str]) -> bytes:
        from hwpx.package import HwpxPackage

        pkg = HwpxPackage.open(template)
        before = sorted(pkg.files())
        leftover: set[str] = set()
        for path in pkg.section_paths():
            xml = pkg.get_text(path)
            for ph, value in values.items():
                xml = xml.replace(ph, escape(value))  # 보안 F: 값은 escape 를 거쳐서만 들어간다
            leftover |= set(_PLACEHOLDER.findall(xml)) & self.slots.placeholders()
            pkg.set_part(path, xml)
        if leftover:
            raise TemplateSlotUnfilled(
                "치환되지 않은 자리표시자(한 글자체로 다시 입력): " + ", ".join(sorted(leftover))
            )
        buf = io.BytesIO()
        pkg.save(buf)
        data = buf.getvalue()
        if sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()) != before:
            raise RenderedXmlInvalid("템플릿 구조가 바뀌었습니다 — 출력을 거부합니다.")
        return data

    # ── 생성 모드 ─────────────────────────────────────────
    def _generate(self, values: Mapping[str, str], confirmation: Confirmation | None) -> bytes:
        from hwpx.document import HwpxDocument

        v = _Lookup(values, self.slots)
        confirmed = dict(confirmation.choices) if confirmation else {}
        doc = HwpxDocument.new()
        doc.add_heading(FORM_TITLE, level=1)
        doc.add_paragraph(FORM_NOTE)

        task_marks = "   ".join(
            f"{CHECKED if i in confirmed.get('task_type', []) else UNCHECKED} {label}"
            for i, label in TASK_TYPES.items()
        )
        budget = " / ".join(
            p
            for p in (
                f"예산과목: {v.input('budget.account')}" if v.input("budget.account") else "",
                f"금액: {v.input('budget.amount_thousand_krw')} 천원"
                if v.input("budget.amount_thousand_krw")
                else "",
            )
            if p
        )
        self._table(
            doc,
            "1. 과제 개요",
            [
                ("가. 연구과제명", v.text("title")),
                ("나. 소요예산(추정액)", budget),
                ("다. 과제유형", task_marks),
            ],
        )
        strategy_line = ", ".join(
            x
            for x in (
                v.choice("strategy_alignment", "direction"),
                v.choice("strategy_alignment", "task"),
            )
            if x
        )
        self._table(
            doc,
            "2. 제안 배경 및 목적",
            [
                ("가. 필요성 (1) 정책적 중요도", v.text("policy_importance")),
                ("(2) 기술적 중요도", v.text("tech_importance")),
                (
                    "(3) 공사 경영전략과의 정합성",
                    "\n".join(x for x in (strategy_line, v.text("strategy_alignment")) if x),
                ),
                ("나. 연구목적", v.text("objective")),
                ("다. 연구 방법 및 주요내용", v.text("method")),
            ],
        )
        self._table(
            doc,
            "3. 기대효과",
            [
                ("가. 경영혁신 측면", v.text("expected_management")),
                ("나. 기술혁신 측면", v.text("expected_technology")),
                ("다. 대외위상 측면", v.text("expected_standing")),
            ],
        )
        marks = "\n".join(
            f"{CHECKED if i in confirmed.get('utilization', []) else UNCHECKED} {label}"
            for i, label in UTILIZATION.items()
        )
        self._table(
            doc,
            "4. 연구결과 활용계획",
            [("활용계획 (해당 항목 체크)", marks), ("실용화 계획", v.text("utilization"))],
        )
        self._table(doc, "5. 특이사항", [("유사과제 검토 결과 등", v.text("overlap_review"))])

        doc.add_paragraph("")
        doc.add_paragraph(f"제안일자: {v.render_only('proposed_on')}")
        doc.add_paragraph(
            "제안자: "
            + " ".join(
                x for x in (v.render_only("proposer.rank"), v.render_only("proposer.name")) if x
            )
            + (
                f" (연락처 {v.render_only('proposer.phone')})"
                if v.render_only("proposer.phone")
                else ""
            )
        )
        doc.add_paragraph(
            "제안부서장: "
            + " ".join(x for x in (v.render_only("head.rank"), v.render_only("head.name")) if x)
            + (f" (연락처 {v.render_only('head.phone')})" if v.render_only("head.phone") else "")
        )
        doc.add_paragraph(f"제안부서: {v.input('department')}")
        return doc.to_bytes()

    @staticmethod
    def _table(doc: Any, caption: str, rows: list[tuple[str, str]]) -> None:
        table = doc.add_table(len(rows) + 1, 2)
        table.merge_cells(0, 0, 0, 1)
        table.set_cell_text(0, 0, caption)
        for i, (label, text) in enumerate(rows, start=1):
            table.set_cell_text(i, 0, label)
            table.set_cell_text(i, 1, text)
        table.set_column_widths([1, 3])
        doc.add_paragraph("")


class _Lookup:
    """자리표시자 → 값 조회를 섹션 키·경로로 할 수 있게 한다 (생성 모드)."""

    def __init__(self, values: Mapping[str, str], slots: SlotMap):
        self.values, self.slots = values, slots

    def text(self, key: str) -> str:
        return self.values.get(self.slots.text.get(key, ""), "")

    def input(self, path: str) -> str:
        return self.values.get(self.slots.input.get(path, ""), "")

    def render_only(self, path: str) -> str:
        return self.values.get(self.slots.render_only.get(path, ""), "")

    def choice(self, key: str, option: str) -> str:
        return self.values.get(self.slots.choice.get(key, {}).get(option, ""), "")


# ── 검증 (보안 F) ─────────────────────────────────────────
def verify_hwpx(data: bytes) -> list[str]:
    """zip 열기 + 모든 섹션 XML 을 defusedxml 로 재파싱. 실패하면 RenderedXmlInvalid. 섹션 경로."""
    import defusedxml.ElementTree as DET

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RenderedXmlInvalid("HWPX zip 을 열 수 없습니다.") from exc
    sections = [n for n in archive.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)]
    if not sections:
        raise RenderedXmlInvalid("섹션 XML 이 없습니다.")
    for name in sections:
        info = archive.getinfo(name)
        if info.file_size > MAX_SECTION_XML_BYTES:
            raise RenderedXmlInvalid("섹션 XML 이 너무 큽니다.")
        try:
            DET.fromstring(archive.read(name))
        except Exception as exc:  # defusedxml: 외부 엔티티·폭탄 포함 모두 거부
            raise RenderedXmlInvalid(
                f"{name}: well-formed XML 이 아닙니다 ({type(exc).__name__})"
            ) from exc
    return sections
