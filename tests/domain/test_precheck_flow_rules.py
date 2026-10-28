"""② 유사과제 흐름 순수 규칙 (2026-10-28 레인 A) — 일반어·핵심 키워드, reranker 중심 판정, 같은 제목
합치기, AI 같음 판정 해석, 제안자 선택·차단 해제·기록, 비교표 칸, 과제안 다듬기·버전."""

from __future__ import annotations

from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.idea_plan import IdeaVersion
from rra.domain.rules import comparison, idea_plan, same_judgment, similar_choice
from rra.domain.rules.keywords import KeywordRule, core_keyword_overlap, core_terms
from rra.domain.rules.overlap import RerankRule, judge

PILOT_GENERIC = ["부족", "정책", "상황", "인식", "필요한", "이용", "방치", "해결책", "마련"]


def _rule():
    return KeywordRule().with_extra_generic(PILOT_GENERIC)


def _doc(doc_id, title, body="", source="own", doc_type="rnd_project"):
    return Document(doc_id=doc_id, source=source, doc_type=doc_type, title=title, body=body)


def _alert(doc_id, title="과제", blocking=False, score=None, sim=0.86, **kw):
    return OverlapAlert(
        doc_id=doc_id,
        title=title,
        tier="own",
        similarity=sim,
        blocking=blocking,
        rerank_score=score,
        rule_blocking=blocking,
        **kw,
    )


# ── 일반어·핵심 키워드 ─────────────────────────────────────
def test_pilot_generic_words_do_not_count_and_core_keywords_must_overlap():
    rule = _rule()
    query = "폐 역사 이용 방안 마련이 필요한 상황 방치 인식이 부족 정책적 해결책"
    procurement = "해외 철도차량 조달정책 분석. 국내 상황과 인식이 부족하고 정책 마련이 필요한 상황"
    # 질의 토큰 전체로 세면 일반어 제외 뒤에도 남는 말이 거의 없다 — 핵심어로 세면 0
    assert core_keyword_overlap(query, ["폐철도역사 활용", "유휴 공간"], procurement, rule) == []
    station = "폐철도역사 유휴 공간을 지역 문화시설로 활용하는 방안"
    shared = core_keyword_overlap(query, ["폐철도역사 활용", "유휴 공간"], station, rule)
    assert shared == ["폐철도역사", "유휴", "공간"]
    assert core_terms(["궤도 틀림 상시 감지", "철도 연구"], rule) == [
        "궤도",
        "틀림",
        "상시",
        "감지",
    ]
    # 핵심어가 없으면 종전처럼 질의 키워드 전체
    assert core_keyword_overlap("궤도 틀림", [], "궤도 틀림 감지", rule) == ["궤도", "틀림"]


def test_reranker_score_is_the_decision_score_and_core_hits_need_one():
    rule = KeywordRule()
    same = _doc("own:1", "궤도 틀림 상시 감지", "궤도 틀림을 상시 감지함")
    other = _doc("own:2", "해외 조달정책 분석", "궤도 관련 내용 없음")
    hits = [(same, 0.84), (other, 0.86)]  # e5 는 무관한 쪽이 더 높다
    alerts = judge(
        hits,
        query="궤도 틀림 상시 감지",
        keywords=rule,
        scores={"own:1": 0.95, "own:2": 0.04},
        rerank=RerankRule(threshold=0.5),
        core_keywords=["궤도 틀림"],
    )
    by = {a.doc_id: a for a in alerts}
    assert by["own:1"].blocking and by["own:1"].rerank_score == 0.95
    assert not by["own:2"].blocking  # e5 0.86 ≥ own 0.80 이지만 reranker 0.04
    assert by["own:1"].rule_blocking is True and alerts[0].doc_id == "own:1"
    # 점수가 없으면 종전 e5 임계치
    (old,) = judge([(other, 0.86)], query="해외 조달정책 분석", keywords=rule)
    assert old.rerank_score is None and old.blocking


# ── 같은 제목 합치기 ──────────────────────────────────────
def test_same_title_rows_merge_into_one_row():
    rows = [
        _alert("ntis:1", "궤도 결함 고속 진단 및 실시간 분석", score=0.79, keywords=["궤도"]),
        _alert("own:9", "다른 과제", score=0.6),
        _alert("ntis:2", "궤도결함 고속 진단 및 실시간 분석 ", True, 0.8, keywords=["진단"]),
    ]
    out = similar_choice.merge_same_titles(rows)
    assert [a.doc_id for a in out] == ["ntis:1", "own:9"]
    assert out[0].merged_ids == ["ntis:2"] and out[0].blocking and out[0].rerank_score == 0.8
    assert out[0].keywords == ["궤도", "진단"]


# ── AI 같음 판정 ─────────────────────────────────────────
def test_verdicts_only_same_blocks_and_missing_keep_rule():
    alerts = [
        _alert("own:1", blocking=True, score=0.9),
        _alert("own:2", blocking=True, score=0.8),
        _alert("own:3"),
    ]
    ids = same_judgment.pick_for_judgment(alerts, 2)
    assert ids == ["own:1", "own:2"]
    parsed = same_judgment.parse_verdicts(
        {
            "items": [
                {"doc_id": "own:1", "verdict": "different", "reason": '일반어만 겹침 <doc id="x">'},
                {"doc_id": "own:9", "verdict": "same", "reason": "모르는 id"},
                {"doc_id": "own:3", "verdict": "같다", "reason": "보내지 않은 후보"},
            ]
        },
        ids,
    )
    assert set(parsed) == {"own:1"} and "<doc" not in parsed["own:1"][1]
    out = {a.doc_id: a for a in same_judgment.apply_verdicts(alerts, parsed, ids, "argon")}
    assert not out["own:1"].blocking and out["own:1"].judgment == "different"
    assert out["own:2"].blocking and out["own:2"].judgment_reason == same_judgment.NO_VERDICT_REASON
    assert not out["own:3"].blocking and out["own:3"].judged_by is None
    assert same_judgment.parse_verdicts({"items": "x"}, ids) is None
    assert same_judgment.parse_verdicts(None, ids) is None


def test_rule_fallback_marks_rows_as_rule_judged():
    out = same_judgment.rule_fallback([_alert("own:1", blocking=True), _alert("own:2")])
    assert [(a.judged_by, a.blocking) for a in out] == [("rule", True), ("rule", False)]


# ── 제안자 선택 ──────────────────────────────────────────
def test_all_blocking_rows_unrelated_releases_the_block_and_records():
    alerts = [_alert("own:1", "가", True, 0.9), _alert("own:2", "나", False, 0.7)]
    choices = {"own:1": "unrelated", "own:2": "similar"}
    shown, released = similar_choice.apply_choices(alerts, choices)
    assert released and not any(a.blocking for a in shown)
    assert not similar_choice.effective_blocking(alerts, choices)
    assert similar_choice.effective_blocking(alerts, {"own:2": "similar"})
    assert [a.doc_id for a in similar_choice.similar_alerts(alerts, choices)] == ["own:2"]
    recs = similar_choice.choice_records(
        alerts, choices, idea=similar_choice.idea_hash("궤도"), at="t", released=released
    )
    assert [(r["doc_id"], r["choice"], r["released"]) for r in recs] == [
        ("own:1", "unrelated", True),
        ("own:2", "similar", True),
    ]
    assert len(recs[0]["idea"]) == 16 and "가" not in str(recs)  # 제목·본문 없음


def test_rows_for_writing_keep_only_similar_as_overlap_targets():
    alerts = [_alert("own:1", blocking=True), _alert("own:2"), _alert("own:3", blocking=True)]
    rows = similar_choice.rows_for_writing(alerts, {"own:1": "unrelated", "own:2": "similar"})
    assert [(a.doc_id, a.blocking) for a in rows] == [("own:2", True), ("own:3", False)]
    assert similar_choice.rows_for_writing(alerts, {}) == alerts
    assert similar_choice.missing_similar_ids(rows, {"own:7": "similar"}) == ["own:7"]


def test_request_choices_validate_and_stay_out_of_prompts():
    req = ProposalRequest(
        current_state="a",
        root_cause="b",
        limitation="c",
        goal="d",
        method="센서 분석",
        similar_choices=[{"doc_id": " own:1 ", "choice": "similar"}],
    )
    assert req.choice_map() == {"own:1": "similar"}
    assert "similar_choices" not in req.prompt_view() and req.prompt_view()["method"] == "센서 분석"
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProposalRequest(
            current_state="a",
            root_cause="b",
            limitation="c",
            goal="d",
            similar_choices=[{"doc_id": '<doc id="x">', "choice": "similar"}],
        )


# ── 비교표 칸 ────────────────────────────────────────────
def test_proposal_row_uses_title_and_method_inputs_not_limitation():
    req = ProposalRequest(
        current_state="a",
        root_cause="b",
        limitation="현행 한계 문장",
        goal="진행 속도 추정",
        title_hint="궤도 열화 예측",
        method="검측 이력 분석",
        scope="경부선",
    )
    col = comparison.proposal_column(req)
    assert col.title == "궤도 열화 예측"
    assert col.cells["method"] == "검측 이력 분석" and col.cells["scope"] == "경부선"
    assert "현행 한계" not in str(col.cells)
    bare = comparison.proposal_column(req.model_copy(update={"title_hint": "", "method": ""}))
    assert bare.title == comparison.PROPOSAL_NO_TITLE
    assert bare.cells["method"] == comparison.PROPOSAL_NO_METHOD
    drafted = comparison.proposal_column(req, draft={"title": "초안 과제명", "method": "초안 방법"})
    assert drafted.title == "초안 과제명" and drafted.cells["method"] == "초안 방법"


def test_rule_cells_drop_symbols_and_never_cut_mid_sentence():
    body = "■ 연구목적: ◦ 궤도 상태를 자동으로 감지함. 점검 비용을 줄임. 셋째 문장임."
    cells = comparison.rule_cells(body)
    assert cells["objective"] == "궤도 상태를 자동으로 감지함. 점검 비용을 줄임."
    assert cells["scope"] == comparison.NO_INFO
    assert comparison.tidy_sentence("1. 350km/h급 궤도 결함 진단") == "350km/h급 궤도 결함 진단"
    assert comparison.tidy_sentence("(2) ◦ 전차선 감시") == "전차선 감시"
    long = ["가" * 50 + " " + "나" * 500]
    assert comparison.clean_cell(long).endswith("…") and len(comparison.clean_cell(long)) < 410


def test_llm_cell_must_come_from_source_text():
    src = "경부선 고속철도 구간의 궤도 틀림을 검측차로 측정함. 보수 주기를 정함."
    assert comparison.cell_from_llm("경부선 고속철도 구간의 궤도 틀림을 측정함", src)
    assert comparison.cell_from_llm("", src) == ""
    assert comparison.cell_from_llm("비용을 37% 줄임", src) is None  # 원문에 없는 수치
    assert comparison.cell_from_llm("인공지능 드론으로 교량을 촬영함", src) is None  # 원문 밖
    assert comparison.cell_from_llm("軌道 측정", src) is None


# ── 과제안 다듬기·버전 ───────────────────────────────────
def test_polish_validation_and_version_normalization():
    allowed = ["검측 이력 기반 보수 우선순위 산정"]
    text, reason = idea_plan.validate_polish(
        "goal", "검측 이력으로 보수 우선순위를 산정함", allowed
    )
    assert text and reason is None
    assert idea_plan.validate_polish("goal", "비용 30% 절감", allowed)[1] == idea_plan.POLISH_NUMBER
    assert idea_plan.validate_polish("goal", "", allowed)[1] == idea_plan.POLISH_EMPTY
    out = idea_plan.normalize_versions(
        [
            IdeaVersion(kind="original", fields={"goal": "목표", "secret": "x"}),
            IdeaVersion(kind="edited", fields={"goal": "연락 010-1234-5678 목표"}),
        ]
    )
    assert out[0]["fields"] == {"goal": "목표"}
    assert "010-1234-5678" not in str(out)
