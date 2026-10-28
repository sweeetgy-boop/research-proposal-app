"""제안서 그림(인포그래픽) 명세·기록 — [G] 2026-10-28 (architecture §4.16, ADR 0029).

그림은 이미지 생성 AI(Nano Banana Pro)가 그리지만, **그릴 내용은 구조화된 명세(JSON)** 로만 정한다.
명세의 글자·수치는 초안 본문·제안자 입력·검증된 근거에 있는 것만 쓴다(rules/figures.validate_spec).
명세 → 템플릿 SVG 밑그림(기본 그림) → 참고 이미지로 Nano Banana Pro 1회 → 채택. 자동 검증은 없고
제안자가 카드에서 확인·수정한다(confirmed).

종류 6: concept(개념도) · process(추진 체계도) · schedule(간트) · stat_chart(수치 그래프) ·
comparison(차별성 비교) · roadmap(성과지표·활용 로드맵).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

FigureKind = Literal["concept", "process", "schedule", "stat_chart", "comparison", "roadmap"]
FIGURE_KINDS: tuple[str, ...] = (
    "concept",
    "process",
    "schedule",
    "stat_chart",
    "comparison",
    "roadmap",
)
KIND_LABEL: dict[str, str] = {
    "concept": "연구 개념도",
    "process": "추진 체계도",
    "schedule": "추진 일정표",
    "stat_chart": "현황 수치 그래프",
    "comparison": "차별성 비교",
    "roadmap": "성과지표·활용 로드맵",
}
# 종류별 기본 섹션 (그림이 붙는 양식 칸). 같은 섹션에 여러 그림이 올 수 있다.
KIND_SECTION: dict[str, str] = {
    "concept": "objective",
    "process": "method",
    "schedule": "method",
    "stat_chart": "tech_importance",
    "comparison": "tech_importance",
    "roadmap": "expected_technology",
}
FigureRenderer = Literal["nano_banana", "baseline"]
Placement = Literal["inline", "appendix"]

MAX_LABEL = 40
MAX_LINE = 60
MAX_CAPTION = 120
MAX_EDIT_REQUEST = 500
MAX_EDIT_HISTORY = 20
MAX_CHANGE_LINES = 8
MAX_CHANGE_LINE = 160

Label = Annotated[str, Field(min_length=1, max_length=MAX_LABEL)]
Line = Annotated[str, Field(min_length=1, max_length=MAX_LINE)]


# ── 종류별 명세 ──────────────────────────────────────────
class ConceptBox(BaseModel):
    label: Label  # 상자 제목 (현황·문제·해결 방안·기대효과)
    lines: list[Line] = Field(default_factory=list, max_length=2)


class ConceptSpec(BaseModel):
    """개념도 — 현황 → 문제(근본 원인) → 해결 방안 → 기대효과, 상자 4개."""

    kind: Literal["concept"] = "concept"
    boxes: list[ConceptBox] = Field(min_length=4, max_length=4)


class ProcessStage(BaseModel):
    name: Label
    outputs: list[Line] = Field(default_factory=list, max_length=3)  # 주요 산출물


class ProcessSpec(BaseModel):
    """추진 체계도 — 단계 3~6개 상자와 화살표, 단계마다 산출물."""

    kind: Literal["process"] = "process"
    stages: list[ProcessStage] = Field(min_length=3, max_length=6)


class ScheduleStage(BaseModel):
    name: Label
    start_month: int = Field(ge=1, le=120)
    end_month: int = Field(ge=1, le=120)

    @field_validator("end_month")
    @classmethod
    def _end_after_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start_month")
        if start is not None and v < start:
            raise ValueError("end_month 가 start_month 보다 앞섭니다.")
        return v


class ScheduleSpec(BaseModel):
    """추진 일정표(간트) — U6 단계별 개월. total_months 는 연구기간(제약)에서."""

    kind: Literal["schedule"] = "schedule"
    total_months: int = Field(ge=1, le=120)
    stages: list[ScheduleStage] = Field(min_length=2, max_length=8)


class ChartSeries(BaseModel):
    name: Label
    values: list[float] = Field(min_length=1, max_length=12)


class FactSource(BaseModel):
    """출처 캡션 — "출처: 문서명, 연도, 쪽". stat_chart 는 필수."""

    doc_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=200)
    year: int | None = Field(default=None, ge=1900, le=2100)
    page: int | None = Field(default=None, ge=1)

    def caption(self) -> str:
        parts = [self.title or self.doc_id]
        if self.year:
            parts.append(f"{self.year}년")
        if self.page:
            parts.append(f"{self.page}쪽")
        return "출처: " + ", ".join(parts)


class StatChartSpec(BaseModel):
    """현황 수치 그래프 — 검증된 table_facts 값만. 값마다 value_texts(표기 그대로)를 함께 둔다."""

    kind: Literal["stat_chart"] = "stat_chart"
    chart: Literal["bar", "line"] = "bar"
    title: Label
    categories: list[Label] = Field(min_length=1, max_length=12)  # 가로축 (연도·구분)
    series: list[ChartSeries] = Field(min_length=1, max_length=4)
    unit: str = Field(default="", max_length=20)
    value_texts: list[str] = Field(default_factory=list, max_length=48)  # 표기 그대로 ("1,512")
    source: FactSource

    @field_validator("series")
    @classmethod
    def _same_length(cls, v: list[ChartSeries], info: Any) -> list[ChartSeries]:
        n = len(info.data.get("categories") or [])
        for s in v:
            if n and len(s.values) != n:
                raise ValueError("series.values 길이가 categories 와 다릅니다.")
        return v


class ComparisonProject(BaseModel):
    title: str = Field(min_length=1, max_length=80)  # 기존 과제명 (비신뢰)
    cells: dict[str, str] = Field(default_factory=dict)  # aspect → 글 ("정보 없음" 허용)


class ComparisonSpec(BaseModel):
    """차별성 비교 — U4 비교표에서 기존 과제 2~3건 대 제안 과제 (연구목표·방법·적용범위)."""

    kind: Literal["comparison"] = "comparison"
    aspects: list[Label] = Field(min_length=1, max_length=5)  # 행 이름
    projects: list[ComparisonProject] = Field(min_length=1, max_length=3)
    proposal: ComparisonProject


class RoadmapMetric(BaseModel):
    name: Label
    target: Line  # 목표치. 없으면 "목표치 확인 필요"


class RoadmapStage(BaseModel):
    name: Label
    desc: Line | None = None


class RoadmapSpec(BaseModel):
    """성과지표·활용 로드맵 — 기대효과의 성과지표와 활용 단계."""

    kind: Literal["roadmap"] = "roadmap"
    metrics: list[RoadmapMetric] = Field(min_length=1, max_length=6)
    stages: list[RoadmapStage] = Field(min_length=2, max_length=5)


FigureSpec = Annotated[
    ConceptSpec | ProcessSpec | ScheduleSpec | StatChartSpec | ComparisonSpec | RoadmapSpec,
    Field(discriminator="kind"),
]
SPEC_TYPES: dict[str, type[BaseModel]] = {
    "concept": ConceptSpec,
    "process": ProcessSpec,
    "schedule": ScheduleSpec,
    "stat_chart": StatChartSpec,
    "comparison": ComparisonSpec,
    "roadmap": RoadmapSpec,
}


def parse_spec(kind: str, data: Any) -> BaseModel:
    """종류에 맞는 Spec 으로 검증. kind 가 섞여 들어와도 인자 kind 를 따른다."""
    model = SPEC_TYPES[kind]
    payload = dict(data) if isinstance(data, dict) else {}
    payload["kind"] = kind
    return model.model_validate(payload)


# ── 그림 기록 ─────────────────────────────────────────────
class EditRequestRecord(BaseModel):
    """[말로 고치기] 요청 원문 — 개인정보 규칙(privacy)으로 정리한 뒤 저장."""

    text: str = Field(max_length=MAX_EDIT_REQUEST)
    at: str | None = None
    ok: bool = True  # 호출 성공 여부


ChangeKind = Literal["content", "style"]


class FigureChange(BaseModel):
    """마지막 [말로 고치기]·[글자 고치기] 결과 — 카드 "바뀐 내용" (2026-10-28 [2]).
    content = 명세(글자·단계·순서)가 바뀌어 밑그림부터 새로 그림,
    style = 명세 그대로 모양만 다시 그림. style 칸은 그림 프롬프트에 붙인 모양 요청."""

    kind: ChangeKind = "content"
    summary: list[Annotated[str, Field(max_length=MAX_CHANGE_LINE)]] = Field(
        default_factory=list, max_length=MAX_CHANGE_LINES
    )
    style: str = Field(default="", max_length=MAX_EDIT_REQUEST)
    model: str | None = None  # 요청 → 명세 변경을 쓴 모델 (argon·local 라벨). 글자 고치기는 None
    at: str | None = None


class Figure(BaseModel):
    id: str  # "f:<section>:<n>"
    kind: FigureKind
    section: str
    caption: str = Field(default="", max_length=MAX_CAPTION)  # "그림 n." 은 렌더 때 붙인다
    alt: str = Field(default="", max_length=600)  # 대체 텍스트 (명세에서 자동)
    spec: FigureSpec
    renderer: FigureRenderer = "baseline"  # 채택된 그림이 무엇인지
    model: str | None = None  # nano_banana 일 때 모델명
    calls: int = 0  # 이 그림에 쓴 Nano Banana 호출 수 (생성·말로 고치기·다시 만들기)
    included: bool = True  # False 면 제안서에서 뺀 것 (다시 넣기 가능)
    confirmed: bool = False  # 제안자 [확인함]. 고치면 다시 False
    internal: bool = False  # 명세 글자·수치가 internal 근거에서 왔는가 (공용 계정이면 제외)
    source_caption: str = Field(default="", max_length=MAX_CAPTION)  # stat_chart "출처: …"
    image_sha: str | None = None  # 채택 그림 파일 해시 (run figures/<id>.png)
    baseline_sha: str | None = None  # 밑그림 파일 해시 (figures/<id>.baseline.png)
    error: str | None = None  # Nano Banana 실패 사유 코드 (budget·http·timeout…)
    edit_requests: list[EditRequestRecord] = Field(
        default_factory=list, max_length=MAX_EDIT_HISTORY
    )
    spec_model: str | None = None  # 명세를 쓴 모델 라벨 (Argon 먼저, 실패면 로컬 — [2])
    last_change: FigureChange | None = None  # 마지막 명세·모양 변경 요약 (버전이 바뀌어도 이어진다)
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)


class FigurePlacement(BaseModel):
    """HWPX 삽입 결과 — manifest 용 (본문 없음)."""

    id: str
    placement: Placement = "inline"
    number: int = 1  # "그림 n"
    bytes: int = 0
