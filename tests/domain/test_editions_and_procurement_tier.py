"""P2-10 판 추적 확인(모호하면 둘 다 현행 + 기록) · P2-6 발주 용역 티어."""

from rra.domain.models import Document
from rra.domain.rules.editions import mark_editions, valid_until_of
from rra.domain.rules.overlap import (
    DEFAULT_THRESHOLDS,
    STATUS_LABELS,
    judge,
    no_overlap_statement,
    tier_label,
    tier_of,
    uncollected_sources,
)


def test_editions_ambiguous_when_latest_date_unknown_keeps_both_current():
    out = mark_editions(
        [
            {"id": "a", "title": "제3차 철도산업발전기본계획", "posted": "2016-06-20"},
            {"id": "b", "title": "제4차 철도산업발전기본계획", "posted": None},
        ]
    )
    assert out[0]["edition"] == {
        "family": "철도산업발전기본계획",
        "no": 3,
        "status": "현행",
        "superseded_by": 4,
        "ambiguous": True,
    }
    assert out[1]["edition"]["status"] == "현행" and valid_until_of(out[0]) is None


def test_editions_same_number_twice_both_current():
    out = mark_editions(
        [
            {"id": "a", "title": "제4차 국가철도망 구축계획(본문)", "posted": "2021-07-05"},
            {"id": "b", "title": "제4차 국가철도망 구축계획(별첨)", "posted": "2021-07-05"},
            {"id": "c", "title": "제3차 국가철도망 구축계획", "posted": "2016-06-20"},
        ]
    )
    assert out[0]["edition"]["status"] == out[1]["edition"]["status"] == "현행"
    assert (
        out[2]["edition"]["status"] == "구판" and out[2]["edition"]["valid_until"] == "2021-07-05"
    )


def _proc(doc_id="g2b:1-00", status="procuring"):
    return Document(
        doc_id=doc_id,
        source="g2b",
        doc_type="procurement",
        title="궤도 기하 열화 예측 모델 개발 연구용역",
        body="궤도 기하 열화 예측 모델 개발 연구용역 공고",
        orgs=["korail"],
        raw={"status": status},
    )


def test_procurement_tier_threshold_and_alert_status():
    doc = _proc()
    assert tier_of(doc) == "procurement" and DEFAULT_THRESHOLDS["procurement"] == 0.80
    assert tier_label("procurement") == "발주 용역"
    alerts = judge([(doc, 0.81)], query="궤도 기하 열화 예측 모델")
    assert (
        alerts[0].tier == "procurement" and alerts[0].blocking and alerts[0].status == "procuring"
    )
    assert STATUS_LABELS[alerts[0].status] == "용역으로 진행 중/예정"
    assert not judge([(doc, 0.79)], query="궤도 기하 열화")[0].blocking


def test_statement_lists_procurement_criterion_and_uncollected_g2b():
    texts = no_overlap_statement({"own": 3}, ["g2b"])
    assert "발주 용역 0.80" in texts[-1]
    assert "나라장터 발주 용역 공고" in texts[1]
    assert "g2b" in uncollected_sources({"own": 1})
    assert "bai" not in uncollected_sources({}) and "datago" not in uncollected_sources({})
