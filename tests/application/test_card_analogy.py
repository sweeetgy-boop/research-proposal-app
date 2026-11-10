"""문제 정의 카드 기반 유추 검색 (ADR 0065, 계약 problem-card.md 4·4.1절) — 가짜 자료원·메모리
저장소, 네트워크 없음.

- 카드 A → 기능 문장을 고친 A' 는 메모·실시간 세션을 다시 쓰지 않고 새 질의로 검색한다.
- 스위치가 꺼져 있으면(설정 없음·enabled=false·쓰임새 꺼짐) 요청에 카드가 있어도 결과·질의·메모 키·
  세션 키가 카드 없는 종전 호출과 같다.
"""

from __future__ import annotations

from rra.application.usecases.live_search import LiveSearch
from rra.application.usecases.novelty import (
    ANALOGY_OWNER,
    ProblemAnalogySearch,
    ProblemKeywords,
)
from rra.domain.models import Document, ProposalRequest
from rra.domain.models.live_search import LiveKeywords
from rra.domain.models.problem_card import CardRank, CardText, CardUse, ProblemCardConfig
from rra.domain.rules.card_queries import (
    analogy_owner,
    card_queries,
    class_query,
    memo_groups,
    pick_fingerprint,
)
from rra.domain.rules.live_search import session_key
from rra.domain.rules.novelty import AnalogySettings, input_key
from tests.application.test_novelty import Repo, Source, _base_cfg
from tests.domain.test_card_queries import IDEA, card
from tests.fakes import FakeTaskRunner

ON = ProblemCardConfig(enabled=True)
# 겹치는 제목 걸러내기(dup_title_ratio)를 끈 설정 — 정렬·상한 규칙만 보는 시험용
NO_DUP = ProblemCardConfig(enabled=True, rank=CardRank(dup_title_ratio=0))
OFF = ProblemCardConfig(enabled=False)
EDITED = CardText(value="조류가 전선과 구조물에 내려앉지 못하게 한다", origin="user")


def req(c=None) -> ProposalRequest:
    return ProposalRequest(**IDEA, problem_card=c)


def doc(doc_id: str, title: str, abstract: str = "", **kw) -> Document:
    base = {"source": doc_id.split(":")[0], "doc_type": "paper", "text_basis": "abstract"}
    return Document(doc_id=doc_id, title=title, abstract=abstract or None, **{**base, **kw})


def pool() -> list[tuple[Document, float]]:
    return [
        (doc("scienceon:S1", "지하 제연설비 역류 침입 방지", "연기 침입을 방지한다"), 0.93),
        (doc("ntis:N1", "설치류 퇴치 미끼 장치", "쥐를 퇴치한다"), 0.91),  # 작용어만
        (doc("scienceon:R1", "도시철도 승강장 비둘기 퇴치"), 0.90),  # 철도 — 뺀다
        (doc("scienceon:B1", "공항 조류 퇴치 장치", "조류가 앉지 못하게"), 0.86),
        (doc("scienceon:B2", "과수원 조류 퇴치 음향 장치"), 0.85),
        (doc("scienceon:B3", "양식장 조류 접근 방지망"), 0.84),
        (doc("scienceon:B4", "건물 외벽 비둘기 착좌 방지 구조"), 0.83),
        (doc("openalex:W1", "Pigeon roosting deterrents on buildings", "birds", lang="en"), 0.82),
        (doc("openalex:W2", "Soft robots that perch", "perching mechanism", lang="en"), 0.81),
        (doc("kipris_kr:1020200000001", "조류 퇴치용 회전 장치", doc_type="patent"), 0.80),
        (doc("scienceon:B5", "축사 조류 침입 차단"), 0.78),  # 하한 아래
    ]


class Scorer:
    """재순위 가짜 — 제목에 든 말로 점수를 준다(절대값은 낮다)."""

    def __init__(self, scores: dict[str, float] | None = None, error: Exception | None = None):
        self.scores, self.error = scores or {}, error
        self.calls: list[tuple[str, list[str]]] = []

    async def score_documents(self, query, docs):
        self.calls.append((query, [d.doc_id for d, _ in docs]))
        if self.error:
            raise self.error
        return [self.scores.get(d.doc_id, 0.1) for d, _ in docs]


def search_for(repo, *, config=ON, scorer=None, live=None, maker=None, **kw):
    return ProblemAnalogySearch(
        repo, card_config=config, scorer=scorer, live=live, problem_keywords=maker, **kw
    )


def stored_queries(repo) -> list[str]:
    return list(dict.fromkeys(c["text"] for name, c in repo.calls if name == "find_similar"))


# ── 정렬 ────────────────────────────────────────────────────
async def test_card_path_requires_object_term_reranks_and_caps_per_source():
    repo = Repo()
    repo.similar = pool()
    scorer = Scorer(
        {"scienceon:B4": 0.42, "scienceon:B1": 0.3, "scienceon:B3": 0.25, "openalex:W1": 0.2}
    )
    plain = ProblemCardConfig(
        enabled=True,
        rank=CardRank(priority_min_ratio=0, with_request_query=False, dup_title_ratio=0),
    )
    out = await search_for(repo, config=plain, scorer=scorer)(req(card()))
    ids = [a.doc_id for a in out]
    # 제연설비(방지만 겹침)·설치류(퇴치만)·철도·영문 무관 자료(perch 만)·하한 아래는 없다
    # 순위 = 재순위 점수. 자료원당 2건 먼저(B4·B1·W1·특허) → 모자란 1건은 넘긴 B3 — 결과는 순위 순
    assert ids == [
        "scienceon:B4",
        "scienceon:B1",
        "scienceon:B3",
        "openalex:W1",
        "kipris_kr:1020200000001",
    ]
    # 저장 자료 질의 = 카드의 사다리 3단 + 국문·영문 기능 문장 (규칙 문제어 질의가 아니다)
    assert stored_queries(repo) == list(card_queries(card()).stored)
    # 재순위 질의 = 국문 기능 문장 + " / " + 영문 기능 문장, 대상은 대상어가 겹친 자료만
    query, scored = scorer.calls[0]
    assert query == (
        "조류가 구조물에 앉거나 둥지를 틀지 못하게 막는다 / "
        "Prevent birds from perching and nesting on structures"
    )
    assert "scienceon:S1" not in scored and "ntis:N1" not in scored and "openalex:W2" not in scored
    by_id = {a.doc_id: a for a in out}
    # 공유 문제어 = 카드 문제어 중 문서에 나온 것 (장소어·일반어 없음)
    assert by_id["scienceon:B4"].why_relevant == "철도 밖에서 같은 문제(비둘기·착좌)를 다룬 자료"
    assert "pigeon" in by_id["openalex:W1"].why_relevant
    assert by_id["scienceon:B4"].similarity == 0.83  # 유사도는 그대로(재순위 점수는 순서에만)


async def test_low_rerank_scores_are_not_a_floor_and_missing_reranker_falls_back():
    repo = Repo()
    repo.similar = pool()
    low = await search_for(repo, config=NO_DUP, scorer=Scorer({}))(req(card()))  # 모두 0.1
    assert len(low) == 5
    for scorer in (None, Scorer(error=RuntimeError("모델 없음"))):
        repo = Repo()
        repo.similar = pool()
        out = await search_for(repo, config=NO_DUP, scorer=scorer)(req(card()))
        # (공유 문제어 수, 유사도) 순 — W1 은 3개(pigeon·bird·deterr), 나머지는 2개에서 유사도 순.
        # 자료원당 2건 먼저(B1·B2), 모자란 1건은 넘긴 B4
        assert [a.doc_id for a in out] == [
            "openalex:W1",
            "scienceon:B1",
            "scienceon:B2",
            "scienceon:B4",
            "kipris_kr:1020200000001",
        ]


async def test_rank_switch_off_uses_card_queries_with_the_old_pick():
    repo = Repo()
    repo.similar = pool()
    config = ProblemCardConfig(enabled=True, use=CardUse(analogy_rank=False))
    scorer = Scorer()
    out = await search_for(repo, config=config, scorer=scorer)(req(card()))
    assert stored_queries(repo) == list(card_queries(card()).stored) and scorer.calls == []
    # 종전 정렬(유사도 순, 한글 자료는 카드 문제어 1개 이상) — 작용어만 겹친 자료도 남는다
    assert [a.doc_id for a in out][:2] == ["ntis:N1", "scienceon:B1"]


async def test_public_account_drops_internal_in_card_path():
    repo = Repo()
    repo.similar = [
        (doc("scienceon:I1", "건물 비둘기 방지 내부 자료", visibility="internal"), 0.9),
        *pool(),
    ]
    out = await search_for(repo, include_internal=False)(req(card()))
    assert "scienceon:I1" not in [a.doc_id for a in out]


# ── 메모·세션 (계약 4.1절) ──────────────────────────────────
def live_setup(repo, config=ON):
    ko = Source(
        "scienceon", "ko", [doc("scienceon:B1", "공항 조류 퇴치 장치", "조류가 앉지 못하게")]
    )
    en = Source("openalex", "en", [doc("openalex:L2", "Bird deterrents", "birds", lang="en")])
    kipris = Source("kipris_kr", "ko", [])
    kipris.class_search = True
    maker = ProblemKeywords(card_config=config)
    cfg = AnalogySettings().live.live_config(
        _base_cfg(
            sources={n: {"enabled": True} for n in ("scienceon", "openalex", "kipris_kr")}
            | {"ntis": {"enabled": False}}
        )
    )
    live = LiveSearch(
        cfg,
        repo,
        FakeTaskRunner(),
        sources={"scienceon": ko, "openalex": en, "kipris_kr": kipris},
        keywords=maker,
        keyword_cache=False,
    )
    return live, maker, ko, en, kipris


async def test_edited_function_sentence_searches_again_without_reusing_memo_or_session():
    repo = Repo()
    repo.similar = pool()
    live, maker, ko, en, kipris = live_setup(repo)
    search = search_for(repo, live=live, maker=maker)
    a, b = card(), card(function_ko=EDITED)

    first = await search(req(a))
    qa = card_queries(a)
    assert ko.calls[0][0] == list(qa.live_ko)
    assert en.calls[0][0] == list(qa.live_en)  # OpenAlex 가 영문 질의를 받는다
    # KIPRIS 는 키워드 뒤에 분류 검색 질의("ipc:" 표식, 확인된 코드만)를 받는다
    assert kipris.calls[0][0] == [*qa.live_ko, class_query("A01M 29/00")]
    assert not any(q.startswith("ipc:") for q in ko.calls[0][0])
    assert any(x.live for x in first)  # 실시간에서 받은 자료 표시
    n_live, n_stored = len(ko.calls), len(repo.calls)

    again = await search(req(a))  # 같은 카드 — 메모 재사용(다시 검색하지 않는다)
    assert [x.doc_id for x in again] == [x.doc_id for x in first]
    assert len(ko.calls) == n_live and len(repo.calls) == n_stored

    await search(req(b))  # 기능 문장을 고침 — 새 세션·새 질의·새 메모
    qb = card_queries(b)
    assert len(ko.calls) == n_live + 1 and ko.calls[-1][0] == list(qb.live_ko)
    # 실시간 국문 키워드는 짧은 대상어+작용어 짝이라 문장은 저장 자료 질의에만 들어간다
    assert EDITED.value in stored_queries(repo)
    keys = set(live._sessions)
    assert keys == {
        session_key(analogy_owner(ANALOGY_OWNER, qa), req(a)),
        session_key(analogy_owner(ANALOGY_OWNER, qb), req(b)),
    }
    memo = set(search._memo._items)
    assert memo == {
        input_key(req(a), [], *memo_groups(pick_fingerprint(qa, a, CardRank()))),
        input_key(req(b), [], *memo_groups(pick_fingerprint(qb, b, CardRank()))),
    }
    # 카드 질의는 입력 글 키의 기억(remember)에 들어가지 않는다
    assert maker._remembered._items == {}


async def test_terms_only_edit_changes_memo_but_not_the_live_session():
    repo = Repo()
    repo.similar = pool()
    live, maker, ko, _, _ = live_setup(repo)
    search = search_for(repo, live=live, maker=maker)
    a = card()
    # 질의에 쓰이지 않는 문제어(둘째 작용어)만 바꾼다 — 실시간 키워드 짝은 첫 작용어만 쓴다
    b = card(terms={**a.terms.model_dump(), "actions_ko": [a.terms.actions_ko[0], "기피"]})
    await search(req(a))
    await search(req(b))
    assert len(ko.calls) == 1 and len(live._sessions) == 1  # 질의가 같아 실시간 세션은 그대로
    assert len(search._memo._items) == 2  # 정렬에 쓰는 값이 달라 메모는 새로


async def test_same_input_with_and_without_card_do_not_share_session_or_memo():
    repo = Repo()
    repo.similar = pool()
    live, maker, ko, _, kipris = live_setup(repo)

    async def base_keywords(_):
        return LiveKeywords(ko=["철도역사 비둘기 퇴치"], en=["pigeon deterrent"], origin="argon")

    search = search_for(repo, live=live, maker=maker, keyword_source=base_keywords)
    await search(req())  # 카드 없음 — 종전 경로
    await search(req(card()))
    assert len(live._sessions) == 2 and len(search._memo._items) == 2
    assert session_key(ANALOGY_OWNER, req()) in live._sessions
    assert ko.calls[0][0][0] == "비둘기 퇴치"  # 종전 규칙 문제어 질의
    assert ko.calls[1][0] == list(card_queries(card()).live_ko)
    assert not any(q.startswith("ipc:") for q in kipris.calls[0][0])  # 카드 없으면 분류 질의 없음


# ── 스위치 꺼짐 = 종전 (회귀) ───────────────────────────────
async def _run_legacy(config, with_card: bool, *, pass_config: bool = True):
    repo = Repo()
    repo.similar = pool()
    live, maker, ko, en, kipris = live_setup(repo, config if pass_config else None)

    async def base_keywords(_):
        return LiveKeywords(
            ko=["철도역사 비둘기 퇴치"], en=["pigeon deterrent station"], origin="argon"
        )

    scorer = Scorer()
    kw = {"card_config": config} if pass_config else {}
    search = ProblemAnalogySearch(
        repo,
        live=live,
        problem_keywords=maker,
        keyword_source=base_keywords,
        scorer=scorer,
        **kw,
    )
    request = req(card() if with_card else None)
    out = await search(request, core_keywords=["철도역사 비둘기 퇴치"])
    return {
        "out": [a.model_dump() for a in out],
        "stored": [c for name, c in repo.calls if name == "find_similar"],
        "live": [ko.calls, en.calls, kipris.calls],
        "sessions": sorted(live._sessions),
        "memo": sorted(search._memo._items),
        "scored": scorer.calls,
        "expected_session": session_key(ANALOGY_OWNER, request),
        "expected_memo": input_key(request, ["철도역사 비둘기 퇴치"]),
    }


async def test_switch_off_results_queries_and_keys_equal_the_cardless_call():
    baseline = await _run_legacy(None, with_card=False, pass_config=False)
    assert baseline["sessions"] == [baseline["expected_session"]]  # 종전 소유자 "analogy"
    assert baseline["memo"] == [baseline["expected_memo"]]  # 종전 메모 키(입력 + 핵심어)
    assert baseline["scored"] == []
    assert [a["doc_id"] for a in baseline["out"]][:3] == [
        "scienceon:S1",
        "ntis:N1",
        "scienceon:B1",
    ]  # 종전 정렬(유사도 순, 문제어 1개 이상) — 고정
    variants = [
        await _run_legacy(None, with_card=True, pass_config=False),  # 설정을 넘기지 않음
        await _run_legacy(None, with_card=True),  # 설정 None
        await _run_legacy(OFF, with_card=True),  # 맨 위 스위치 꺼짐
        await _run_legacy(OFF, with_card=False),
        await _run_legacy(ON, with_card=False),  # 켜져 있어도 카드가 없으면 종전
        await _run_legacy(
            ProblemCardConfig(enabled=True, use=CardUse(analogy_queries=False)), with_card=True
        ),  # 질의 쓰임새 꺼짐 → 정렬도 종전
    ]
    for got in variants:
        assert got == baseline


async def test_request_query_joins_candidates_and_rerank_and_weak_sources_get_no_priority():
    """기본 설정(2026-11-10 실제 카드 측정 뒤): 제안문 문제어 질의를 후보·재순위에 함께 쓰고(높은
    점수를 취함), 재순위 점수가 1위의 25% 미만인 다른 자료원 자료는 자료원 몫으로 끌어오지
    않는다."""
    repo = Repo()
    repo.similar = pool()
    scorer = Scorer(
        {"scienceon:B4": 0.42, "scienceon:B1": 0.3, "scienceon:B3": 0.25, "openalex:W1": 0.2}
    )  # 특허는 0.1 — 1위(0.42)의 25% 미만
    out = await search_for(repo, scorer=scorer)(req(card()))
    ids = [a.doc_id for a in out]
    assert ids[:4] == ["scienceon:B4", "scienceon:B1", "scienceon:B3", "openalex:W1"]
    assert "kipris_kr:1020200000001" not in ids[:4]
    stored = stored_queries(repo)
    assert stored[: len(card_queries(card()).stored)] == list(card_queries(card()).stored)
    assert len(stored) == len(card_queries(card()).stored) + 1  # + 제안문 문제어 질의
    assert len(scorer.calls) == 2 and scorer.calls[1][0] == stored[-1]
