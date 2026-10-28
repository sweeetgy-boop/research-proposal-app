"""별지 제2호서식(2024.02.19.) HWPX 렌더러 — python-hwpx.

두 모드:
- 템플릿 모드: config/templates/proposal_korail.hwpx 가 있으면 그 파일을 열어 slots.yaml 에 선언된
  자리표시자({{…}})만 치환한다. 섹션 XML 의 문자열만 바꾸므로 템플릿 구조는 그대로다.
  자리표시자는 한 run(<hp:t>) 안에 있어야 한다 — 글자 속성이 중간에 바뀌어 run 이 갈라지면
  치환되지 않고 TemplateSlotUnfilled 로 거부한다 (양식 파일에서 자리표시자를 한 글자체로 다시 입력).
  slots.yaml `paragraphs` 에 적힌 섹션은 자리표시자가 든 단락(<hp:p>)을 통째로 복제해 문장마다
  "○ " 머리표가 붙은 단락 하나씩으로 넣는다 (서식 paraPr·charPr 은 원본 단락 그대로).
  나머지 슬롯(연구과제명·예산·전략방향·전략과제·제안자 칸)은 같은 run 안에서 인라인 치환만 한다.
- 생성 모드: 템플릿이 없으면 양식 구조(1 과제 개요 / 2 가·나·다 / 3 기대효과 / 4 활용계획 /
  5 특이사항)를 표로 직접 만든다. 체크 표시는 ■/□.

보안 F:
- 치환 텍스트는 sanitize(XML 1.0 금지 문자 제거) 뒤 xml.sax.saxutils.escape 를 거쳐 XML 문자열에
  들어간다 (템플릿 모드). 순서는 escape → 단락 생성 → defusedxml 재파싱. 생성 모드는 python-hwpx 가
  XML 노드로 넣어 직렬화하므로 escape 가 라이브러리 안에서 일어난다.
- 결과 zip 의 모든 섹션 XML 을 defusedxml 로 다시 파싱해 well-formed 가 아니면 출력을 거부한다.
- 체크 칸은 confirmed(Confirmation)로만 채운다. 과제유형·활용계획이 확정되지 않았으면 거부한다.
  표시 문자는 slots.yaml marks (실물 양식은 괄호 안 "○" / " ").
- 제안자 정보(ProposerInfo)는 render() 인자로만 받는다. 이 모듈은 파일을 쓰지 않는다 (bytes 반환).
  제안일자가 비면 렌더 시점 날짜를 "2026. 10. 26." 형식으로 넣는다 (clock 인자로 바꿀 수 있다).
- slots.yaml 에 없는 자리표시자·선택지 id 를 요구하면 UnknownSlot.
- 양식 본문에는 근거 문서 id·출처를 넣지 않는다 (문장 text 만). task_type 의 설명 문장도
  넣지 않는다.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from rra.application.ports.renderer import RenderRejected
from rra.domain.models import Confirmation, Draft, ProposerInfo, StrategyCatalog
from rra.domain.models.figure import Figure, FigurePlacement
from rra.domain.models.selection import TASK_TYPES, UTILIZATION
from rra.domain.rules.llm_output import clean_sentence

FORM_TITLE = "연구과제 제안서"
FORM_NOTE = "한국철도공사 연구개발 규정 시행세칙 별지 제2호서식 (개정 2024.02.19.)"
CHECKED, UNCHECKED = "■", "□"  # 생성 모드의 체크 표시. 템플릿 모드는 slots.yaml marks
DEFAULT_BULLET = "○ "
_PLACEHOLDER = re.compile(r"\{\{[^{}]{1,40}\}\}")
# XML 1.0 에서 허용되지 않는 문자 (탭·개행·CR 은 허용)
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_DATE = re.compile(r"^\s*(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*[.일]?\s*$")
MAX_SLOT_CHARS = 20_000
MAX_SECTION_XML_BYTES = 50 * 1024 * 1024
_P_OPEN, _P_CLOSE = "<hp:p ", "</hp:p>"
# 한/글이 저장한 줄 배치 캐시. 글자가 바뀐 단락에 남겨 두면 한/글이 그대로 써서 글자가 겹친다
# (python-hwpx 저장 검증이 거부). 캐시가 없는 단락은 한/글이 다시 배치한다.
_LINESEG = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.S)


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


def format_proposed_on(value: str, today: Callable[[], date] = date.today) -> str:
    """제안일자 칸 표기 "2026. 10. 26.".

    비면 렌더 시점의 날짜. "2026-10-26"·"2026.10.26"·"2026년 10월 26일" 꼴은 같은 표기로 맞추고,
    그 밖의 문자열은 그대로 둔다 (자르지 않는다 — 길이는 render_check 가 알린다).
    """
    text = (value or "").strip()
    if not text:
        d = today()
        return f"{d.year}. {d.month:02d}. {d.day:02d}."
    m = _DATE.match(text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return f"{y}. {mo:02d}. {d:02d}."
    return text


def _scrub(sentence: str) -> str:
    """문장 속 자료 태그·(文档ID: …) 조각 제거 + 공백 정리 (domain 규칙). 문장은 자르지 않는다."""
    return clean_sentence(sentence)


def format_budget_amount(amount_thousand_krw: int | None) -> str:
    """1-나 금액 칸. 입력(Budget.amount_thousand_krw)이 이미 천원 단위이므로 환산 없이
    천 단위 쉼표만 찍는다 (양식 칸 뒤의 "천원" 단위 글자는 템플릿에 있다). 비면 빈칸."""
    return f"{amount_thousand_krw:,}" if amount_thousand_krw is not None else ""


# ── slots.yaml ────────────────────────────────────────────
@dataclass(frozen=True)
class SlotMap:
    """config/templates/proposal_korail.slots.yaml 의 자리표시자 선언."""

    text: dict[str, str] = field(default_factory=dict)  # 섹션 키 → {{…}}
    choice: dict[str, dict[str, str]] = field(default_factory=dict)  # 섹션 → 선택지 id → {{…}}
    input: dict[str, str] = field(default_factory=dict)  # request 경로(budget.account) → {{…}}
    render_only: dict[str, str] = field(default_factory=dict)  # proposer 경로 → {{…}}
    paragraphs: frozenset[str] = frozenset()  # 문장마다 단락으로 넣는 text 섹션 키
    bullet: str = DEFAULT_BULLET  # 그 단락의 머리표
    checked: str = CHECKED  # 템플릿 모드 체크 표시
    unchecked: str = UNCHECKED
    line_limits: dict[str, int] = field(default_factory=dict)  # 한 줄 칸 글자 수 (render_check)

    @classmethod
    def from_config(cls, data: Mapping[str, Any]) -> SlotMap:
        def flat(section: str) -> dict[str, str]:
            raw = data.get(section) or {}
            return {str(k): _placeholder(v) for k, v in raw.items()}

        choice = {
            str(key): {str(i): _placeholder(p) for i, p in (opts or {}).items()}
            for key, opts in (data.get("choice") or {}).items()
        }
        text = flat("text")
        paragraphs = frozenset(str(k) for k in (data.get("paragraphs") or []))
        unknown = paragraphs - set(text)
        if unknown:
            raise ValueError(f"slots.yaml paragraphs 에 text 슬롯이 아닌 키: {sorted(unknown)}")
        marks = data.get("marks") or {}
        checked = _mark(marks.get("checked", CHECKED))
        unchecked = _mark(marks.get("unchecked", UNCHECKED))
        limits = {str(k): int(v) for k, v in (data.get("line_limits") or {}).items()}
        return cls(
            text=text,
            choice=choice,
            input=flat("input"),
            render_only=flat("render_only"),
            paragraphs=paragraphs,
            bullet=sanitize(data.get("paragraph_bullet", DEFAULT_BULLET)),
            checked=checked,
            unchecked=unchecked,
            line_limits=limits,
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


def _mark(value: Any) -> str:
    text = sanitize(value)
    if len(text) > 4 or "{{" in text:
        raise ValueError(f"slots.yaml marks 는 4자 이하 문자열이어야 합니다: {text!r}")
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
    today: Callable[[], date] = date.today,
) -> dict[str, str]:
    """{{자리표시자}} → 치환 문자열. 체크 칸은 확정값으로만, 개인정보는 proposer 인자로만.

    여러 문장 섹션은 문장을 개행으로 이어 둔다 — 템플릿 모드가 개행 단위로 단락을 만든다.
    근거 id·출처는 넣지 않는다.
    """
    confirmed = dict(confirmation.choices) if confirmation else {}
    missing = [k for k in required_choices if k in slots.choice and not confirmed.get(k)]
    if missing:
        raise ConfirmationRequired(f"확정되지 않은 선택형 항목: {', '.join(missing)}")

    values: dict[str, str] = {}
    req = draft.request
    for key, ph in slots.text.items():
        section = draft.section(key)
        sep = "\n" if key in slots.paragraphs else " "  # 한 줄 칸(연구과제명)은 띄어쓰기로 잇는다
        # 양식 본문에 근거 id·출처 조각을 넣지 않는다 — 저장된 문장에 남아 있어도 여기서 지운다
        text = sep.join(_scrub(s.text) for s in section.sentences) if section else ""
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
            values[ph] = slots.checked if option_id in picked else slots.unchecked

    budget = req.budget
    person = proposer or ProposerInfo()
    inputs = {
        "budget.account": budget.account if budget else "",
        "budget.amount_thousand_krw": (
            format_budget_amount(budget.amount_thousand_krw) if budget else ""
        ),
        # 마무리 때 입력한 제안부서가 있으면 그것, 없으면 request 의 값
        "department": person.department or req.department,
    }
    for path, ph in slots.input.items():
        if path not in inputs:
            raise UnknownSlot(f"input 슬롯을 채울 수 없습니다: {path}")
        values[ph] = sanitize(inputs[path])

    render_only = {
        "proposed_on": format_proposed_on(person.proposed_on, today),
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
        clock: Callable[[], date] = date.today,
        figure_placement: str = "inline",
        figure_max_width: int = 42000,
        figure_caption_prefix: str = "그림",
    ):
        self.slots = slots
        self.titles = dict(titles or {})
        self.strategy = strategy or StrategyCatalog()
        self.template_path = Path(template_path) if template_path else None
        self.required_choices = required_choices
        self.clock = clock
        # [G] 그림 — inline(섹션 칸 안, 본문 뒤) | appendix(문서 끝 "별첨 그림"). 칸 없으면 appendix
        self.figure_placement = figure_placement
        self.figure_max_width = int(figure_max_width)
        self.figure_caption_prefix = figure_caption_prefix

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
            today=self.clock,
        )
        if self.mode == "template":
            data = self._fill_template(self.template_path.read_bytes(), values)  # type: ignore[union-attr]
        else:
            data = self._generate(values, confirmation)
        verify_hwpx(data)
        return data

    def render_with_figures(
        self,
        draft: Draft,
        *,
        confirmation: Confirmation | None = None,
        proposer: ProposerInfo | None = None,
        figures: Sequence[tuple[Figure, bytes, str]] = (),
    ) -> tuple[bytes, list[FigurePlacement]]:
        """[G] 그림 삽입. 섹션 본문 마지막 줄에 표식 단락을 넣어 치환한 뒤, 표식 단락을 그림+캡션
        으로 바꾼다(inline). 표식이 표 칸 안에 없거나 설정이 appendix 면 "(별첨 그림 n 참조)" 로
        바꾸고 문서 끝 "별첨 그림" 에 모은다. BinData 추가 외의 구조 변화는 거부한다."""
        if not figures:
            return self.render(draft, confirmation=confirmation, proposer=proposer), []
        values = dict(
            slot_values(
                draft,
                self.slots,
                confirmation=confirmation,
                proposer=proposer,
                strategy=self.strategy,
                required_choices=self.required_choices,
                today=self.clock,
            )
        )
        numbered: list[tuple[int, Figure, bytes, str]] = []
        for n, (fig, data, mime) in enumerate(figures, start=1):
            if mime not in ("image/png", "image/jpeg") or not data:
                raise RenderRejected("그림 형식은 PNG·JPEG 만 받습니다.")
            numbered.append((n, fig, data, mime))
            ph = self.slots.text.get(fig.section)
            if ph is not None and fig.section in self.slots.paragraphs:
                values[ph] = (values.get(ph, "") + "\n" + figure_marker(fig.id)).strip("\n")
        if self.mode == "template":
            data = self._fill_template(
                self.template_path.read_bytes(),  # type: ignore[union-attr]
                values,
                allow_bindata=True,
            )
        else:
            data = self._generate(values, confirmation)
        data, placements = self._insert_figures(data, numbered)
        verify_hwpx(data)
        return data, placements

    def _insert_figures(
        self, data: bytes, figures: list[tuple[int, Figure, bytes, str]]
    ) -> tuple[bytes, list[FigurePlacement]]:
        from hwpx.document import HwpxDocument

        from rra.adapters.figures import image_size

        doc = HwpxDocument.open(data)
        placements: list[FigurePlacement] = []
        appendix: list[tuple[int, Figure, str, int, int]] = []  # (n, fig, item_id, w, h)
        for n, fig, png, mime in figures:
            try:
                w_px, h_px = image_size(png)
            except ValueError as exc:
                raise RenderRejected("그림 파일을 읽을 수 없습니다.") from exc
            fmt = "jpg" if mime == "image/jpeg" else "png"
            item_id = str(_add_image(doc, png, fmt))
            cell_para = _find_marker(doc, figure_marker(fig.id))
            inline = self.figure_placement == "inline" and cell_para is not None
            width = self.figure_max_width
            cell = cell_para[0] if cell_para else None
            if cell is not None and getattr(cell, "width", None):
                width = min(width, max(int(cell.width) - 2000, 8000))
            height = max(1, round(width * h_px / max(w_px, 1)))
            caption = f"{self.figure_caption_prefix} {n}. {sanitize(fig.caption)}".strip()
            extra = [sanitize(fig.source_caption)] if fig.source_caption else []
            if inline and cell_para is not None:
                para = cell_para[1]
                _clear_paragraph(para)
                para.add_picture(item_id, width=width, height=height)
                if cell is not None:  # 표 칸 안 — 칸 끝에 캡션 단락
                    for text in (caption, *extra):
                        cell.add_paragraph(text)
                else:  # 본문 단락(실물 양식) — 그림 단락 바로 뒤에 캡션 단락
                    _insert_after(para, [caption, *extra])
                placements.append(
                    FigurePlacement(id=fig.id, placement="inline", number=n, bytes=len(png))
                )
            else:
                if cell_para is not None:
                    note = f"(별첨 {self.figure_caption_prefix} {n} 참조)"
                    _set_paragraph_text(cell_para[1], note)
                appendix.append((n, fig, item_id, width, height))
                placements.append(
                    FigurePlacement(id=fig.id, placement="appendix", number=n, bytes=len(png))
                )
        if appendix:
            doc.add_paragraph(f"별첨 {self.figure_caption_prefix}")
            for n, fig, item_id, width, height in appendix:
                para = doc.add_paragraph("")
                para.add_picture(item_id, width=width, height=height)
                doc.add_paragraph(f"{self.figure_caption_prefix} {n}. {sanitize(fig.caption)}")
                if fig.source_caption:
                    doc.add_paragraph(sanitize(fig.source_caption))
        return doc.to_bytes(), placements

    # ── 템플릿 모드 ───────────────────────────────────────
    def _fill_template(
        self, template: bytes, values: Mapping[str, str], *, allow_bindata: bool = False
    ) -> bytes:
        from hwpx.package import HwpxPackage

        pkg = HwpxPackage.open(template)
        before = sorted(pkg.files())
        paragraph_slots = {self.slots.text[k] for k in self.slots.paragraphs}
        leftover: set[str] = set()
        for path in pkg.section_paths():
            xml = pkg.get_text(path)
            for ph, value in values.items():
                if ph in paragraph_slots:
                    xml = expand_paragraphs(xml, ph, value, bullet=self.slots.bullet)
                else:
                    xml = replace_inline(xml, ph, escape(value))  # 보안 F: escape 를 거쳐서만
            leftover |= set(_PLACEHOLDER.findall(xml)) & self.slots.placeholders()
            pkg.set_part(path, xml)
        if leftover:
            raise TemplateSlotUnfilled(
                "치환되지 않은 자리표시자(한 글자체로 다시 입력): " + ", ".join(sorted(leftover))
            )
        buf = io.BytesIO()
        pkg.save(buf)
        data = buf.getvalue()
        after = sorted(zipfile.ZipFile(io.BytesIO(data)).namelist())
        if after != before:
            raise RenderedXmlInvalid("템플릿 구조가 바뀌었습니다 — 출력을 거부합니다.")
        del allow_bindata  # 그림(BinData)은 _insert_figures 가 뒤에 더한다
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


# ── 템플릿 치환 (템플릿 모드) ─────────────────────────────
def _paragraph_bounds(xml: str, inner_idx: int, placeholder: str) -> tuple[int, int]:
    start = xml.rfind(_P_OPEN, 0, inner_idx)
    end = xml.find(_P_CLOSE, inner_idx)
    if start < 0 or end < 0:
        raise RenderedXmlInvalid(f"{placeholder} 단락 경계를 찾을 수 없습니다.")
    end += len(_P_CLOSE)
    para = xml[start:end]
    if para.count(_P_OPEN) != 1 or "<hp:tbl" in para:
        raise RenderedXmlInvalid(f"{placeholder} 단락 구조가 예상과 다릅니다 (표·중첩 단락).")
    return start, end


# ── [G] 그림 삽입 보조 ────────────────────────────────────
_MARKER_PREFIX = "\u200b[fig:"


def figure_marker(figure_id: str) -> str:
    """섹션 본문 마지막 줄에 넣는 표식 단락 — 치환 뒤 그림으로 바꾼다(영폭 공백으로 본문과 구분)."""
    safe = re.sub(r"[^a-z0-9_:-]", "", figure_id)
    return f"{_MARKER_PREFIX}{safe}]"


def _add_image(doc: Any, data: bytes, fmt: str) -> Any:
    media = getattr(doc, "media", None)
    if media is not None and hasattr(media, "add_image"):
        return media.add_image(data, fmt)
    return doc.add_image(data, fmt)


def _find_marker(doc: Any, marker: str) -> tuple[Any, Any] | None:
    """표식이 든 표 칸의 (cell, paragraph). 표 밖(생성 모드 본문)이면 (None, paragraph)."""
    for para in doc.paragraphs:
        for table in para.tables:
            for r in range(table.row_count):
                for c in range(table.column_count):
                    cell = _cell_or_none(table, r, c)
                    if cell is None or marker not in (getattr(cell, "text", "") or ""):
                        continue
                    for cp in cell.paragraphs:
                        if marker in (cp.text or ""):
                            return cell, cp
        if marker in (para.text or ""):
            return None, para
    return None


def _cell_or_none(table: Any, r: int, c: int) -> Any:
    try:
        return table.cell(r, c)
    except Exception:  # noqa: BLE001 — 병합 칸은 건너뛴다
        return None


def _insert_after(para: Any, texts: list[str]) -> None:
    """본문 단락 `para` 바로 뒤에 글 단락들을 끼워 넣는다 (같은 섹션, 서식은 단락 기본)."""
    section = para.section
    siblings = list(section.paragraphs)
    index = next((i for i, p in enumerate(siblings) if p.element is para.element), None)
    if index is None:
        for text in texts:
            section.add_paragraph(text)
        return
    made = []
    for text in texts:
        made.append(section.add_paragraph(text))  # 끝에 만든 뒤 자리로 복사
    section.insert_paragraphs(index + 1, made)
    for p in made:
        p.remove()


def _clear_paragraph(para: Any) -> None:
    if hasattr(para, "clear_text"):
        para.clear_text()
    else:
        para.set_text_preserving_runs("")


def _set_paragraph_text(para: Any, text: str) -> None:
    if hasattr(para, "set_text_preserving_runs"):
        para.set_text_preserving_runs(text)
    else:
        _clear_paragraph(para)
        para.add_run(text)


def replace_inline(xml: str, placeholder: str, escaped: str) -> str:
    """한 줄 칸: 자리표시자를 같은 run 안에서 바꾸고, 그 단락의 줄 배치 캐시를 지운다.

    escaped 는 이미 escape 를 거친 문자열. 값 안에 자리표시자 글자가 있어도 한 번만 처리한다.
    """
    pos = 0
    while (idx := xml.find(placeholder, pos)) >= 0:
        start, end = _paragraph_bounds(xml, idx, placeholder)
        para = _LINESEG.sub("", xml[start:end]).replace(placeholder, escaped)
        xml = xml[:start] + para + xml[end:]
        pos = start + len(para)
    return xml


def expand_paragraphs(
    xml: str, placeholder: str, value: str, *, bullet: str = DEFAULT_BULLET
) -> str:
    """자리표시자가 든 <hp:p> 를 문장(개행 구분)마다 하나씩 복제한다.

    복제 단락은 원본의 paraPr·charPr 을 그대로 가지고, 텍스트만 escape 한 문장으로 바뀐다
    (escape → 단락 생성 순서). 줄 배치 캐시(linesegarray)는 지운다 — 한/글이 다시 배치한다.
    값이 비면 자리표시자만 지운 빈 단락 하나를 남긴다.
    자리표시자 단락이 표(<hp:tbl>)를 품거나 단락 경계를 찾을 수 없으면 거부한다 — 구조를 추측해
    바꾸지 않는다.
    """
    lines = [ln.strip() for ln in value.split("\n") if ln.strip()]
    pos = 0  # 넣은 값 안에 자리표시자 글자가 있어도 다시 찾지 않는다 (무한 반복 방지)
    while (idx := xml.find(placeholder, pos)) >= 0:
        start, end = _paragraph_bounds(xml, idx, placeholder)
        para = _LINESEG.sub("", xml[start:end])  # 새 글자·새 위치 — 줄 배치 캐시는 버린다
        if lines:
            copies = "".join(para.replace(placeholder, escape(bullet + ln)) for ln in lines)
        else:
            copies = para.replace(placeholder, "")
        xml = xml[:start] + copies + xml[end:]
        pos = start + len(copies)
    return xml


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
