"""Q9 측정 유스케이스(EvaluateQuality) — 가짜 RunManager·precheck 로 지표·JSON·표를 검증한다."""

import json

from rra.application.usecases.evaluate import EvaluateQuality
from rra.domain.models import OverlapAlert
from rra.entrypoints.views import eval_markdown
from tests.application.test_run_manager_quality import REQ, build, reply


class FakePrecheck:
    def __init__(self, alerts=None):
        self.alerts = list(alerts or [])

    async def __call__(self, req):
        return list(self.alerts)


def alert(doc_id="own:1", blocking=True):
    return OverlapAlert(
        doc_id=doc_id, title="t", tier="own", similarity=0.9, blocking=blocking, keywords=[]
    )


async def test_evaluate_collects_version_review_citation_and_precheck_metrics():
    mgr, store, log = build(review=reply("A"))
    ev = EvaluateQuality(
        mgr,
        FakePrecheck([alert()]),
        label="all",
        pipeline=mgr.pipeline.model_dump(),
        model="qwen",
        review_model="argon",
        rss_sampler=lambda: 1234.5,
        expected={"01": ["own:1"]},
        clock=iter(range(0, 100, 1)).__next__,
    )
    result = await ev([("01", REQ)])
    assert result.label == "all" and result.max_rss_mb == 1234.5 and result.gemini_calls == 1
    (a,) = result.ideas
    assert a.status == "drafted" and a.v1_alerts >= 1 and a.v2_alerts is not None
    assert a.sentences_v1 == 5 and a.sentences_v2 == 6  # 추가 문장 1
    assert a.style_fixed == 2 and a.style_warnings >= 1 and a.outline_sections == 1
    assert a.cited_ids == 1 and a.paper_citations == 1 and a.irrelevant_citations == 0
    assert a.scores == {"필요성": 3} and a.applied == 2 and a.additions == 3
    assert a.additions_applied == 1 and a.checklist_coverage == 0.5
    assert a.candidates == {"method": "A"} and a.section_search
    assert a.precheck_alerts == 1 and a.precheck_hit is True and a.precheck_top == ["own:1"]
    assert "section:method" in a.step_seconds and a.seconds >= 0
    t = result.totals()
    assert t["ideas"] == 1 and t["score_sum"] == 3 and t["precheck_hits"] == 1
    assert t["precheck_known"] == 1 and t["checklist_coverage"] == 0.5
    data = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
    assert data["totals"]["sentences_v2"] == 6 and data["ideas"][0]["run_id"] == a.run_id
    text = eval_markdown([data], date="2026-10-27")
    assert "## 초안 품질 강화 비교 (2026-10-27)" in text and "| all |" in text
    assert "Q2 설계도" in text and "1/1" in text and "method:A" in text


async def test_evaluate_without_reviewer_reports_skipped_review_and_unknown_hits():
    mgr, store, log = build(review=None, answers=None)
    ev = EvaluateQuality(
        mgr, FakePrecheck([alert()]), label="none", pipeline={}, expected={"03": []}
    )
    (idea,) = (await ev([("03", REQ)])).ideas
    assert idea.review_status == "skipped" and idea.gemini_calls == 0 and idea.scores == {}
    assert idea.v2_alerts is None and idea.precheck_alerts == 1
    assert idea.precheck_hit is False  # 정답 "없음" 인데 알림이 났다
    text = eval_markdown([{"label": "none", "pipeline": {}, "ideas": [], "totals": {}}], date="d")
    assert "(없음)" in text
