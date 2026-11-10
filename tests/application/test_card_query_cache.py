"""카드 질의와 실시간 검색 캐시·세션 (ADR 0065, 계약 problem-card.md 4.1절).

LiveSearch 는 고치지 않는다 — 세션은 (소유자, 입력 글), 24시간 자료원 캐시는 (자료원, 보낸 질의,
건수)가 키다. 카드 기반 유추는 소유자에 질의 지문을 붙이고(`analogy_owner`), 키워드는 요청에 실린
카드에서 그대로 만든다. 그러면 기능 문장을 고쳤을 때 이전 결과가 재사용되지 않는다.
"""

from pathlib import Path

from rra.adapters.persistence.file_cache import FileCache
from rra.adapters.runs import AsyncioTaskRunner
from rra.application.usecases.live_search import LiveSearch
from rra.domain.models import ProposalRequest
from rra.domain.models.live_search import LiveKeywords
from rra.domain.models.problem_card import CardText, LadderStep, ProblemTerms
from rra.domain.rules.card_queries import analogy_owner, card_queries
from tests.application.test_live_search import FakeSource, IdentityRepo, _cfg, _doc
from tests.domain.test_card_queries import IDEA, card

LEGACY = LiveKeywords(ko=["비둘기 침입 방지"], en=["pigeon intrusion"], origin="rule")


async def card_keywords(req: ProposalRequest) -> LiveKeywords:
    """레인 B 의 유추 키워드가 따를 모양 — 카드가 있으면 카드 질의, 없으면 종전(규칙) 키워드."""
    q = card_queries(req.problem_card)
    if q is None:
        return LEGACY
    return LiveKeywords(ko=list(q.live_ko), en=list(q.live_en), origin="rule")


def setup(tmp_path: Path):
    srcs = [
        FakeSource("scienceon", "ko", [_doc("scienceon:A1")]),
        FakeSource("openalex", "en", [_doc("openalex:W1", lang="en")]),
    ]
    live = LiveSearch(
        _cfg(),
        IdentityRepo(),
        AsyncioTaskRunner(),
        sources={s.source: s for s in srcs},
        keywords=card_keywords,
        keyword_cache=False,  # 유추 검색 인스턴스와 같다 — 입력 글 키의 키워드 캐시를 쓰지 않는다
        cache=FileCache(tmp_path / "cache", ttl_sec=24 * 3600),
    )
    return live, srcs


def req_with(c) -> ProposalRequest:
    return ProposalRequest(**IDEA, problem_card=c)


def owner(req: ProposalRequest) -> str:
    return analogy_owner("analogy", card_queries(req.problem_card))


async def test_edited_function_sentence_is_searched_again_not_served_from_cache(tmp_path):
    live, (ko_src, en_src) = setup(tmp_path)
    first = req_with(card())
    await live.prepare(owner(first), first)
    assert ko_src.calls[0][0] == ["비둘기 퇴치", "조류 퇴치", "비둘기 착좌 둥지 방지"]
    assert en_src.calls[0][0][-1] == "Prevent birds from perching and nesting on structures"

    # 기능 문장을 고치고 그에 따라 사다리·문제어·영문이 다시 만들어진 카드
    edited = req_with(
        card(
            function_ko=CardText(value="조류가 지붕에 머무르지 못하게 한다", origin="user"),
            function_en=CardText(value="Keep birds from staying on station roofs"),
            ladder=[
                LadderStep(level="구체", text="비둘기 체류 방지"),
                LadderStep(level="일반화", text="조류 체류 억제 장치"),
            ],
            terms=ProblemTerms(
                objects_ko=["비둘기", "조류"],
                actions_ko=["체류"],
                objects_en=["pigeon", "bird"],
                actions_en=["roost"],
            ),
        )
    )
    again = await live.prepare(owner(edited), edited)
    # 입력 글은 같지만 보낸 질의가 달라 새 세션·새 호출(24시간 캐시 재사용 없음)
    assert len(ko_src.calls) == 2 and len(en_src.calls) == 2
    assert not any(r.cached for r in again.sources if r.status == "ok")
    assert ko_src.calls[1][0] == ["비둘기 체류", "조류 체류", "비둘기 체류 방지"]
    assert en_src.calls[1][0][-1] == "Keep birds from staying on station roofs"


async def test_only_sentence_changed_resends_only_the_queries_that_changed(tmp_path):
    """국문 기능 문장만 바뀌고 문제어·사다리가 그대로면(다시 만들기 실패 등) 새 세션이지만, 글자가
    같은 실시간 질의는 자료원 응답 캐시가 맞는다 — 키는 카드가 아니라 실제 보낸 질의다."""
    live, (ko_src, en_src) = setup(tmp_path)
    first = req_with(card())
    await live.prepare(owner(first), first)
    sentence_only = req_with(
        card(function_ko=CardText(value="조류가 지붕에 머무르지 못하게 한다", origin="user"))
    )
    assert owner(sentence_only) != owner(first)  # 저장 자료 질의가 달라 지문·세션은 새로
    again = await live.prepare(owner(sentence_only), sentence_only)
    assert live.find(owner(sentence_only), sentence_only) is not live.find(owner(first), first)
    assert all(r.cached for r in again.sources if r.status == "ok")  # 같은 질의 → 같은 응답
    assert len(ko_src.calls) == 1 and len(en_src.calls) == 1


async def test_same_queries_reuse_cache_and_switch_off_is_separate(tmp_path):
    live, (ko_src, en_src) = setup(tmp_path)
    with_card = req_with(card())
    plain = ProposalRequest(**IDEA)  # 스위치 꺼짐·카드 없음 — 종전 소유자·규칙 키워드
    await live.prepare(owner(with_card), with_card)
    off = await live.prepare(owner(plain), plain)
    assert owner(plain) == "analogy"
    assert live.find(owner(plain), plain) is not live.find(owner(with_card), with_card)
    assert ko_src.calls[1][0] == ["비둘기 침입 방지"]  # 종전 질의로 따로 호출
    assert not any(r.cached for r in off.sources if r.status == "ok")
    # 질의에 안 들어가는 칸만 고친 카드 → 같은 질의 → 같은 세션(다시 부르지 않는다)
    cause_only = req_with(card(causes=[CardText(value="앉을 자리가 있음", origin="user")]))
    await live.prepare(owner(cause_only), cause_only)
    assert len(ko_src.calls) == 2 and len(en_src.calls) == 2
    # 다른 인스턴스(재시작 뒤)라도 같은 질의면 24시간 자료원 캐시가 맞는다
    live2, (ko2, en2) = setup(tmp_path)
    cached = await live2.prepare(owner(with_card), with_card)
    assert all(r.cached for r in cached.sources if r.status == "ok")
    assert ko2.calls == [] and en2.calls == []


async def test_without_fingerprint_owner_the_old_session_would_be_reused(tmp_path):
    """왜 소유자에 지문이 필요한가 — 종전 소유자("analogy")를 그대로 쓰면 고친 카드가 옛 세션을
    받는다."""
    live, (ko_src, _) = setup(tmp_path)
    first = req_with(card())
    edited = req_with(card(function_ko=CardText(value="조류가 지붕에 머무르지 못하게 한다")))
    a = live.start("analogy", first)
    await live.wait(a)
    assert live.start("analogy", edited) is a  # 같은 입력 글 → 같은 세션 (고친 질의로 검색 안 함)
    assert len(ko_src.calls) == 1
