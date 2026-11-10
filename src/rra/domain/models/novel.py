"""새 과제 추천 갈래 (ADR 0057, 계약 docs/contracts/novel-recommend.md).

② 과제안은 두 갈래다. [유사함] 0건(ADR 0054 한 규칙)이고 차단도 없으면 `novel`,
아니면 `differentiate`(종전 차별화 과제안). 판정은 `usecases/similar_rows.recommend_mode` 한 곳.

novel 결과는 `RecommendationResult` 의 `mode="novel"`·`coverage`·`analogies`·`novel` 칸에
담기고, 차별화 카드 칸(`recommendations`)은 비어 있다. LLM 출력은 검증을 통과한 값만
들어온다(비신뢰 텍스트).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecommendMode = Literal["differentiate", "novel"]
MODE_DIFFERENTIATE: RecommendMode = "differentiate"
MODE_NOVEL: RecommendMode = "novel"

BarrierType = Literal["수요", "규제", "비용", "기술", "운영"]
BARRIER_TYPES: tuple[BarrierType, ...] = ("수요", "규제", "비용", "기술", "운영")
BasisLevel = Literal["근거 있음", "추정"]
BASIS_EVIDENCED: BasisLevel = "근거 있음"
BASIS_ESTIMATED: BasisLevel = "추정"
Maturity = Literal["즉시 적용", "실증 필요", "연구 필요"]
MATURITIES: tuple[Maturity, ...] = ("즉시 적용", "실증 필요", "연구 필요")
StageName = Literal["기획", "시범", "확대"]
STAGE_NAMES: tuple[StageName, ...] = ("기획", "시범", "확대")

MAX_NOVEL = 3  # 안 2~3건
MAX_ANALOGIES = 5
MAX_BARRIERS = 5  # 갈래마다 하나까지
MAX_TITLES = 3
MAX_NOVEL_CHARS = 600
MAX_NOVEL_TITLE_CHARS = 200
COVERAGE_NOTE = "저장 자료와 실시간 검색 범위 안에서 기존 과제 없음"


class NoveltyCoverage(BaseModel):
    """새로움 확인 범위 — 실제로 확인한 자료원만(확인 안 한 자료원은 넣지 않는다)."""

    searched: list[str] = Field(default_factory=list)  # 자료원 코드 (예: scienceon, openalex, own)
    searched_labels: list[str] = Field(default_factory=list)  # 화면 이름 (searched 와 같은 순서)
    live: bool = False  # 실시간 검색을 실제로 했다(한 자료원이라도 응답)
    # 실시간 검색을 하지 못한 자료원과 사유 열거값 — {"source": "ntis", "status": "ip_blocked"}
    unavailable: list[dict[str, str]] = Field(default_factory=list)
    note: str = COVERAGE_NOTE


class Analogy(BaseModel):
    """다른 분야 사례 한 건 (유추 검색, 최대 5). domain_label 은 자료원 메타데이터에서만."""

    doc_id: str
    title: str  # 수집 문서 제목 (비신뢰)
    source: str = ""
    source_label: str = ""
    domain_label: str  # 분야 — 메타데이터(학술지 분야·분류 코드·자료원 분류)에서, 지어내지 않는다
    why_relevant: str  # 왜 참고가 되는지 — 공유하는 '문제' 축 단어 등 규칙으로 만든 문장
    url: str | None = None
    year: int | None = None
    live: bool = False  # 실시간 검색에서 찾은 자료
    similarity: float | None = None


AnalogyKind = Literal["other_field", "related"]
ANALOGY_OTHER_FIELD: AnalogyKind = "other_field"  # 철도 밖 사례 (종전)
ANALOGY_RELATED: AnalogyKind = "related"  # 대상이 철도 시설 — 철도 자료 포함 '관련 선행 자료'


class AnalogyReport(BaseModel):
    """유추 검색 보고 (ADR 0065, 문제 정의 카드 경로에서만) — 무엇을 어디까지 찾았는가.

    자료가 없거나 적을 때 '없는 것'과 '못 찾은 것'을 구분해 보이기 위한 값이다. 문장은 진입점이
    만든다(`views`). 카드를 쓰지 않은 유추에는 보고가 없다(None) — 화면은 종전 그대로."""

    kind: AnalogyKind = ANALOGY_OTHER_FIELD
    rail_basis: list[str] = Field(default_factory=list)  # 철도 시설 과제로 본 근거 낱말(기록용)
    count: int = 0  # 최종 건수
    candidates: int = 0  # 종전 규칙(하한·같은 제목)을 지난 후보 수
    dropped_weak: int = 0  # 관련이 약해 뺀 수(재순위 점수 기준)
    dropped_similar: int = 0  # 제목이 겹쳐 뺀 수
    # 확인 범위 — NoveltyCoverage 와 같은 뜻(실제로 확인한 자료원만)
    searched: list[str] = Field(default_factory=list)
    unavailable: list[dict[str, str]] = Field(default_factory=list)  # {source, status}
    sources_total: int = 0
    languages: list[str] = Field(default_factory=lambda: ["한국어", "영어"])

    @property
    def partial(self) -> bool:
        """응답하지 않은 자료원이 있다 — '없음'이 아니라 '일부만 확인'."""
        return bool(self.unavailable)


class BarrierBasis(BaseModel):
    level: BasisLevel
    doc_ids: list[str] = Field(default_factory=list)  # level=근거 있음 이면 1개 이상, 입력 구획 안


class Barrier(BaseModel):
    """'왜 아직 아무도 안 했나' 장벽 하나."""

    type: BarrierType
    statement: str = Field(min_length=1, max_length=MAX_NOVEL_CHARS)
    basis: BarrierBasis
    check: str = Field(default="", max_length=MAX_NOVEL_CHARS)  # 확인 방법 (추정이면 필수)


class NovelTitle(BaseModel):
    """장벽 해소형 과제명 — resolves 는 같은 안의 barriers 인덱스(0부터), 1개 이상."""

    title: str = Field(min_length=1, max_length=MAX_NOVEL_TITLE_CHARS)
    resolves: list[int] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=MAX_NOVEL_CHARS)
    # ADR 0065 — 이 과제명이 기댄 TRIZ 발명 원리 번호(1~40). 문제 정의 카드의 모순에 붙은 원리
    # 안에서만(그 밖의 번호는 검증이 뺀다). 카드가 없으면 늘 비어 있다.
    principles: list[int] = Field(default_factory=list, max_length=3)


class NovelStage(BaseModel):
    stage: StageName
    text: str = Field(min_length=1, max_length=MAX_NOVEL_CHARS)


class NovelRecommendation(BaseModel):
    """새 과제안 하나 (검증 통과분)."""

    approach: str = Field(min_length=1, max_length=MAX_NOVEL_CHARS)  # 접근 방식 한 줄
    summary: str = Field(min_length=1, max_length=MAX_NOVEL_CHARS)
    first_step: str = Field(default="", max_length=MAX_NOVEL_CHARS)
    stages: list[NovelStage] = Field(default_factory=list, max_length=3)  # 기획 → 시범 → 확대
    maturity: Maturity
    evidence: list[str] = Field(default_factory=list)  # doc_id — 입력 구획 안
    barriers: list[Barrier] = Field(default_factory=list, max_length=MAX_BARRIERS)
    titles: list[NovelTitle] = Field(min_length=1, max_length=MAX_TITLES)
    # 근거 문서 제목·자료원 (화면은 내부 번호 대신 이것을 보인다) — RecommendationRef 와 같은 모양
    refs: list[dict[str, str]] = Field(default_factory=list)
