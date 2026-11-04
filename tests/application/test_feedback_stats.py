"""평가 기록 집계 (ADR 0056 2026-11-04 덧붙임) — 규칙·유스케이스·과제안 측정 test 인자.

시험 계정 줄(`test: true`)은 기본 제외, include_test 면 포함. event·source 가 없는 옛 줄은 "없음",
열거값 밖은 "기타"(값은 내보내지 않는다). 측정 줄은 provider 별·로컬 대체 수·seconds 중앙값.
"""

from __future__ import annotations

from rra.application.ports import FeedbackReaderPort, JsonlRows
from rra.application.usecases.feedback_stats import FeedbackStats
from rra.domain.rules.feedback_stats import NONE_LABEL, OTHER_LABEL, choice_stats, metrics_stats
from tests.application.test_recommend_metrics import MemoryMetrics
from tests.application.test_recommend_projects import ALERTS, REQ, make, rec, reply

CHOICES = [
    {"event": "apply", "source": "user", "doc_id": "alio:1"},
    {"event": "generate", "source": "ai_prefill", "doc_id": "alio:2"},
    {"doc_id": "alio:3"},  # 옛 줄 (event·source 없음)
    {"event": "apply", "source": "user", "doc_id": "alio:4", "test": True},
    {"event": "generate", "source": "user", "doc_id": "alio:5", "test": True},
    {"event": "weird-<b>", "source": "누군가", "doc_id": "alio:6"},
]
METRICS = [
    {"provider": "gemini", "fallback_local": False, "seconds": 10.0},
    {"provider": "mlx", "fallback_local": True, "seconds": 30.0},
    {"provider": "gemini", "fallback_local": False, "seconds": 20.0},
    {"provider": "gemini", "fallback_local": False, "seconds": 99.0, "test": True},
    {"provider": None, "fallback_local": False, "seconds": "bad"},
]


def test_choice_stats_excludes_test_lines_by_default_and_counts_old_lines():
    s = choice_stats(CHOICES)
    assert (s.total, s.test_lines, s.include_test) == (4, 2, False)
    assert s.by_event == {"apply": 1, "generate": 1, OTHER_LABEL: 1, NONE_LABEL: 1}
    assert s.by_source == {"user": 1, "ai_prefill": 1, OTHER_LABEL: 1, NONE_LABEL: 1}
    s = choice_stats(CHOICES, include_test=True)
    assert (s.total, s.test_lines) == (6, 2)
    assert s.by_event["apply"] == 2 and s.by_event["generate"] == 2
    assert choice_stats([]).by_event == {"apply": 0, "generate": 0}
    # "test" 가 정확히 true 일 때만 시험 줄
    assert choice_stats([{"event": "apply", "test": "true"}]).test_lines == 0


def test_metrics_stats_provider_fallback_and_median():
    s = metrics_stats(METRICS)
    assert (s.total, s.test_lines) == (4, 1)
    assert s.by_provider == {"gemini": 2, "mlx": 1, NONE_LABEL: 1}
    assert s.fallback_local == 1 and s.median_seconds == 20.0
    s = metrics_stats(METRICS, include_test=True)
    assert s.total == 5 and s.by_provider["gemini"] == 3 and s.median_seconds == 25.0
    assert metrics_stats([]).median_seconds is None
    assert metrics_stats([{"provider": "x y <z>"}]).by_provider == {OTHER_LABEL: 1}


class FakeReader:
    def __init__(self, choices=None, metrics=None):
        self._c, self._m = choices, metrics

    def choice_rows(self) -> JsonlRows:
        if self._c is None:
            return JsonlRows()
        return JsonlRows(rows=tuple(self._c), found=True, unreadable=1)

    def metrics_rows(self) -> JsonlRows:
        if self._m is None:
            return JsonlRows()
        return JsonlRows(rows=tuple(self._m), found=True)


def test_usecase_lines_show_counts_only():
    reader = FakeReader(CHOICES, METRICS)
    assert isinstance(reader, FeedbackReaderPort)
    text = "\n".join(FeedbackStats(reader)().as_lines())
    assert "전체 줄: 6건, 시험 계정 줄: 2건 (제외), 센 줄: 4건" in text
    assert "읽지 못한 줄: 1건" in text
    assert "시점(event): apply 1, generate 1, 기타 1, 없음 1" in text
    assert "출처(source): user 1, ai_prefill 1, 기타 1, 없음 1" in text
    assert "전체 줄: 5건, 시험 계정 줄: 1건 (제외), 센 줄: 4건" in text
    assert "provider: gemini 2, mlx 1, 없음 1" in text
    assert "로컬 대체(fallback_local): 1건" in text and "seconds 중앙값: 20초" in text
    assert "--include-test" in text
    for leaked in ("alio:", "weird", "누군가", "<b>"):
        assert leaked not in text

    text = "\n".join(FeedbackStats(reader)(include_test=True).as_lines())
    assert "시험 계정 줄: 2건 (포함), 센 줄: 6건" in text and "센 줄: 5건" in text
    assert "--include-test" not in text

    empty = "\n".join(FeedbackStats(FakeReader())().as_lines())
    assert empty.count("파일 없음") == 2


async def test_recommend_usecase_marks_metrics_line_only_when_test_is_passed():
    uc, _, _ = make([reply([rec("운행 차량 가속도 기반 진행 속도 추정")])] * 2)
    uc.metrics = MemoryMetrics()
    await uc(REQ, ALERTS)
    await uc(REQ, ALERTS, test=True)
    plain, marked = uc.metrics.rows
    assert "test" not in plain and marked["test"] is True
    assert {k: v for k, v in marked.items() if k not in ("test", "seconds")} == {
        k: v for k, v in plain.items() if k != "seconds"
    }
