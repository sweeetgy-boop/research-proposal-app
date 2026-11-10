"""문제 정의 카드 (ADR 0065, 계약 docs/contracts/problem-card.md).

0단계 계약 — 레인은 고치지 않는다.

제안 입력(가제·현황·원인·한계·목표)을 AI 1회 호출로 진단하고 규칙으로 검증한 결과다. 유추 검색·
새로움 확인·장벽 점검·과제명 추천이 장소어가 아니라 '문제' 기준으로 돌게 하는 재료다.

- 항목마다 누가 채웠는지(`origin` ai|user)와 무엇에 기댔는지(`basis` 근거 있음 = 제안문에 있음 /
  추정 = AI 가 채움)를 갖는다. 근거가 없으면 비워 둘 수 있다(`value=""`). 사용자가 고친 항목
  (`origin="user"`)은 AI 가 덮어쓰지 않는다(ADR 0054 와 같은 원칙).
- 카드는 `ProposalRequest.problem_card` 로 다닌다. 양식·유사과제 판정·차단·기존 캐시 키
  (`search_text`·`keyword_cache_key`)에는 쓰지 않는다. 카드가 없으면(None) 모든 소비자는 종전 방식.
- 카드 글은 제안자 입력과 같은 신뢰 수준이지만 웹에서 되돌아오는 값이므로 서버가 길이·형식을
  다시 검증한다(이 모델). 프롬프트에 넣을 때는 다른 입력처럼 태그를 무력화한다.
- 개인정보(이름·연락처)는 넣지 않는다 — 진단 프롬프트 입력·저장 전 모두 `rules/privacy` 로 지운다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CARD_VERSION = 1

CardOrigin = Literal["ai", "user"]
CardBasis = Literal["근거 있음", "추정"]
BASIS_STATED: CardBasis = "근거 있음"  # 제안문에 있는 내용
BASIS_GUESSED: CardBasis = "추정"  # AI 가 채운 내용 — 보완 질문으로 확인

LadderLevel = Literal["구체", "일반화", "추상화"]
LADDER_LEVELS: tuple[LadderLevel, ...] = ("구체", "일반화", "추상화")

# 커네빈 문제 성격 — 단순(알려진 해법 적용)·난해(전문 분석으로 풀림)·복잡(인과 불명, 탐색·시범)
ProblemNature = Literal["단순", "난해", "복잡"]
ProjectMode = Literal["도입형", "실증형", "연구형"]

# 조건부 분석 신호 (1차는 기록만, 실행하지 않는다)
Signal = Literal[
    "broad_scope",  # 범위 넓음 → KT IS/IS NOT
    "unclear_cause",  # 원인 불명확·다수 → 특성요인도(4M+환경)
    "safety_failure",  # 안전·고장 → FMEA·RAMS 심각도
    "policy_service",  # 정책·서비스·이용자 → JTBD·HMW
    "few_analogies",  # 유추 결과 3건 미만 → 생체모방 기능 분류로 넓혀 재검색
]
SIGNALS: tuple[Signal, ...] = (
    "broad_scope",
    "unclear_cause",
    "safety_failure",
    "policy_service",
    "few_analogies",
)

# 분류 코드 확인 경로 — table(공식 코드표)·corpus(저장 특허·과제에 실제로 붙어 있는 코드)·
# kipris(KIPRIS 분류 검색 건수 ≥ 1)·unverified(확인 못 함 — 검색에 쓰지 않는다)
CodeVerified = Literal["table", "corpus", "kipris", "unverified"]
CodeKind = Literal["ipc", "science_class"]

# 화면 '핵심 문제' 카드 4줄 = function·cause·contradiction·codes. 수정 단위(항목 이름).
CardField = Literal[
    "function_ko",
    "function_en",
    "ladder",
    "terms",
    "cause",
    "contradiction",
    "ipc",
    "science_class",
    "facets",
    "nature",
]
CARD_FIELDS: tuple[CardField, ...] = (
    "function_ko",
    "function_en",
    "ladder",
    "terms",
    "cause",
    "contradiction",
    "ipc",
    "science_class",
    "facets",
    "nature",
)

# 수정된 항목 → 다시 계산할 것 (계약 4절). 값은 열거 문자열:
#   derive      영문 기능 문장·사다리·문제어를 AI 1회로 다시 만든다(그 항목이 user 가 아니면)
#   principles  TRIZ 발명 원리 번호·이름 재검증(규칙)
#   codes       분류 코드 확인(규칙·KIPRIS 건수)
#   checks      '확인 필요' 재판정(규칙)
#   analogy     유추 질의·검색·정렬 (다음 과제안 요청 때 새 카드로 돈다)
#   clarify     보완 질문의 카드 문장
#   plans_stale 이미 받은 과제안이 옛 카드 기준 — 화면이 [과제안 다시 만들기] 를 보인다
#               (자동 실행 없음)
Rerun = Literal["derive", "principles", "codes", "checks", "analogy", "clarify", "plans_stale"]
CARD_DEPENDENTS: dict[CardField, tuple[Rerun, ...]] = {
    "function_ko": ("derive", "analogy", "plans_stale"),
    "function_en": ("analogy", "plans_stale"),
    "ladder": ("analogy", "plans_stale"),
    "terms": ("analogy", "plans_stale"),
    "cause": ("checks", "clarify"),
    "contradiction": ("principles", "plans_stale"),
    "ipc": ("codes", "analogy", "plans_stale"),
    "science_class": ("codes",),
    "facets": (),
    "nature": (),
}

MAX_CARD_TEXT = 300
MAX_TERM = 30
MAX_TERMS = 8
MAX_CAUSES = 2  # 5 Whys 2단계까지
MAX_IPC = 3
MAX_SCIENCE_CLASS = 2
MAX_PRINCIPLES = 3
MAX_CODE = 24
TRIZ_PRINCIPLE_COUNT = 40

_BAD_CHARS = '<>"\r\n\t'


def _clean(value: str, limit: int) -> str:
    out = " ".join(str(value or "").translate({ord(c): " " for c in _BAD_CHARS}).split())
    return out[:limit]


class CardText(BaseModel):
    """카드의 글 한 칸. 비어 있을 수 있다(근거가 없어 비워 둠)."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(default="", max_length=MAX_CARD_TEXT)
    origin: CardOrigin = "ai"
    basis: CardBasis = BASIS_GUESSED
    # 사용자가 고치기 전 AI 값 (origin=user 일 때만 의미 — 수정 짝 기록·되돌리기용)
    ai_value: str = Field(default="", max_length=MAX_CARD_TEXT)
    # 분석끼리 어긋남(예: 제안자가 쓴 원인과 AI 근본 원인이 다름) → 화면 '확인 필요'
    needs_check: bool = False

    @field_validator("value", "ai_value", mode="before")
    @classmethod
    def _tidy(cls, v: object) -> str:
        return _clean(str(v or ""), MAX_CARD_TEXT)


class LadderStep(BaseModel):
    """추상화 사다리 한 단 — 유추 검색의 단별 질의가 된다."""

    model_config = ConfigDict(extra="forbid")

    level: LadderLevel
    text: str = Field(default="", max_length=MAX_CARD_TEXT)

    @field_validator("text", mode="before")
    @classmethod
    def _tidy(cls, v: object) -> str:
        return _clean(str(v or ""), MAX_CARD_TEXT)


def _terms(v: object) -> list[str]:
    out: list[str] = []
    for raw in v if isinstance(v, (list, tuple)) else []:
        term = _clean(str(raw or ""), MAX_TERM).lower()
        if len(term) >= 2 and term not in out:
            out.append(term)
    return out[:MAX_TERMS]


class ProblemTerms(BaseModel):
    """문제어 — 유추 최종 정렬의 '대상어 겹침' 판정과 공유 문제어 표시에 쓴다. 장소어는 넣지 않는다.

    objects: 문제를 일으키거나 다루는 대상. 구체 단과 **일반화 단의 대상어를 함께** 넣는다
      (비둘기 + 조류). 추상화 단의 말(유해동물 등 너무 넓은 말)은 넣지 않는다.
    actions: 작용·현상 낱말(퇴치·착좌·둥지). 이것만 겹친 자료는 대상어 겹침으로 보지 않는다.
    영문은 영문 자료(OpenAlex 등) 판정용 — 소문자, 낱말 앞부분 일치로 본다.
    """

    model_config = ConfigDict(extra="forbid")

    objects_ko: list[str] = Field(default_factory=list)
    actions_ko: list[str] = Field(default_factory=list)
    objects_en: list[str] = Field(default_factory=list)
    actions_en: list[str] = Field(default_factory=list)
    origin: CardOrigin = "ai"

    @field_validator("objects_ko", "actions_ko", "objects_en", "actions_en", mode="before")
    @classmethod
    def _tidy(cls, v: object) -> list[str]:
        return _terms(v)


class TrizPrinciple(BaseModel):
    """TRIZ 발명 원리 — 번호는 1~40, 이름은 고정 목록(domain/rules/triz)과 대조해 맞춘다."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=TRIZ_PRINCIPLE_COUNT)
    name: str = Field(default="", max_length=40)


class Contradiction(BaseModel):
    """모순 — 좋게 하려는 것 ↔ 그 때문에 나빠지는 것. 1차는 novel 갈래의 장벽·과제명에만 쓴다."""

    model_config = ConfigDict(extra="forbid")

    improve: str = Field(default="", max_length=MAX_CARD_TEXT)
    worsen: str = Field(default="", max_length=MAX_CARD_TEXT)
    principles: list[TrizPrinciple] = Field(default_factory=list, max_length=MAX_PRINCIPLES)
    origin: CardOrigin = "ai"
    basis: CardBasis = BASIS_GUESSED
    ai_improve: str = Field(default="", max_length=MAX_CARD_TEXT)
    ai_worsen: str = Field(default="", max_length=MAX_CARD_TEXT)

    @field_validator("improve", "worsen", "ai_improve", "ai_worsen", mode="before")
    @classmethod
    def _tidy(cls, v: object) -> str:
        return _clean(str(v or ""), MAX_CARD_TEXT)

    @property
    def filled(self) -> bool:
        return bool(self.improve and self.worsen)


class ClassCode(BaseModel):
    """분류 코드 후보 — verified 가 unverified 면 검색에 쓰지 않고 화면에 '확인 못 함' 으로 둔다."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE)
    label: str = Field(
        default="", max_length=80
    )  # 코드표·메타데이터의 이름. 없으면 빈 값(지어내지 않음)
    origin: CardOrigin = "ai"
    verified: CodeVerified = "unverified"
    count: int | None = Field(default=None, ge=0)  # 확인에 쓴 건수(저장 자료 또는 KIPRIS)

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, v: object) -> str:
        return _clean(str(v or ""), MAX_CODE).upper()

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, v: object) -> str:
        return _clean(str(v or ""), 80)


class Facets(BaseModel):
    """항목 나누기 — 현상 / 대상 / 장소 / 원인 / 피해 / 원하는 결과.

    place(장소)는 유추 질의·공유 문제어에서 **빼는** 말이다(예: 철도역사·승강장).
    """

    model_config = ConfigDict(extra="forbid")

    phenomenon: CardText = Field(default_factory=CardText)
    target: CardText = Field(default_factory=CardText)
    place: CardText = Field(default_factory=CardText)
    cause: CardText = Field(default_factory=CardText)
    harm: CardText = Field(default_factory=CardText)
    desired: CardText = Field(default_factory=CardText)


class Nature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProblemNature | None = None
    mode: ProjectMode | None = None
    origin: CardOrigin = "ai"


class ProblemCard(BaseModel):
    """문제 정의 카드 한 장."""

    model_config = ConfigDict(extra="forbid")

    version: int = CARD_VERSION
    facets: Facets = Field(default_factory=Facets)
    # 기능 문장(TRIZ 기능 분석: 대상 + 작용, 장소어 제외). 영문은 OpenAlex·영문 자료 검색용.
    function_ko: CardText = Field(default_factory=CardText)
    function_en: CardText = Field(default_factory=CardText)
    ladder: list[LadderStep] = Field(default_factory=list, max_length=len(LADDER_LEVELS))
    ladder_origin: CardOrigin = "ai"
    terms: ProblemTerms = Field(default_factory=ProblemTerms)
    contradiction: Contradiction = Field(default_factory=Contradiction)
    # 근본 원인(5 Whys 2단계까지). 화면 '원인' 줄은 첫 칸.
    causes: list[CardText] = Field(default_factory=list, max_length=MAX_CAUSES)
    ipc: list[ClassCode] = Field(default_factory=list, max_length=MAX_IPC)
    science_class: list[ClassCode] = Field(default_factory=list, max_length=MAX_SCIENCE_CLASS)
    nature: Nature = Field(default_factory=Nature)
    signals: list[Signal] = Field(default_factory=list)
    # 실행한 방법 이름(1차는 "core" 하나)과 '확인 필요' 사유 열거값(예: cause_mismatch)
    methods: list[str] = Field(default_factory=list, max_length=12)
    checks: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("ladder")
    @classmethod
    def _ladder_order(cls, v: list[LadderStep]) -> list[LadderStep]:
        """단마다 하나, 구체 → 일반화 → 추상화 순."""
        by_level = {s.level: s for s in v}
        return [by_level[lv] for lv in LADDER_LEVELS if lv in by_level]

    @field_validator("signals")
    @classmethod
    def _signals(cls, v: list[Signal]) -> list[Signal]:
        return [s for s in SIGNALS if s in v]

    def ladder_text(self, level: LadderLevel) -> str:
        return next((s.text for s in self.ladder if s.level == level), "")

    def user_fields(self) -> list[CardField]:
        """사용자가 고친 항목 — 재진단이 덮어쓰지 않는다."""
        out: list[CardField] = []
        if self.function_ko.origin == "user":
            out.append("function_ko")
        if self.function_en.origin == "user":
            out.append("function_en")
        if self.ladder_origin == "user":
            out.append("ladder")
        if self.terms.origin == "user":
            out.append("terms")
        if any(c.origin == "user" for c in self.causes) or self.facets.cause.origin == "user":
            out.append("cause")
        if self.contradiction.origin == "user":
            out.append("contradiction")
        if any(c.origin == "user" for c in self.ipc):
            out.append("ipc")
        if any(c.origin == "user" for c in self.science_class):
            out.append("science_class")
        if any(
            getattr(self.facets, name).origin == "user"
            for name in ("phenomenon", "target", "place", "harm", "desired")
        ):
            out.append("facets")
        if self.nature.origin == "user":
            out.append("nature")
        return out


# ── 설정 (config/problem_card.yaml) ─────────────────────────
class CardUse(BaseModel):
    """카드를 쓰는 곳별 스위치 — 맨 위 enabled 가 꺼져 있으면 모두 꺼진 것으로 본다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analogy_queries: bool = True  # 사다리 단별 질의 + 영문 기능 문장(OpenAlex)
    analogy_rank: bool = True  # 대상어 겹침 → 기능 문장 재순위 → 자료원당 상한
    contradiction: bool = True  # 모순·발명 원리 → novel 갈래 장벽·과제명
    kipris_class: bool = True  # 분류 코드 → KIPRIS 분류 검색
    clarify: bool = True  # 원인·추정 항목 → 보완 질문


class CardRank(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rerank_top: int = Field(default=30, ge=5, le=100)  # 재순위에 넘길 후보 수(유사도 순)
    per_source: int = Field(default=2, ge=1, le=5)  # 자료원당 우선 건수 — 모자라면 순위대로 채움
    # 자료원당 우선은 재순위 상위 이 범위 안에서만 — 범위 밖의 약한 다른 자료원 자료를 먼저 담지
    # 않는다(2026-11-10 악취 사례: 30위 밖 0.019 점 자료가 5번째로 들어옴)
    priority_window: int = Field(default=15, ge=5, le=100)
    # 자료원당 우선은 재순위 점수가 1위의 이 비율 이상인 자료에만 — 점수가 거의 0 인 다른 자료원
    # 자료를 자료원 몫으로 끌어오지 않는다(2026-11-10 실제 카드: 같은 무관 특허가 두 사례에 들어옴)
    priority_min_ratio: float = Field(default=0.25, ge=0, le=1)
    # 재순위 질의에 제안문 문제어 질의(종전 규칙)도 써서 높은 점수를 취한다 — 카드 기능 문장이
    # 좁게 잡혀도 직접 관련 자료가 밀리지 않게. 후보에도 그 질의의 검색 결과를 합친다
    with_request_query: bool = True
    # 제목에서 흔한 꼬리말을 뺀 낱말이 이 비율 이상 겹치면(짧은 쪽 기준) 같은 자료로 보고 순위 높은
    # 하나만 남긴다. 0 이면 끔. 2026-11-10 악취 사례: "악취 역류 차단 장치"·"하수구 악취 역류
    # 방지기"·"악취 역류 방지장치" 가 5건 중 3건
    dup_title_ratio: float = Field(default=0.6, ge=0, le=1)
    dup_title_suffixes: tuple[str, ...] = ("방지기", "장치", "시스템", "방법", "구조")
    # 약한 자료 제외 — 재순위 점수가 1위의 이 비율 미만이면 뺀다(절대값이 아니라 1위 대비).
    # 5건을 억지로 채우지 않는다. 0 이면 끔. 값과 근거는 docs/contracts/problem-card.md 4.3절
    weak_ratio: float = Field(default=0.15, ge=0, le=1)
    # 대상어가 제목에 나온 자료는 점수가 낮아도 남긴다(재순위 모델이 놓치는 직접 관련 자료 보호)
    weak_keep_title_object: bool = True
    require_object: bool = True  # 대상어(구체·일반화)가 겹친 자료만


class CardLearning(BaseModel):
    """누적 학습 — 모델 학습 없음. 1차는 수정 짝 저장과 **본인** 수정 예시만."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    store_edits: bool = True  # 수정 짝 저장(공용 계정 제외, test 줄은 표시)
    examples: bool = True  # 새 진단 지시문에 본인의 비슷한 수정 예시를 넣는다
    max_examples: int = Field(default=3, ge=0, le=5)
    example_min_similarity: float = Field(default=0.80, ge=0, le=1)
    # 변경 전후 의미 유사도가 이 값 이상이면 표현 다듬기로 보고 학습에서 뺀다
    polish_similarity: float = Field(default=0.95, ge=0, le=1)
    # 2차(사전 후보)용 — 1차는 값만 둔다
    candidate_min_count: int = Field(default=3, ge=1)
    candidate_min_users: int = Field(default=2, ge=1)
    per_user_cap: int = Field(default=5, ge=1)


class CardVerify(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ipc_corpus: bool = True  # 저장 특허에 실제로 붙어 있는 IPC 로 확인
    ipc_kipris: bool = True  # KIPRIS 분류 검색 건수로 확인(일일 상한 안에서, 코드별 캐시)
    code_table: bool = False  # 공식 코드표(내려받은 뒤 켠다)
    cache_days: int = Field(default=30, ge=0)


class CardReuseConfig(BaseModel):
    """같은 제안문의 카드 재사용·확인한 카드 고정 (계약 4.4절) — 부를 때마다 흔들리지 않게."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True  # 꺼지면 종전처럼 부를 때마다 AI 를 새로 부른다(고정도 하지 않는다)
    cache_days: int = Field(default=30, ge=0)  # 공용 캐시 보관 기간. 0 이면 공용 캐시 없음(고정만)


class ProblemCardConfig(BaseModel):
    """config/problem_card.yaml (ADR 0065). 파일이 없으면 기본값 = **꺼짐**."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    stage: str = "diagnose"  # llm.yaml stages 의 Argon 단계 이름
    local_stage: str = "clarify"  # 실패 때 로컬 단계
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)  # 넘으면 카드 없이 진행
    methods: dict[str, bool] = Field(default_factory=lambda: {"core": True})
    # 조건부 분석 — 1차는 신호만 기록한다(실행 스위치는 모두 false)
    conditional: dict[str, bool] = Field(default_factory=dict)
    use: CardUse = Field(default_factory=CardUse)
    rank: CardRank = Field(default_factory=CardRank)
    verify: CardVerify = Field(default_factory=CardVerify)
    learning: CardLearning = Field(default_factory=CardLearning)
    reuse: CardReuseConfig = Field(default_factory=CardReuseConfig)
    # 대상어 동의어 묶음 — 묶음 안의 말은 같은 대상어로 본다(대상어 겹침 판정). 띄어쓰기 차이
    # ("가속도센서" = "가속도 센서")는 목록 없이도 같게 본다
    object_synonyms: tuple[tuple[str, ...], ...] = ()
    # 저장 위치 덮어쓰기 — edits: 수정 짝 JSONL (기본 data/feedback/card_edits.jsonl),
    # cards: 카드 재사용 캐시 폴더 (기본 data/cache/problem_cards, 고정 카드는 그 아래 pinned/)
    paths: dict[str, str] = Field(default_factory=dict)

    def uses(self, name: str) -> bool:
        """그 쓰임새가 켜져 있는가 — 맨 위 스위치와 함께 본다."""
        return self.enabled and bool(getattr(self.use, name))
