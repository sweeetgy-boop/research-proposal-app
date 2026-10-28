"""② v3 (2026-10-28 밤 레인 A, ADR 0039) — 표 먼저·판정 칸·기본 선택·진행 중 판정 합류·취소·제한
시간 없음,
카드 겹침 재판정(한 번 다시 받기·경고 문구·정렬)·[더 만들기] 중복 제거. FakeLLM 만 (임베딩·LLM
호출 없음)."""

from __future__ import annotations

import asyncio
import json

import pytest

from rra.application.usecases.card_overlap import CARD_JUDGE_HEAD, CardOverlapCheck
from rra.application.usecases.judge_sameness import SameJudge
from rra.application.usecases.polish_field import PolishField
from rra.application.usecases.recommend_projects import RecommendProjects
from rra.domain.models import OverlapAlert, ProposalRequest, RetrievalSnapshot
from rra.domain.rules.card_overlap import CardCheck, closeness, difference_level, warning_fields
from rra.domain.rules.precheck_levels import basis_alerts, default_choices, level_view
from tests.application.test_precheck_flow_usecases import IDEA, _precheck, _repo, verdicts
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository


class SlowLLM:
    """첫 호출을 gate 가 열릴 때까지 붙잡는다 — 느린 Argon. cancelled 는 취소됐는지."""

    def __init__(self, answer: str):
        self.answer = answer
        self.gate = asyncio.Event()
        self.calls = 0
        self.cancelled = False

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        self.calls += 1
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.answer


ANSWER = verdicts(
    ("own:station", "same", "폐역사 유휴 공간 활용으로 같음"),
    ("alio:proc", "partial", "철도 정책이라는 점만 같음"),
    ("ntis:tunnel", "different", "터널 진동으로 대상이 다름"),
)


# ── 표 먼저 → AI 판정 ────────────────────────────────────
async def test_table_first_then_judgment_maps_levels_and_default_choices():
    llm = FakeLLM([ANSWER])
    pre = _precheck(_repo(), SameJudge(primary=llm, repo=_repo()))
    rule = await pre.rule_stage(IDEA, remember=True)
    assert rule.judgment.status == "off" and not llm.calls  # 표는 LLM 없이
    views = {a.doc_id: level_view(a) for a in rule.alerts}
    assert views["own:station"]["level_label"] == "차단"
    assert {v["level_basis_label"] for v in views.values()} == {"규칙 기준"}
    assert await pre(IDEA) == rule.alerts  # 후속 경로는 판정 전 메모(규칙)

    judged = await pre.judgment(IDEA)
    assert judged.judgment.status == "ai" and len(llm.calls) == 1
    labels = {a.doc_id: level_view(a)["level_label"] for a in judged.alerts}
    assert labels == {"own:station": "차단", "alio:proc": "근접", "ntis:tunnel": "관련 낮음"}
    assert {level_view(a)["level_basis"] for a in judged.alerts} == {"ai"}
    assert default_choices(judged.alerts) == {"ntis:tunnel": "unrelated"}
    again = await pre.judgment(IDEA)  # 메모 — 다시 부르지 않는다
    assert again.judgment.status == "ai" and len(llm.calls) == 1


async def test_judgment_and_current_share_one_inflight_call():
    slow = SlowLLM(ANSWER)
    pre = _precheck(_repo(), SameJudge(primary=slow, repo=_repo()))
    await pre.rule_stage(IDEA, remember=True)
    cards_side = asyncio.ensure_future(pre.current(IDEA))  # 과제안 요청이 먼저 와도
    screen_side = asyncio.ensure_future(pre.judgment(IDEA))
    await asyncio.sleep(0.01)
    slow.gate.set()
    a, b = await asyncio.gather(cards_side, screen_side)
    assert slow.calls == 1  # 판정은 한 번
    assert a.judgment.status == b.judgment.status == "ai"


async def test_slow_argon_is_awaited_not_replaced_by_local():
    """제한 시간 없음 — 느린 Argon 은 오류가 아니다(로컬로 넘어가지 않는다)."""
    slow = SlowLLM(ANSWER)
    local = FakeLLM([verdicts(("own:station", "partial", "로컬"))])
    pre = _precheck(_repo(), SameJudge(primary=slow, local=local, repo=_repo()))
    task = asyncio.ensure_future(pre.run(IDEA))
    for _ in range(5):
        await asyncio.sleep(0.02)  # 옛 제한 시간이 있었다면 여기서 로컬로
    assert not task.done() and not local.calls
    slow.gate.set()
    result = await task
    assert result.judgment.judged_by == "argon" and not local.calls
    assert not hasattr(SameJudge(), "timeout")


async def test_cancel_of_only_waiter_stops_the_job():
    slow = SlowLLM(ANSWER)
    pre = _precheck(_repo(), SameJudge(primary=slow, repo=_repo()))
    await pre.rule_stage(IDEA, remember=True)
    task = asyncio.ensure_future(pre.judgment(IDEA))
    await asyncio.sleep(0.01)
    task.cancel()  # 화면 [취소] → REST 가 코루틴을 취소
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.01)
    assert slow.cancelled  # 작업도 멈췄다
    memo = pre.memo(IDEA)  # 메모(규칙 판정)는 그대로 — 화면은 이전 상태
    assert memo is not None and memo.judgment.status == "off"


async def test_cancel_of_one_waiter_keeps_job_for_the_other():
    slow = SlowLLM(ANSWER)
    pre = _precheck(_repo(), SameJudge(primary=slow, repo=_repo()))
    await pre.rule_stage(IDEA, remember=True)
    screen_side = asyncio.ensure_future(pre.judgment(IDEA))
    await asyncio.sleep(0.01)
    cards_side = asyncio.ensure_future(pre.current(IDEA))
    await asyncio.sleep(0.01)
    screen_side.cancel()
    await asyncio.sleep(0.01)
    assert not slow.cancelled
    slow.gate.set()
    assert (await cards_side).judgment.status == "ai"


def test_basis_alerts_use_similar_rows_or_drop_unrelated_and_unchosen_different():
    rows = [
        OverlapAlert(
            doc_id="a", title="A", tier="own", similarity=0.8, blocking=True, judgment="same"
        ),
        OverlapAlert(
            doc_id="b", title="B", tier="own", similarity=0.8, blocking=False, judgment="partial"
        ),
        OverlapAlert(
            doc_id="c", title="C", tier="own", similarity=0.8, blocking=False, judgment="different"
        ),
    ]
    assert [a.doc_id for a in basis_alerts(rows, {})] == ["a", "b"]
    assert [a.doc_id for a in basis_alerts(rows, {"b": "unrelated", "c": "similar"})] == ["c"]
    assert [a.doc_id for a in basis_alerts(rows, {"a": "unrelated"})] == ["b"]


# ── 카드 겹침 재판정 ─────────────────────────────────────
REQ = ProposalRequest(
    current_state="수송수요를 해마다 예측함",
    root_cause="신설역 개통 효과를 반영하지 못함",
    limitation="월별 변동을 다루지 않음",
    goal="신설역 개통과 월별 계절성을 반영한 수송수요 예측 모형",
)


def _alert(doc_id, title, score, blocking=True):
    return OverlapAlert(
        doc_id=doc_id,
        title=title,
        tier="own",
        similarity=0.86,
        blocking=blocking,
        rule_blocking=blocking,
        rerank_score=score,
    )


def _card(title, summary):
    return {
        "title": title,
        "summary": summary,
        "goal": summary,
        "method": "수송 실적을 분석함",
        "scope": "광역철도",
        "differentiation": "기존 과제는 연간 예측에 그침",
        "reasons": [],
        "compared_with": ["own:demand"],
        "evidence": ["own:demand"],
    }


def _reply(*cards):
    return json.dumps({"recommendations": list(cards)}, ensure_ascii=False)


def _card_verdicts(*rows):
    return json.dumps(
        {"items": [{"card": c, "doc_id": d, "verdict": v, "reason": r} for c, d, v, r in rows]},
        ensure_ascii=False,
    )


class Probe:
    """카드 글 → 규칙 판정 대역. '기상' 이 든 카드는 기상 수요 과제와 규칙에 걸린다."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    async def __call__(self, req, core):
        self.calls.append((req.title_hint, list(core)))
        if "기상" in req.search_text():
            return [_alert("own:weather", "기상 반영 수송수요 예측", 0.92)]
        if "신설역" in req.search_text():
            return [_alert("own:demand", "연도별 수송수요 예측", 0.55, blocking=False)]
        return []


def _recommender(main: list[str], judge: list[str]):
    from rra.domain.models import Document

    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id="own:demand",
                source="own",
                doc_type="rnd_project",
                title="연도별 수송수요 예측",
                abstract=(
                    "연도별 수송수요 예측 모형 수송 실적 분석 광역철도 신설역 개통 월별 계절성 기상"
                ),
            ),
            Document(
                doc_id="own:weather",
                source="own",
                doc_type="rnd_project",
                title="기상 반영 수송수요 예측",
                abstract="기상 변수를 넣은 수송수요 예측 모형",
            ),
        ],
        [],
    )

    async def retrieve(req):
        return RetrievalSnapshot.of(req.search_text(), [])

    probe = Probe()
    judge_llm = FakeLLM(list(judge))
    check = CardOverlapCheck(probe=probe, primary=judge_llm, repo=repo)
    llm = FakeLLM(list(main))
    uc = RecommendProjects(
        llm,
        FakePromptLibrary(),
        repo,
        precheck=None,  # type: ignore[arg-type] — 카드 겹침 재판정이 대신한다
        retrieve=retrieve,
        card_check=check,
    )
    alerts = [_alert("own:demand", "연도별 수송수요 예측", 0.6)]
    return uc, llm, judge_llm, probe, alerts


async def test_overlapping_card_is_regenerated_once_before_shown_and_sorted():
    weather = _card("기상 변수 반영 수송수요 예측", "기상 변수를 넣어 수송수요를 예측함")
    month = _card("신설역 개통 초기 월별 수요 보정", "신설역 개통 초기 월별 수요를 보정함")
    fixed = _card("광역철도 월별 계절성 분해 모형", "월별 계절성을 분해해 수요를 봄")
    uc, llm, judge, probe, alerts = _recommender(
        [_reply(weather, month), _reply(fixed)],
        [
            _card_verdicts(("c1", "own:weather", "same", "둘 다 기상 변수를 넣은 수요 예측 모형")),
        ],
    )
    out = await uc(REQ, alerts, similar_only=True, core_keywords=["수송수요"])
    titles = [r.title for r in out.recommendations]
    # 겹친 '기상' 카드만 다시 받았고(한 번), 다시 받은 안은 규칙에 걸리지 않아 판정 없이 통과
    assert "기상 변수 반영 수송수요 예측" not in titles
    assert (
        "광역철도 월별 계절성 분해 모형" in titles
        and out.overlap_regenerated == out.overlap_found == 1
    )
    regen = next(r for r in out.recommendations if r.regenerated)
    assert regen.title == "광역철도 월별 계절성 분해 모형" and not regen.overlap_warning
    assert "[겹침을 피해 다시 쓸 안]" in llm.calls[1] and "기상 반영 수송수요 예측" in llm.calls[1]
    assert (
        len(llm.calls) == 2 and len(judge.calls) == 1
    )  # 다시 받은 안은 규칙 후보가 없어 판정 생략
    assert judge.calls[0].startswith(CARD_JUDGE_HEAD)
    assert all(core == ["수송수요"] for _, core in probe.calls)  # 아이디어 핵심어로 같은 기준
    # 정렬: 가까움 낮은(가장 다른) 안부터 — 규칙 후보 없는 계절성 안(0) < 신설역 안(0.55×0.5)
    assert [r.title for r in out.recommendations] == [
        "광역철도 월별 계절성 분해 모형",
        "신설역 개통 초기 월별 수요 보정",
    ]
    assert out.recommendations[0].refs[0].title == "연도별 수송수요 예측"  # 근거는 제목으로


async def test_still_overlapping_card_shows_titles_and_judge_reason():
    weather = _card("기상 변수 반영 수송수요 예측", "기상 변수를 넣어 수송수요를 예측함")
    weather2 = _card("기상 예보 연계 수송수요 예측", "기상 예보를 넣어 수송수요를 예측함")
    uc, llm, judge, _, alerts = _recommender(
        [_reply(weather), _reply(weather2)],
        [
            _card_verdicts(("c1", "own:weather", "same", "둘 다 기상 변수를 넣은 수요 예측 모형")),
            _card_verdicts(("c1", "own:weather", "same", "")),  # 이유 없음 → 제목만
        ],
    )
    out = await uc(REQ, alerts, similar_only=True)
    (card,) = out.recommendations
    assert card.regenerated and card.title == "기상 예보 연계 수송수요 예측"
    assert card.overlap_warning == ["own:weather"]
    assert card.overlap_titles == ["기상 반영 수송수요 예측"]
    assert card.overlap_reason == ""  # 판정이 이유를 주지 않으면 지어내지 않는다
    assert card.difference == "low" and card.overlap_by == "argon"


def test_warning_fields_use_judge_reason_and_rule_fallback_has_no_reason():
    cand = [_alert("own:weather", "기상 반영 수송수요 예측", 0.9)]
    ai = CardCheck(
        candidates=cand,
        verdicts={"own:weather": ("same", "둘 다 기상 변수를 넣은 수요 예측 모형")},
        by="argon",
    )
    w = warning_fields(ai)
    assert w["overlap_titles"] == ["기상 반영 수송수요 예측"]
    assert w["overlap_reason"] == "둘 다 기상 변수를 넣은 수요 예측 모형"
    assert closeness(ai) == pytest.approx(1.9) and difference_level(ai) == "low"
    rule = CardCheck(candidates=cand, by="rule")
    assert (
        warning_fields(rule)["overlap_reason"] == ""
        and warning_fields(rule)["overlap_by"] == "rule"
    )
    partial = CardCheck(candidates=cand, verdicts={"own:weather": ("partial", "x")}, by="argon")
    assert not warning_fields(partial)["overlap_warning"] and difference_level(partial) == "mid"


async def test_more_cards_skip_ones_already_shown():
    shown_card = _card("신설역 개통 초기 월별 수요 보정", "신설역 개통 초기 월별 수요를 보정함")
    new_card = _card("광역철도 월별 계절성 분해 모형", "월별 계절성을 분해해 수요를 봄")
    uc, llm, _, _, alerts = _recommender([_reply(shown_card)], [])
    first = await uc(REQ, alerts, similar_only=True)
    uc2, llm2, _, _, _ = _recommender([_reply(shown_card, new_card)], [])
    more = await uc2(REQ, alerts, similar_only=True, shown=list(first.recommendations))
    assert [r.title for r in more.recommendations] == ["광역철도 월별 계절성 분해 모형"]
    assert any(d["reason"] == "duplicate" for d in more.discarded)
    assert (
        "[이미 보인 과제안]" in llm2.calls[0] and "신설역 개통 초기 월별 수요 보정" in llm2.calls[0]
    )


async def test_polish_has_no_time_limit():
    slow = SlowLLM(json.dumps({"text": "다듬은 목표임"}, ensure_ascii=False))
    local = FakeLLM([json.dumps({"text": "로컬"}, ensure_ascii=False)])
    polish = PolishField(primary=slow, local=local)
    task = asyncio.ensure_future(polish(IDEA, "goal", "폐철도역사 유휴 공간 활용 유형 제시"))
    await asyncio.sleep(0.05)
    assert not task.done() and not local.calls
    slow.gate.set()
    out = await task
    assert out.by == "argon" and not local.calls


def test_generic_terms_from_pilot_are_not_core_keywords():
    """시범 핵심 키워드 칸의 일반어(예측·변화·수요 …)는 겹친 키워드로 세지 않는다
    (config/overlap.yaml)."""
    from rra.config_loader import keyword_rule
    from rra.domain.rules.keywords import core_keyword_overlap, core_terms
    from rra.settings import Settings

    rule = keyword_rule(Settings(_env_file=None))
    assert core_terms(["광역철도 수요 예측 모형", "기후 변화 대응"], rule) == ["광역철", "기후"]
    assert core_terms(["수송수요 예측", "차량기지 화차"], rule) == ["수송수요", "차량기지", "화차"]
    doc = "연도별 수요 예측 모형의 변화 추정"
    assert core_keyword_overlap("", ["철도 수요 예측", "궤도 틀림"], doc, rule) == []
