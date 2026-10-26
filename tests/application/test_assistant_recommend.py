"""Agent 연결·run 복사·manifest·저장소·설정·조립 — 차별화 과제 추천 (LLM 없음)."""

from __future__ import annotations

from datetime import date

from rra.adapters.logging import check_manifest
from rra.adapters.runs import FileRunStore
from rra.domain.models import ProposalRequest, RecommendationResult
from tests.entrypoints.ui.fake_app import FakeRecommend, make_assistant
from tests.fakes import DeterministicEmbedding, InMemoryRunStore

REQ = ProposalRequest(
    current_state="궤도 틀림을 분기별로 측정함",
    root_cause="구간별 진행 속도가 다름",
    limitation="우선순위 근거가 없음",
    goal="궤도 틀림을 상시 감지함",
)


async def test_intake_recommends_automatically_once_and_logs_the_decision():
    assistant = make_assistant(blocking=True)
    res = await assistant.intake(REQ)
    assert res.recommendations is not None and len(res.recommendations.recommendations) == 2
    assert [d.tool for d in res.decisions if d.tool == "rra_recommend"] == ["rra_recommend"]
    rec_logs = [t for t in assistant.trace if t.tool == "rra_recommend"]
    assert (
        len(rec_logs) == 1
        and "추천 2건" in rec_logs[-1].summary
        and "gemini" in rec_logs[-1].summary
    )
    assert len(assistant.recommend_usecase.calls) == 1
    # 다시 받기 — 사용자 요청 (needs_human 행)
    again = await assistant.recommend(REQ, res.alerts, again=True)
    assert again is not None and len(assistant.recommend_usecase.calls) == 2
    assert "다시 받기" in assistant.trace[-1].condition


async def test_intake_with_auto_off_or_without_usecase_does_not_recommend():
    assistant = make_assistant(recommend_auto=False)
    res = await assistant.intake(REQ)
    assert res.recommendations is None and not assistant.recommend_usecase.calls
    assert any(d.tool == "rra_recommend" and d.needs_human for d in res.decisions)
    none = make_assistant(recommend=None)
    res = await none.intake(REQ)
    assert res.recommendations is None
    assert await none.recommend(REQ, res.alerts) is None and "건너뜀" in none.trace[-1].summary


async def test_zero_recommendations_log_the_reason():
    assistant = make_assistant(recommend=FakeRecommend(count=0))
    res = await assistant.intake(REQ)
    assert res.recommendations.recommendations == []
    assert (
        "추천 없음" in assistant.trace[-1].summary and "충분히 다름" in assistant.trace[-1].summary
    )


async def test_preview_then_proceed_copies_result_into_run_and_manifest():
    assistant = make_assistant()
    res = await assistant.intake(REQ)
    rec = res.recommendations.recommendations[1]
    new_req, preview = assistant.preview_recommendation(REQ, rec, 1)
    assert preview.index == 1 and new_req.title_hint == rec.title
    assert new_req.differentiation == rec.differentiation and REQ.title_hint == ""
    state = await assistant.proceed(
        new_req,
        res.alerts,
        acknowledged=True,
        recommendations=res.recommendations,
        chosen_recommendation=1,
    )
    await assistant.manager.wait(assistant.user, state.run_id)
    saved = assistant.manager.store.load_recommendations(assistant.user, state.run_id)
    assert [r["title"] for r in saved["recommendations"]] == [
        r.title for r in res.recommendations.recommendations
    ]
    manifests = [m for _, m in assistant.manager.run_log.records]
    rec_m = manifests[-1]["recommendations"]
    assert rec_m["chosen"] == 1 and rec_m["recommendations"] == 2 and rec_m["calls"] == 1
    assert "title" not in rec_m and "summary" not in str(rec_m)  # 본문은 manifest 에 없다
    for m in manifests:
        check_manifest(m)
    # 추천 없이 생성하면 recommendations.json 도 manifest 항목도 없다
    plain = await assistant.proceed(REQ, res.alerts, acknowledged=True)
    await assistant.manager.wait(assistant.user, plain.run_id)
    assert assistant.manager.store.load_recommendations(assistant.user, plain.run_id) is None
    assert [m for rid, m in assistant.manager.run_log.records if rid == plain.run_id][-1][
        "recommendations"
    ] is None


def test_manifest_rejects_unknown_recommendation_keys():
    import pytest

    base = {"run_id": "20260101000000-00000001", "status": "done"}
    check_manifest({**base, "recommendations": {"chosen": 0, "calls": 1}})
    with pytest.raises(ValueError, match="recommendations"):
        check_manifest({**base, "recommendations": {"title": "본문"}})


def test_recommendations_round_trip_in_file_and_memory_stores(tmp_path):
    store = FileRunStore(tmp_path / "runs")
    state = store.create("local", REQ, ["title"], "2026-10-27T00:00:00+00:00")
    assert store.load_recommendations("local", state.run_id) is None
    data = RecommendationResult(provider="gemini", calls=1).model_dump(mode="json")
    store.save_recommendations("local", state.run_id, data)
    assert store.load_recommendations("local", state.run_id) == data
    assert (tmp_path / "runs" / "local" / state.run_id / "recommendations.json").is_file()
    mem = InMemoryRunStore()
    s2 = mem.create("local", REQ, ["title"], "2026-10-27T00:00:00+00:00")
    assert mem.load_recommendations("local", s2.run_id) is None
    mem.save_recommendations("local", s2.run_id, data)
    assert mem.load_recommendations("local", s2.run_id) == data


def test_recommend_policy_and_stage_in_project_llm_yaml():
    from rra.config_loader import llm_config, recommend_policy
    from tests.test_composition import project_settings

    settings = project_settings()
    assert recommend_policy(settings) == {"auto": True}
    cfg = llm_config(settings, "recommend")
    assert cfg["provider"] == "gemini" and cfg["max_tokens"] == 3000


def test_build_recommender_uses_gemini_with_key_and_falls_back_without():
    from pydantic import SecretStr

    from rra.composition import build_recommender
    from tests.test_composition import project_settings

    repo = make_assistant().repo
    without = build_recommender(project_settings(gemini_api_key=None), repo=repo, llm=object())
    assert without.fallback_local is True and without.provider == "mlx"
    with_key = build_recommender(
        project_settings(gemini_api_key=SecretStr("k")), repo=repo, llm=object()
    )
    assert with_key.fallback_local is False and with_key.provider == "gemini"
    assert with_key.include_internal is True and callable(with_key.retrieve)


def test_file_store_today_is_not_used_by_recommendations(tmp_path):
    """recommendations.json 은 날짜·사용자 외 메타 없이 결과 그대로 — 개인정보 없음."""
    store = FileRunStore(tmp_path / "runs")
    state = store.create("local", REQ, ["title"], "2026-10-27T00:00:00+00:00")
    store.save_recommendations("local", state.run_id, {"recommendations": [], "calls": 0})
    text = (tmp_path / "runs" / "local" / state.run_id / "recommendations.json").read_text()
    assert "proposer" not in text and date.today().isoformat() not in text
    _ = DeterministicEmbedding  # 임베딩은 쓰지 않는다 (import 만 확인)
