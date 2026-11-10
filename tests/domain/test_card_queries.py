"""카드 질의·지문 (ADR 0065, 계약 problem-card.md 4.1절) — 캐시·세션·메모는 실제 보낸 질의 기준."""

from rra.domain.models import ProposalRequest
from rra.domain.models.problem_card import (
    CardRank,
    CardText,
    ClassCode,
    Contradiction,
    LadderStep,
    ProblemCard,
    ProblemTerms,
)
from rra.domain.rules.card_queries import (
    analogy_owner,
    card_queries,
    class_query,
    memo_groups,
    pick_fingerprint,
    search_fingerprint,
)
from rra.domain.rules.live_search import cache_key, session_key
from rra.domain.rules.novelty import input_key

IDEA = {
    "title_hint": "철도역사 비둘기 침입 방지",
    "current_state": "역사 승강장 지붕에 비둘기가 드나들어 배설물 민원이 반복됨",
    "root_cause": "출입구가 열려 있어 비둘기 침입 경로가 막히지 않음",
    "limitation": "그물 설치는 미관을 해치고 유지관리가 어려움",
    "goal": "역사 구조에 맞는 비둘기 침입 방지 방법을 마련함",
}


def card(**over) -> ProblemCard:
    base = dict(
        function_ko=CardText(value="조류가 구조물에 앉거나 둥지를 틀지 못하게 막는다"),
        function_en=CardText(value="Prevent birds from perching and nesting on structures"),
        ladder=[
            LadderStep(level="구체", text="비둘기 착좌 둥지 방지"),
            LadderStep(level="일반화", text="조류 접근 방지 장치"),
            LadderStep(level="추상화", text="유해동물 구조물 접근 차단"),
        ],
        terms=ProblemTerms(
            objects_ko=["비둘기", "조류"],
            actions_ko=["퇴치", "착좌"],
            objects_en=["pigeon", "bird"],
            actions_en=["deterr", "perch"],
        ),
        ipc=[
            ClassCode(code="A01M 29/00", verified="corpus", count=12),
            ClassCode(code="E04D 13/00"),  # 확인 못 함 — 검색에 쓰지 않는다
        ],
    )
    return ProblemCard(**{**base, **over})


def test_queries_come_from_ladder_and_function_sentences():
    q = card_queries(card())
    assert q.stored == (
        "비둘기 착좌 둥지 방지",
        "조류 접근 방지 장치",
        "유해동물 구조물 접근 차단",
        "조류가 구조물에 앉거나 둥지를 틀지 못하게 막는다",
        "Prevent birds from perching and nesting on structures",
    )
    assert q.live_ko[:2] == ("비둘기 착좌 둥지 방지", "조류 접근 방지 장치")
    assert q.live_en == (
        "pigeon deterr",
        "bird deterr",
        "Prevent birds from perching and nesting on structures",
    )
    assert q.ipc == ("A01M 29/00",)


def test_no_card_or_switch_off_means_legacy_keys():
    req = ProposalRequest(**IDEA)
    assert card_queries(None) is None
    assert card_queries(card(), use_queries=False) is None
    assert card_queries(ProblemCard()) is None  # 빈 카드
    assert search_fingerprint(None) == ""
    assert analogy_owner("analogy", None) == "analogy"
    assert memo_groups("") == []
    assert input_key(req, ["비둘기"], *memo_groups("")) == input_key(req, ["비둘기"])
    assert card_queries(card(), use_class=False).ipc == ()


def test_editing_function_sentence_changes_fingerprint_session_and_memo():
    """기능 문장(과 그에 따라 다시 만든 사다리)을 고치면 이전 세션·메모를 다시 쓰지 않는다."""
    req = ProposalRequest(**IDEA)
    before = card_queries(card())
    edited = card(
        function_ko=CardText(value="조류가 지붕 구조물에 머무르지 못하게 한다", origin="user"),
    )
    after = card_queries(edited)
    assert search_fingerprint(after) != search_fingerprint(before)
    # 같은 입력 글이라 session_key 는 owner 로만 갈린다
    assert session_key(analogy_owner("analogy", after), req) != session_key(
        analogy_owner("analogy", before), req
    )
    rank = CardRank()
    key_before = input_key(req, [], *memo_groups(pick_fingerprint(before, card(), rank)))
    key_after = input_key(req, [], *memo_groups(pick_fingerprint(after, edited, rank)))
    assert key_before != key_after
    # 사다리·영문만 바뀌어도(derive 결과) 마찬가지
    ladder_only = card(
        ladder=[
            LadderStep(level="구체", text="비둘기 영소 방지"),
            LadderStep(level="일반화", text="조류 접근 방지 장치"),
            LadderStep(level="추상화", text="유해동물 구조물 접근 차단"),
        ]
    )
    assert search_fingerprint(card_queries(ladder_only)) != search_fingerprint(before)


def test_card_keys_never_equal_switch_off_keys():
    req = ProposalRequest(**IDEA)
    q = card_queries(card())
    assert analogy_owner("analogy", q).startswith("analogy:card:")
    assert session_key(analogy_owner("analogy", q), req) != session_key("analogy", req)
    with_card = input_key(req, [], *memo_groups(pick_fingerprint(q, card(), CardRank())))
    assert with_card != input_key(req, [])


def test_fields_not_sent_do_not_change_search_fingerprint():
    """원인·모순처럼 질의에 들어가지 않는 칸은 검색 지문을 바꾸지 않는다(카드 전체가 키가
    아니다)."""
    base = search_fingerprint(card_queries(card()))
    other = card(
        causes=[CardText(value="앉을 자리와 먹이가 있음", origin="user")],
        contradiction=Contradiction(improve="접근 차단", worsen="미관"),
        signals=["unclear_cause"],
    )
    assert search_fingerprint(card_queries(other)) == base
    # 띄어쓰기·대소문자만 다른 질의는 같은 질의
    spaced = card(
        function_en=CardText(value="prevent  BIRDS from perching and nesting on structures")
    )
    assert search_fingerprint(card_queries(spaced)) == base


def test_rank_inputs_change_pick_fingerprint_only():
    q = card_queries(card())
    more_terms = card(
        terms=ProblemTerms(
            objects_ko=["비둘기", "조류", "까치"],
            actions_ko=["퇴치", "착좌"],
            objects_en=["pigeon", "bird"],
            actions_en=["deterr", "perch"],
        )
    )
    assert search_fingerprint(card_queries(more_terms)) == search_fingerprint(q)
    rank = CardRank()
    assert pick_fingerprint(card_queries(more_terms), more_terms, rank) != pick_fingerprint(
        q, card(), rank
    )
    assert pick_fingerprint(q, card(), CardRank(per_source=3)) != pick_fingerprint(q, card(), rank)


def test_class_query_does_not_collide_with_keyword_query():
    assert class_query("a01m  29/00") == "ipc:A01M 29/00"
    assert cache_key("kipris_kr", [class_query("A01M 29/00")], 30) != cache_key(
        "kipris_kr", ["A01M 29/00"], 30
    )
