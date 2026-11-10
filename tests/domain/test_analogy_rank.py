"""유추 최종 정렬 규칙 (ADR 0065, 계약 problem-card.md 4절 `analogy_rank`) — 순수 함수."""

from rra.domain.models import Document
from rra.domain.models.problem_card import CardRank
from rra.domain.rules.analogy_rank import (
    card_shared_terms,
    few_analogies,
    object_hits,
    order_rows,
    rank_rows,
    take_by_source,
)
from tests.domain.test_card_queries import card


def doc(doc_id: str, title: str, abstract: str = "", **kw) -> Document:
    base = {"source": doc_id.split(":")[0], "doc_type": "paper", "text_basis": "abstract"}
    return Document(doc_id=doc_id, title=title, abstract=abstract or None, **{**base, **kw})


BIRD = doc("scienceon:B1", "공항 조류 퇴치 장치", "조류가 앉지 못하게 한다")
PIGEON_EN = doc("openalex:W1", "Pigeons roosting on buildings", "Deterrents for birds", lang="en")
SMOKE = doc("scienceon:S1", "지하 제연설비 역류 방지", "연기 확산을 방지한다")  # 작용어도 없음
ACTION_ONLY = doc("ntis:N1", "설치류 퇴치 미끼 장치", "쥐를 퇴치한다")  # 작용어(퇴치)만
EN_UNRELATED = doc("openalex:W2", "Perching robots for inspection", "A perch mechanism", lang="en")


def test_object_term_is_required_for_korean_and_english_documents():
    rows = rank_rows(
        [(BIRD, 0.83), (PIGEON_EN, 0.82), (SMOKE, 0.9), (ACTION_ONLY, 0.88), (EN_UNRELATED, 0.87)],
        card(),
        CardRank(),
    )
    assert [r.doc.doc_id for r in rows] == ["scienceon:B1", "openalex:W1"]
    assert rows[0].objects == ("조류",) and rows[0].shared == ("조류", "퇴치")
    # 영문 자료도 대상어(낱말 앞부분 일치: pigeon → pigeons, bird → birds)가 겹쳐야 남는다
    assert rows[1].objects == ("pigeon", "bird") and "deterr" in rows[1].shared
    assert object_hits(card(), EN_UNRELATED) == []
    assert card_shared_terms(card(), ACTION_ONLY) == ["퇴치"]


def test_require_object_off_keeps_everything_and_rerank_top_cuts_by_similarity():
    found = [(SMOKE, 0.9), (ACTION_ONLY, 0.88), (BIRD, 0.83)]
    rows = rank_rows(found, card(), CardRank(require_object=False))
    assert [r.doc.doc_id for r in rows] == ["scienceon:S1", "ntis:N1", "scienceon:B1"]
    many = [(doc(f"scienceon:M{i}", f"조류 {i}"), 0.9 - i * 0.001) for i in range(8)]
    top = rank_rows(many, card(), CardRank(rerank_top=5))
    assert [r.doc.doc_id for r in top] == [f"scienceon:M{i}" for i in range(5)]


def test_multiword_term_needs_every_word():
    c = card(terms={"objects_ko": ["유해 조수"], "objects_en": ["wild boar"]})
    assert object_hits(c, doc("ntis:A", "유해 야생 조수 피해 방지")) == ["유해 조수"]
    assert object_hits(c, doc("ntis:B", "유해 물질 저감")) == []
    assert object_hits(c, doc("openalex:C", "Wild boars in orchards", lang="en")) == ["wild boar"]


def test_rerank_scores_set_the_order_only_and_fallback_is_shared_count_then_similarity():
    a = doc("scienceon:A", "조류 퇴치 착좌 방지")  # 공유 3
    b = doc("ntis:B", "비둘기 관리")  # 공유 1, 유사도 높음
    c = doc("openalex:C", "Bird deterrent", lang="en")  # 공유 2
    rows = rank_rows([(a, 0.80), (b, 0.90), (c, 0.85)], card(), CardRank())
    assert [r.doc.doc_id for r in rows] == ["ntis:B", "openalex:C", "scienceon:A"]
    # 점수는 낮아도(0.1 대) 순서만 정한다 — 하한으로 쓰지 않는다
    ordered = order_rows(rows, [0.05, 0.31, 0.12])
    assert [r.doc.doc_id for r in ordered] == ["openalex:C", "scienceon:A", "ntis:B"]
    assert [r.score for r in ordered] == [0.31, 0.12, 0.05]
    fallback = order_rows(rows, None)
    assert [r.doc.doc_id for r in fallback] == ["scienceon:A", "openalex:C", "ntis:B"]
    assert order_rows(rows, [0.5]) == fallback  # 개수가 맞지 않는 점수는 쓰지 않는다


def test_per_source_first_then_fill_in_rank_order():
    names = ["scienceon:1", "scienceon:2", "scienceon:3", "scienceon:4", "ntis:1", "scienceon:5"]
    ordered = order_rows(
        rank_rows(
            [(doc(n, f"조류 {n}"), 0.9 - i * 0.01) for i, n in enumerate(names)],
            card(),
            CardRank(require_object=False),
        ),
        [0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
    )
    picked = take_by_source(ordered, per_source=2, limit=5)
    # 자료원당 2건 먼저(scienceon 1·2, ntis 1) → 모자란 2건은 넘긴 것(scienceon 3·4)을 순위대로
    assert [r.doc.doc_id for r in picked] == [
        "scienceon:1",
        "scienceon:2",
        "scienceon:3",
        "scienceon:4",
        "ntis:1",
    ]
    # 다른 자료원이 넉넉하면 상한이 지켜진다
    mixed = [*names[:4], "ntis:1", "ntis:2", "openalex:1"]
    ordered = order_rows(
        rank_rows(
            [(doc(n, f"조류 {n}"), 0.9 - i * 0.01) for i, n in enumerate(mixed)],
            card(),
            CardRank(require_object=False),
        ),
        [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3],
    )
    picked = take_by_source(ordered, per_source=2, limit=5)
    assert [r.doc.doc_id for r in picked] == [
        "scienceon:1",
        "scienceon:2",
        "ntis:1",
        "ntis:2",
        "openalex:1",
    ]
    assert take_by_source(ordered, per_source=2, limit=0) == []


def test_few_analogies_signal_is_under_three():
    assert few_analogies(0) and few_analogies(2) and not few_analogies(3)


def test_priority_window_keeps_far_low_ranked_sources_out():
    """자료원당 우선은 순위 상위 window 안에서만 — 한참 아래의 다른 자료원 자료가 5번째로
    들어오지 않는다(2026-11-10 악취 사례: 30위 밖 0.019 점 특허)."""
    names = [*(f"scienceon:{i}" for i in range(1, 8)), "kipris_kr:far"]
    ordered = order_rows(
        rank_rows(
            [(doc(n, f"조류 {n}"), 0.9 - i * 0.01) for i, n in enumerate(names)],
            card(),
            CardRank(require_object=False),
        ),
        [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.01],
    )
    loose = take_by_source(ordered, per_source=2, limit=5)
    assert loose[-1].doc.doc_id == "kipris_kr:far"  # 범위 제한이 없으면 들어온다
    tight = take_by_source(ordered, per_source=2, limit=5, window=6)
    assert [r.doc.doc_id for r in tight] == [f"scienceon:{i}" for i in range(1, 6)]
    # 범위 안의 다른 자료원 자료는 여전히 우선
    near = take_by_source(ordered, per_source=2, limit=5, window=8)
    assert near[-1].doc.doc_id == "kipris_kr:far"
    assert CardRank().priority_window == 15


def test_similar_titles_keep_only_the_highest_ranked():
    """제목에서 흔한 꼬리말을 뺀 낱말이 60% 이상 겹치면 같은 자료 — 순위 높은 하나만
    (2026-11-10 악취 사례: 역류 방지 장치 3건이 5건 중 3건)."""
    from rra.domain.models.problem_card import ProblemTerms
    from rra.domain.rules.analogy_rank import drop_similar_titles, title_overlap, title_words

    suffixes = CardRank().dup_title_suffixes
    a = title_words("악취 역류 차단 장치", suffixes)
    b = title_words("하수구 악취 역류 방지기", suffixes)
    c = title_words("악취 역류 방지장치", suffixes)
    assert a == ["악취", "역류", "차단"] and b == ["하수구", "악취", "역류"]
    assert c == ["악취", "역류", "방지"]
    assert title_overlap(a, b) >= 0.6 and title_overlap(a, c) >= 0.6
    other = title_words("공중화장실 복합악취 및 개선에 관한 연구 (대전광역시 동구)", suffixes)
    assert title_overlap(a, other) < 0.6
    # 낱말이 하나뿐인 제목은 판정하지 않는다, 영문은 불용어를 빼고 본다
    assert title_overlap(title_words("악취 장치", suffixes), a) == 0.0
    assert (
        title_overlap(
            title_words("Deterrence of pigeons on buildings"),
            title_words("Pigeon deterrence for a building"),
        )
        == 1.0
    )
    titles = [
        "악취 역류 차단 장치",
        "하수구 악취 역류 방지기",
        "공중화장실 악취 개선에 관한 연구",
        "악취 역류 방지장치",
        "변기용 악취 제거 장치",
    ]
    rows = order_rows(
        rank_rows(
            [(doc(f"scienceon:{i}", t), 0.9 - i * 0.01) for i, t in enumerate(titles)],
            card(terms=ProblemTerms(objects_ko=["악취"])),
            CardRank(),
        ),
        [0.9, 0.8, 0.7, 0.6, 0.5],
    )
    kept = drop_similar_titles(rows, ratio=0.6, suffixes=suffixes)
    assert [r.doc.title for r in kept] == [titles[0], titles[2], titles[4]]
    assert len(drop_similar_titles(rows, ratio=0, suffixes=suffixes)) == 5  # 0 이면 끔
