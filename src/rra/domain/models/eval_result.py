"""평가 결과 형식 (ADR 0058, 계약 docs/contracts/eval-results.md) — 0단계 계약 모델.

`eval/results/<날짜>-<단계>.json` 한 파일 = `EvalResult` 하나. 레인 D(평가 체계)가 쓰고,
`rra eval compare` 와 2차 비교 평가(가·나·다)가 읽는다. 지표는 비율·초·건수만 — 문제 본문·과제명·
doc_id·사용자 식별자는 넣지 않는다(보안 D). 시험용 봉인 묶음(seed 고정)의 문제 본문은 결과 파일에도
쓰지 않는다 — 수치만.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvalSuite = Literal["l0", "l1", "l2"]
SUITES: tuple[str, ...] = ("l0", "l1", "l2")
SUITE_LABELS: dict[str, str] = {
    "l0": "L0 PR 마다 — 검색·판정만, LLM 응답 캐시 재생",
    "l1": "L1 매일 밤 — 자동 생성 문제 100건 이상, 3회 평균",
    "l2": "L2 배포 전·주 1회 — 골든셋 10건 + 초안, 사람 확인 표본 10%",
}

# 지표 이름 (계약 고정 — 바꾸려면 계약 파일부터). 값은 모두 숫자(비율 0~1, 초, 건수)
METRIC_KEYS: tuple[str, ...] = (
    "recall_at5",  # 역방향 문제: 정답 과제가 ② 상위 5행 안에 든 비율
    "false_block",  # 함정 문제·새 영역 문제: 차단된 비율 (낮을수록 좋다)
    "novel_rate",  # 새 영역 문제: novel 갈래로 간 비율
    "novel_estimated_barrier_ratio",  # novel 과제안의 '추정' 장벽 비율
    "latency_p50",  # ② 표 + 판정(+ 과제안) 벽시계 초, 중앙값
    "latency_p90",
    "rec_zero_rate",  # 과제안 0건으로 끝난 비율
)


class CI95(BaseModel):
    """95% 신뢰구간 [low, high] — 같은 문제 3회 평균(AI 흔들림)을 반영. n 이 작아 못 구하면 None."""

    model_config = ConfigDict(frozen=True)

    low: float | None = None
    high: float | None = None


class EvalMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_at5: float | None = None
    false_block: float | None = None
    novel_rate: float | None = None
    novel_estimated_barrier_ratio: float | None = None
    latency_p50: float | None = None
    latency_p90: float | None = None
    rec_zero_rate: float | None = None


class ProblemRecord(BaseModel):
    """문제 한 건의 결과 요약 — 짝 비교(같은 묶음을 두 구성으로 돌린 뒤 문제별 맞힘 대조,
    McNemar)용. `id` 는 문제 해시(본문·doc_id 아님). `correct` 는 종류별 정답 기준(역방향 = 상위 5
    적중, 함정 = 차단 안 됨, 새 영역 = novel 갈래)이고 반복이 여러 번이면 과반. 2026-11-09 보완."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str  # reverse | trap | novel
    correct: bool | None = None  # 판정 불가(종류 밖)면 None
    runs: int = Field(default=1, ge=1)
    correct_runs: int = Field(default=0, ge=0)
    blocked: bool = False  # 마지막 실행 기준
    seconds: float = 0.0  # 실행 평균 초


class EvalResult(BaseModel):
    """한 번의 평가 실행. `config_flags` 는 비교에 뜻이 있는 스위치만(facets·idf_weighting·synonyms·
    judgment 등 — 열거값·불리언·숫자만, 경로·키 금지). `label` 은 비교표의 열 이름(가·나·다 …).
    `problems` 는 문제별 요약(선택) — 두 결과가 같은 문제 id 를 가지면 `rra eval compare` 가 짝
    비교를 낸다."""

    model_config = ConfigDict(frozen=True)

    suite: EvalSuite
    seed: int
    n: int = Field(ge=0)  # 문제 수 (반복 횟수를 곱하지 않은 수)
    repeats: int = Field(default=1, ge=1)  # 같은 문제 반복 횟수 (L1 기본 3)
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)
    ci95: dict[str, CI95] = Field(default_factory=dict)  # 지표 이름 → 구간
    config_flags: dict[str, bool | int | float | str] = Field(default_factory=dict)
    label: str = ""
    commit: str = ""  # 짧은 해시 (비밀 없음)
    started_at: str = ""  # ISO 초 단위, 지역 시각
    seconds: float = 0.0  # 전체 벽시계
    sealed: bool = False  # 시험용 봉인 묶음으로 돌렸는가 (문제 본문은 결과에 없다)
    llm_calls: int = 0  # 외부(Gemini) 호출 수 — 일일 상한 안에서만
    cache_hits: int = 0  # L0 캐시 재생 수
    notes: list[str] = Field(default_factory=list)  # 짧은 메모(문제 본문 금지)
    problems: list[ProblemRecord] = Field(default_factory=list)  # 문제별 요약 (짝 비교용, 선택)
