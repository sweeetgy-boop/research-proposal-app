"""평가 문제 묶음 (ADR 0058, 계약 docs/contracts/eval-results.md §2·§3) — 레인 D.

문제 한 건 = 아이디어 입력(ProposalRequest 의 네 칸 + 가제) + 정답. 종류(kind)마다 정답과 지표가
다르다:
- reverse(역방향): DB 의 실제 과제를 제목 단어 없이 아이디어로 바꿔 쓴 것. `answers` = 원래 과제
  doc_id(연작·같은 제목 판은 여러 개). 지표 recall_at5.
- trap(함정): 과제 A 의 대상 × 과제 B 의 방법. 차단되면 오답. `answers` 는 A·B 의 doc_id(참고용).
- novel(새 영역): 철도 밖 주제 사전에서 뽑은 아이디어. recommend_mode == novel 이 정답.

문제 본문은 결과 파일(EvalResult)에 쓰지 않는다 — 문제 파일(`data/eval/sealed|practice`)에만 있고,
봉인 묶음은 600 권한·열람 금지(docs/eval-protocol.md). 개인정보 칸(이름·연락처·사번)은 문제에
들어가지 않는다 — 생성기는 제목·초록·본문만 읽는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rra.domain.models.request import ProposalRequest

ProblemKind = Literal["reverse", "trap", "novel"]
PROBLEM_KINDS: tuple[str, ...] = ("reverse", "trap", "novel")
KIND_LABELS: dict[str, str] = {"reverse": "역방향", "trap": "함정", "novel": "새 영역"}

IDEA_FIELDS: tuple[str, ...] = (
    "title_hint",
    "current_state",
    "root_cause",
    "limitation",
    "goal",
)


class EvalProblem(BaseModel):
    """문제 한 건. `request` 는 IDEA_FIELDS 만(그 밖의 칸은 비워 둔다)."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: ProblemKind
    request: dict[str, str]
    answers: list[str] = Field(default_factory=list)  # reverse: 정답 doc_id, trap: A·B doc_id
    sources: list[str] = Field(default_factory=list)  # 문제를 만든 자료원 (own·alio·ntis·topic)

    def to_request(self) -> ProposalRequest:
        return ProposalRequest(**{k: self.request.get(k, "") for k in IDEA_FIELDS})


class NovelTopic(BaseModel):
    """새 영역 문제의 재료 — 철도 밖 주제 하나 (config/eval.yaml novel_topics)."""

    model_config = ConfigDict(frozen=True)

    title_hint: str = ""
    current_state: str
    root_cause: str
    limitation: str
    goal: str


class ProblemMix(BaseModel):
    """종류별 비율 (합이 1 이 아니어도 비율로 나눈다)."""

    model_config = ConfigDict(frozen=True)

    reverse: float = Field(default=0.6, ge=0.0)
    trap: float = Field(default=0.25, ge=0.0)
    novel: float = Field(default=0.15, ge=0.0)

    def counts(self, n: int) -> dict[str, int]:
        """n 건을 비율대로 나눈다. 나머지는 reverse 에 더한다(정답이 있는 종류)."""
        total = self.reverse + self.trap + self.novel
        if n <= 0 or total <= 0:
            return {"reverse": 0, "trap": 0, "novel": 0}
        trap = int(n * self.trap / total)
        novel = int(n * self.novel / total)
        return {"reverse": n - trap - novel, "trap": trap, "novel": novel}


class ProblemSource(BaseModel):
    """문제 재료 자료원 (+ 허용 doc_type, 비면 전부)."""

    model_config = ConfigDict(frozen=True)

    source: str
    doc_types: tuple[str, ...] = ()


class L1Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    n: int = Field(default=120, ge=1)
    repeats: int = Field(default=3, ge=1)
    mix: ProblemMix = Field(default_factory=ProblemMix)
    sources: tuple[ProblemSource, ...] = (
        ProblemSource(source="own"),
        ProblemSource(source="alio"),
        ProblemSource(source="ntis", doc_types=("rnd_project",)),
    )
    min_text_chars: int = Field(default=150, ge=20)  # 이보다 짧은 과제는 재료로 쓰지 않는다
    with_recommend: bool = True  # 과제안까지 (지표 rec_zero_rate·novel_estimated_barrier_ratio)


class L0Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    problems: str = "tests/eval/l0_problems.jsonl"  # 고정 문제 (합성·공개 자료만)
    corpus: str = "tests/eval/l0_corpus.jsonl"  # 합성 코퍼스 (메모리 저장소)
    cache_dir: str = "tests/eval/l0_cache"  # LLM 응답 캐시 (프롬프트 sha256 → 응답)


class L2Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_ratio: float = Field(default=0.1, ge=0.0, le=1.0)  # 사람 확인 표본


class EvalSuiteConfig(BaseModel):
    """config/eval.yaml 전체."""

    model_config = ConfigDict(frozen=True)

    sealed_seed: int = 20261109
    daily_llm_calls: int = Field(default=150, ge=0)  # 평가용 Gemini 일일 상한 (운영 600 과 별도)
    l0: L0Config = Field(default_factory=L0Config)
    l1: L1Config = Field(default_factory=L1Config)
    l2: L2Config = Field(default_factory=L2Config)
    novel_topics: tuple[NovelTopic, ...] = ()
