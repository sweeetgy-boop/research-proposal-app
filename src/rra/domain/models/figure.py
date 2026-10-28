"""제안서 그림(인포그래픽) 명세·기록 — [G] 2026-10-28 (architecture §4.16, ADR 0029).

그림은 이미지 생성 AI(Nano Banana Pro)가 그리지만, **그릴 내용은 구조화된 명세(JSON)** 로만 정한다.
명세의 글자·수치는 초안 본문·제안자 입력·검증된 근거에 있는 것만 쓴다(rules/figures.validate_spec).
명세 → 템플릿 SVG 밑그림(기본 그림) → 참고 이미지로 Nano Banana Pro 1회 → 채택. 자동 검증은 없고
제안자가 카드에서 확인·수정한다(confirmed).

종류 8: concept(개념도) · process(추진 체계도) · schedule(간트) · stat_chart(수치 그래프) ·
comparison(차별성 비교) · roadmap(성과지표·활용 로드맵) · as_is_to_be(현재 → 연구 후, v2) ·
technique(분석 기법 인포그래픽 — SWOT·퓨 매트릭스·비용-편익 등 20종, v2 [11]).

v2(2026-10-28, ADR 0033): 기본 그림은 As-Is/To-Be 1 + 분석 기법 추천 0~2 (+ 검증 수치
그래프·일정표), 최대 4장. 개념도·체계도·로드맵은 [다른 그림 추가]에서만. 상자 글자는
`MAX_BOX`(1~2줄)로 줄인다.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

FigureKind = Literal[
    "concept",
    "process",
    "schedule",
    "stat_chart",
    "comparison",
    "roadmap",
    "as_is_to_be",
    "technique",
]
FIGURE_KINDS: tuple[str, ...] = (
    "concept",
    "process",
    "schedule",
    "stat_chart",
    "comparison",
    "roadmap",
    "as_is_to_be",
    "technique",
)
KIND_LABEL: dict[str, str] = {
    "concept": "연구 개념도",
    "process": "추진 체계도",
    "schedule": "추진 일정표",
    "stat_chart": "현황 수치 그래프",
    "comparison": "차별성 비교",
    "roadmap": "성과지표·활용 로드맵",
    "as_is_to_be": "As-Is / To-Be",
    "technique": "분석 기법",
}
# [23] 화면·버전 목록에 보이는 한국어 이름 (영문·내부 코드 없음). 분석 기법은 "분석 기법 그림 – <기법 이름>"
DISPLAY_NAME: dict[str, str] = {
    "concept": "연구 개념도",
    "process": "추진 체계도",
    "schedule": "추진 일정표",
    "stat_chart": "현황 수치 그래프",
    "comparison": "차별성 비교표",
    "roadmap": "성과지표·활용 로드맵",
    "as_is_to_be": "현재·연구 후 비교 그림",
    "technique": "분석 기법 그림",
}


def display_name(kind: str, technique_label: str | None = None) -> str:
    """그림 종류 → 화면 이름. 분석 기법은 기법 이름을 붙인다 ("분석 기법 그림 – SWOT 분석")."""
    base = DISPLAY_NAME.get(kind, "그림")
    if kind == "technique" and technique_label:
        return f"{base} – {technique_label}"
    return base


# 종류별 기본 섹션 (그림이 붙는 양식 칸). 같은 섹션에 여러 그림이 올 수 있다.
KIND_SECTION: dict[str, str] = {
    "concept": "objective",
    "process": "method",
    "schedule": "method",
    "stat_chart": "tech_importance",
    "comparison": "tech_importance",
    "roadmap": "expected_technology",
    # 양식에 "연구배경 및 필요성" 칸이 없다 — 현재 → 목표를 말하는 2-나 연구목적 (비면 2-가-(2),
    # rules)
    "as_is_to_be": "objective",
    "technique": "method",  # 기법별 칸은 config/figures/techniques.yaml section
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
# v2 [4] 상자 한 칸 글자 — 제안서에 넣었을 때 읽히는 1~2줄. 새 명세는 normalize 가 이 길이로 줄인다
MAX_BOX = 30

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


# ── v2 [3] As-Is / To-Be ─────────────────────────────────
AS_IS_TAGS: tuple[str, ...] = ("현황", "원인", "한계")
TO_BE_TAGS: tuple[str, ...] = ("목표", "해결 방안", "기대효과")
Box = Annotated[str, Field(min_length=1, max_length=MAX_BOX)]


class SideItem(BaseModel):
    tag: Label  # As-Is: 현황·원인·한계 / To-Be: 목표·해결 방안·기대효과 (rules 가 고정 라벨로 맞춤)
    text: Box


class AsIsToBeSpec(BaseModel):
    """현재(As-Is: 현황·원인·한계) → 연구 후(To-Be: 목표·해결 방안·기대효과), 쪽마다 3~4칸,
    가운데 화살표에 연구의 핵심 해결 방안 한 줄. 글자는 입력·초안에서만."""

    kind: Literal["as_is_to_be"] = "as_is_to_be"
    as_is: list[SideItem] = Field(min_length=3, max_length=4)
    to_be: list[SideItem] = Field(min_length=3, max_length=4)
    solution: Box


# ── v2 [11] 분석 기법 인포그래픽 ──────────────────────────────
PRELIM_NOTE = "제안 내용 기반 예비 평가"  # 판단 기반 등급(상·중·하, +/0/−)에 항상 붙는다
NEED_CALC = "산출 필요"  # 제안·근거에 수치가 없는 금액 칸
TechniqueFamily = Literal["qualitative", "evaluation", "economic"]
FAMILY_LABEL: dict[str, str] = {
    "qualitative": "정성 분석",
    "evaluation": "비교·평가",
    "economic": "경제성·확률",
}


class TechItem(BaseModel):
    """기법 항목 한 칸 — source 는 본문 문장 id(s:<섹션>:<n>)·근거 청크 id·input:<입력 칸>."""

    text: Box
    rating: str | None = Field(default=None, max_length=4)  # 정성: 상·중·하
    amount: str | None = Field(default=None, max_length=MAX_BOX)  # 경제성: 수치 또는 "산출 필요"
    source: str = Field(default="", max_length=200)


class TechGroup(BaseModel):
    name: Label  # 기법의 고정 묶음 이름 (강점·약점… / 비용·편익… / 시나리오 이름)
    items: list[TechItem] = Field(min_length=1, max_length=4)


class MatrixRow(BaseModel):
    """비교·평가 표 한 줄 — 평가 기준(또는 FMEA 고장 유형)과 열마다 평가 기호."""

    name: Box
    cells: list[str] = Field(min_length=1, max_length=5)  # +·0·− 또는 상·중·하
    source: str = Field(default="", max_length=200)


class TechniqueSpec(BaseModel):
    """분석 기법 결과 — 정성·경제성은 groups(묶음별 항목), 비교·평가는 columns×rows 표.
    technique 는 config/figures/techniques.yaml 의 key. note 는 항상 PRELIM_NOTE."""

    kind: Literal["technique"] = "technique"
    technique: str = Field(min_length=1, max_length=40)
    title: Label
    groups: list[TechGroup] = Field(default_factory=list, max_length=6)
    columns: list[Label] = Field(default_factory=list, max_length=5)
    rows: list[MatrixRow] = Field(default_factory=list, max_length=6)
    note: str = Field(default=PRELIM_NOTE, max_length=60)


FigureSpec = Annotated[
    ConceptSpec
    | ProcessSpec
    | ScheduleSpec
    | StatChartSpec
    | ComparisonSpec
    | RoadmapSpec
    | AsIsToBeSpec
    | TechniqueSpec,
    Field(discriminator="kind"),
]
SPEC_TYPES: dict[str, type[BaseModel]] = {
    "concept": ConceptSpec,
    "process": ProcessSpec,
    "schedule": ScheduleSpec,
    "stat_chart": StatChartSpec,
    "comparison": ComparisonSpec,
    "roadmap": RoadmapSpec,
    "as_is_to_be": AsIsToBeSpec,
    "technique": TechniqueSpec,
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


RecommendationStatus = Literal["pending", "accepted", "dismissed"]


class FigureRecommendation(BaseModel):
    """[11] 앱이 추천한 그림 — 카드 "추천" 배지·이유 한 줄. pending = 결정 전(제출 전 점검),
    accepted = [넣기 확정], dismissed = [필요 없음](제안서에서 빠지고 아래로 접힘, 다시 넣기
    가능)."""

    technique: str = Field(min_length=1, max_length=40)
    reason: str = Field(default="", max_length=120)  # LLM 출력(비신뢰) — 화면은 그대로 보여 준다
    status: RecommendationStatus = "pending"
    model: str | None = None  # 고른 모델 라벨 (Argon 먼저, 실패면 로컬)
    swapped_from: str | None = None  # [다른 기법으로 바꾸기] 전 기법
    at: str | None = None


class TechniqueOutcome(BaseModel):
    """[11] 마지막 기법 추천 결과 — 빈 결과도 사유를 남긴다 (RunState.figure_techniques).
    status: recommended | none(해당 없음) | failed(호출 실패) | filtered(규칙에 걸러짐) | off."""

    status: Literal["recommended", "none", "failed", "filtered", "off"] = "none"
    reason: str = Field(default="", max_length=200)  # 해당 없음 사유(모델 한 줄, 비신뢰) 또는 코드
    picks: list[str] = Field(default_factory=list, max_length=2)  # 추천한 기법 key
    dropped: list[str] = Field(default_factory=list, max_length=4)  # 걸러진 기법 key
    model: str | None = None
    at: str | None = None


TextMethod = Literal["svg", "ocr", "baseline"]


class FigureFit(BaseModel):
    """[23] 그림이 본문 폭에 맞게 들어가는가 — 그림 단계(draw)가 남기고 HWPX 삽입 때 다시 잰다
    (manifest `figure_fit`). 폭은 양식 본문 안쪽 폭, 높이는 비율로. 높이 상한은 쪽 높이의 1/3.
    min_text_pt 는 본문 폭으로 넣었을 때 그림 안 가장 작은 글자 크기(pt) — 밑그림은 SVG 글자 크기로
    계산(svg), Nano Banana 그림은 OCR 글자 상자 높이로 어림(ocr), OCR 을 못 쓰면 밑그림 값(baseline)."""

    width_mm: float = Field(ge=0)
    height_mm: float = Field(ge=0)
    ratio: str = Field(
        default="16:9", max_length=12
    )  # 고른 비율 (생성 API 비율과 다를 수 있다: 4:1)
    fits: bool = True  # 높이 ≤ 쪽 높이 1/3
    min_text_pt: float | None = None
    text_ok: bool = True  # min_text_pt ≥ 하한 (모르면 True)
    text_method: TextMethod = "svg"
    redraws: int = 0  # 넓은 비율·글자 줄이기로 다시 그린 횟수 (밑그림 + 그림)
    shortened: int = 0  # 글자 크기를 맞추려고 줄인 칸 수
    widened: bool = False  # 높이 상한 때문에 더 넓은 비율로 바꿨다


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
    recommendation: FigureRecommendation | None = None  # [11] 앱 추천 그림이면 (분석 기법)
    fit: FigureFit | None = None  # [23] 본문 폭 맞춤 (비율·높이·글자 크기)
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def undecided(self) -> bool:
        """[11] 추천 그림인데 [넣기 확정]·[필요 없음] 을 아직 고르지 않았다."""
        return self.recommendation is not None and self.recommendation.status == "pending"


class FigurePlacement(BaseModel):
    """HWPX 삽입 결과 — manifest 용 (본문 없음)."""

    id: str
    placement: Placement = "inline"
    number: int = 1  # "그림 n"
    bytes: int = 0
    fit: FigureFit | None = None  # [23] HWPX 에 넣은 실제 폭·높이·비율·글자 크기
