"""문제 정의 카드 재사용·고정 (계약 problem-card.md 4.4절) — 같은 제안문은 AI 1회, 다시 정리는 새로,
실패는 캐시하지 않음, 사용자 항목 보존, 고정은 사용자별·공용 계정 제외, 꺼짐이면 저장소를 건드리지
않음. FakeLLM·메모리 저장소, 네트워크 없음."""

from __future__ import annotations

import json
import logging

from rra.application.usecases.card_reuse import CardReuse
from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import CardReuseConfig, ProblemCard, ProblemCardConfig
from rra.domain.rules import card_reuse as reuse_rules
from rra.domain.rules import problem_card as rules
from tests.application.test_problem_card_usecases import (
    GOOD,
    GUEST,
    ME,
    ON,
    OTHER,
    TESTER,
    Codes,
    MemLog,
    SlowLLM,
    base_card,
    diagnosis,
    edit_row,
    edited,
)
from tests.domain.test_problem_card_rules import RAW, REQ
from tests.fakes import DeterministicEmbedding, FakeLLM, FakePromptLibrary

OTHER_GOOD = json.dumps({**RAW, "function_ko": "비둘기의 착좌를 막는다"}, ensure_ascii=False)


class Store:
    """CachePort 가짜 — 읽기·쓰기 횟수를 센다."""

    def __init__(self, *, broken: bool = False):
        self.data: dict[str, dict] = {}
        self.gets: list[str] = []
        self.sets: list[str] = []
        self.broken = broken

    def get(self, key):
        self.gets.append(key)
        if self.broken:
            raise OSError("디스크 오류")
        return self.data.get(key)

    def set(self, key, value):
        self.sets.append(key)
        if self.broken:
            raise OSError("디스크 오류")
        self.data[key] = json.loads(json.dumps(value))


def reuse_for(config=ON, **kw) -> CardReuse:
    return CardReuse(config, cache=kw.pop("cache", Store()), pins=kw.pop("pins", Store()), **kw)


def user_edit(card: ProblemCard, text: str = "조류의 착좌를 막는다") -> ProblemCard:
    out, _ = rules.apply_edits(card, edited(card, function_ko=text), ["function_ko"])
    return out


# ── 공용 캐시 ───────────────────────────────────────────────
async def test_same_input_twice_calls_ai_once_and_reports_cached():
    llm, codes, reuse = FakeLLM([GOOD, OTHER_GOOD]), Codes({"A01M 29/00": 4}), reuse_for()
    diag = diagnosis(llm, code_check=codes, reuse=reuse, model_name="argon-x")
    first = await diag(REQ, principal=ME)
    checked = len(codes.calls)
    second = await diag(REQ, principal=OTHER)  # 공용 캐시 — 다른 사용자도 같은 카드
    spaced = ProposalRequest(**{**REQ.model_dump(), "goal": f"  {REQ.goal}  "})
    third = await diag(spaced, principal=None)
    assert len(llm.calls) == 1 and len(codes.calls) == checked  # AI·분류 확인을 다시 부르지 않는다
    assert (first.reused, second.reused, third.reused) == (None, "cached", "cached")
    assert second.status == "ok" and second.card == first.card == third.card
    assert (second.provider, second.model) == (None, None)


async def test_cache_holds_only_the_card_no_input_text_or_user_id():
    reuse = reuse_for()
    await diagnosis(FakeLLM([GOOD]), reuse=reuse)(REQ, principal=ME)
    (key,) = reuse.cache.data
    stored = reuse.cache.data[key]
    assert ProblemCard.model_validate(stored).function_ko.value == "비둘기의 침입을 막는다"
    blob = key + json.dumps(stored, ensure_ascii=False)
    assert ME.id not in blob and REQ.current_state not in blob and REQ.limitation not in blob
    assert reuse.pins.sets == []  # 진단만으로는 고정하지 않는다


async def test_refresh_calls_ai_again_and_replaces_the_cache():
    llm, reuse = FakeLLM([GOOD, OTHER_GOOD]), reuse_for()
    diag = diagnosis(llm, reuse=reuse)
    await diag(REQ, principal=ME)
    fresh = await diag(REQ, principal=ME, refresh=True)
    assert len(llm.calls) == 2 and fresh.reused is None
    assert fresh.card.function_ko.value == "비둘기의 착좌를 막는다"
    again = await diag(REQ, principal=ME)
    assert again.reused == "cached" and again.card == fresh.card and len(llm.calls) == 2
    assert len(reuse.cache.data) == 1  # 같은 키를 갈아 끼웠다


async def test_failure_and_timeout_are_not_cached():
    reuse = reuse_for()
    bad = json.dumps({**RAW, "function_ko": ""}, ensure_ascii=False)
    out = await diagnosis(FakeLLM([bad, bad]), reuse=reuse)(REQ)
    assert out.status == "failed" and reuse.cache.sets == []
    cfg = ProblemCardConfig(enabled=True, timeout_seconds=0.05)
    slow_reuse = reuse_for(cfg)
    out = await diagnosis(SlowLLM(), config=cfg, reuse=slow_reuse)(REQ)
    assert (out.status, out.reason) == ("failed", "timeout") and slow_reuse.cache.sets == []
    # 실패 뒤 같은 입력은 다시 AI 를 부른다
    llm = FakeLLM([GOOD])
    ok = await diagnosis(llm, reuse=reuse)(REQ)
    assert ok.status == "ok" and ok.reused is None and len(llm.calls) == 1


async def test_prompt_or_model_change_misses_the_cache():
    llm, reuse = FakeLLM([GOOD, GOOD, GOOD]), reuse_for()
    await diagnosis(llm, reuse=reuse, model_name="argon-x")(REQ)
    assert (await diagnosis(llm, reuse=reuse, model_name="argon-x")(REQ)).reused == "cached"
    assert (await diagnosis(llm, reuse=reuse, model_name="argon-y")(REQ)).reused is None
    other_prompt = diagnosis(llm, reuse=reuse, model_name="argon-x")
    other_prompt.prompts = FakePromptLibrary()
    other_prompt.prompts.diagnose = lambda: "DIAGNOSE 새 지시문"
    assert (await other_prompt(REQ)).reused is None
    assert len(llm.calls) == 3 and len(reuse.cache.data) == 3


async def test_cached_card_keeps_user_items_of_previous():
    llm, reuse = FakeLLM([GOOD]), reuse_for()
    diag = diagnosis(llm, reuse=reuse)
    await diag(REQ)
    prev = user_edit(base_card())
    out = await diag(REQ, previous=prev)
    assert out.reused == "cached" and len(llm.calls) == 1
    assert out.card.function_ko.value == "조류의 착좌를 막는다"
    assert out.card.function_ko.origin == "user" and out.card.function_en.origin == "ai"
    # 캐시에는 사용자 항목이 섞이지 않는다
    (stored,) = reuse.cache.data.values()
    assert stored["function_ko"]["origin"] == "ai"


async def test_results_shaped_by_user_items_or_own_examples_stay_out_of_the_shared_cache():
    reuse = reuse_for()
    llm = FakeLLM([GOOD, GOOD])
    out = await diagnosis(llm, reuse=reuse)(REQ, previous=user_edit(base_card()), refresh=True)
    assert out.status == "ok" and reuse.cache.sets == []
    log = MemLog([edit_row(ME.id)])
    personal = diagnosis(llm, reuse=reuse, edit_log=log, embedding=DeterministicEmbedding())
    out = await personal(REQ, principal=ME)
    assert out.status == "ok" and out.examples == 1 and reuse.cache.sets == []


# ── 고정 ────────────────────────────────────────────────────
async def test_pinned_card_comes_first_only_for_that_user():
    llm, reuse = FakeLLM([GOOD]), reuse_for()
    diag = diagnosis(llm, reuse=reuse)
    first = await diag(REQ, principal=ME)
    mine = user_edit(first.card)
    assert reuse.pin(REQ, mine, ME) is True
    got = await diag(REQ, principal=ME)
    assert got.reused == "pinned" and got.card == mine and len(llm.calls) == 1
    # 다른 사용자·공용 계정·로그인 없음에는 고정 카드가 나오지 않는다 — 공용 캐시의 AI 카드만
    for who in (OTHER, GUEST, None):
        out = await diag(REQ, principal=who)
        assert out.reused == "cached" and out.card == first.card
        assert out.card.function_ko.value != mine.function_ko.value
    assert len(llm.calls) == 1


async def test_guest_and_anonymous_are_never_pinned_but_tester_and_admin_are():
    reuse = reuse_for()
    card = base_card()
    assert reuse.pin(REQ, card, GUEST) is False and reuse.pin(REQ, card, None) is False
    assert reuse.pin(REQ, None, ME) is False
    assert reuse.pins.sets == []
    assert reuse.pin(REQ, card, TESTER) is True
    assert len(reuse.pins.data) == 1
    # 공용 계정은 고정 저장소를 읽지도 않는다
    reuse.pins.gets.clear()
    assert reuse.lookup(REQ, GUEST, "v") == (None, None) and reuse.pins.gets == []


async def test_pin_keys_isolate_users_even_with_the_same_input():
    reuse = reuse_for()
    a, b = (
        user_edit(base_card(), "조류의 착좌를 막는다"),
        user_edit(base_card(), "새의 둥지를 막는다"),
    )
    reuse.pin(REQ, a, ME)
    reuse.pin(REQ, b, OTHER)
    assert len(reuse.pins.data) == 2
    assert reuse.lookup(REQ, ME, "v")[0] == a and reuse.lookup(REQ, OTHER, "v")[0] == b
    assert ME.id not in "".join(reuse.pins.data) and OTHER.id not in "".join(reuse.pins.data)
    other_input = ProposalRequest(**{**REQ.model_dump(), "goal": "전혀 다른 목표를 세움"})
    assert reuse.lookup(other_input, ME, "v") == (None, None)


async def test_refresh_skips_the_pin_but_leaves_it_until_confirmed_again():
    llm, reuse = FakeLLM([GOOD, OTHER_GOOD]), reuse_for()
    diag = diagnosis(llm, reuse=reuse)
    first = await diag(REQ, principal=ME)
    reuse.pin(REQ, first.card, ME)
    fresh = await diag(REQ, principal=ME, refresh=True)
    assert fresh.reused is None and len(llm.calls) == 2
    assert (await diag(REQ, principal=ME)).card == first.card  # 고정은 그대로
    reuse.pin(REQ, fresh.card, ME)  # 새 카드로 진행하면 새로 고정된다
    again = await diag(REQ, principal=ME)
    assert again.reused == "pinned" and again.card == fresh.card


# ── 꺼짐·오류 ───────────────────────────────────────────────
async def test_switched_off_never_touches_the_stores():
    card = base_card()
    for cfg in (
        ProblemCardConfig(),  # 맨 위 스위치 꺼짐(저장소 값)
        ProblemCardConfig(enabled=False, reuse=CardReuseConfig(enabled=True)),
        ProblemCardConfig(enabled=True, timeout_seconds=1.0, reuse=CardReuseConfig(enabled=False)),
    ):
        reuse = reuse_for(cfg)
        llm = FakeLLM([GOOD, GOOD])
        diag = diagnosis(llm, config=cfg, reuse=reuse)
        outs = [await diag(REQ, principal=ME), await diag(REQ, principal=ME)]
        assert reuse.pin(REQ, card, ME) is False
        assert reuse.lookup(REQ, ME, "v") == (None, None) and reuse.store(REQ, card, "v") is False
        for store in (reuse.cache, reuse.pins):
            assert store.gets == [] and store.sets == []
        if cfg.enabled:  # 재사용만 끄면 종전처럼 부를 때마다 AI
            assert [o.reused for o in outs] == [None, None] and len(llm.calls) == 2
        else:
            assert [o.status for o in outs] == ["off", "off"] and llm.calls == []


async def test_without_reuse_every_call_asks_ai_as_before():
    llm = FakeLLM([GOOD, GOOD])
    diag = diagnosis(llm)
    outs = [await diag(REQ), await diag(REQ)]
    assert len(llm.calls) == 2 and [o.reused for o in outs] == [None, None]


async def test_store_errors_do_not_break_diagnosis():
    reuse = reuse_for(cache=Store(broken=True), pins=Store(broken=True))
    llm = FakeLLM([GOOD])
    out = await diagnosis(llm, reuse=reuse)(REQ, principal=ME)
    assert out.status == "ok" and out.reused is None and len(llm.calls) == 1
    assert reuse.pin(REQ, out.card, ME) is False


async def test_reuse_log_has_kind_only(caplog):
    reuse = reuse_for()
    diag = diagnosis(FakeLLM([GOOD]), reuse=reuse)
    with caplog.at_level(logging.INFO, logger="rra.problem_card"):
        first = await diag(REQ, principal=ME)
        await diag(REQ, principal=ME)
        reuse.pin(REQ, first.card, ME)
        await diag(REQ, principal=ME)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("card.reuse")]
    assert lines == ["card.reuse kind=none", "card.reuse kind=cached", "card.reuse kind=pinned"]
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert ME.id not in text and "비둘기" not in text and reuse_rules.text_hash(REQ) not in text
