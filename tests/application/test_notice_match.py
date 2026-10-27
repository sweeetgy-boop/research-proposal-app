"""NoticeMatcher — rnd_notice 자료원만, 접수 중(마감 전) 공고만, 상위 3건, LLM 없음."""

from datetime import date

from rra.application.usecases.notice_match import NoticeMatcher
from rra.domain.models import Chunk, Document, ProposalRequest
from rra.domain.rules.retrieval_scope import OVERLAP_EXCLUDED_DOC_TYPES, overlap_candidates
from tests.fakes import InMemoryRepository

TODAY = date(2026, 10, 27)
REQ = ProposalRequest(
    current_state="궤도 틀림 점검이 수작업",
    root_cause="센서 부재",
    limitation="주기 점검",
    goal="상태기반 유지보수 자동 감지",
)


def notice(n: str, deadline: date | None, **extra) -> Document:
    return Document(
        doc_id=f"rnd_notice:{n}",
        source="rnd_notice",
        doc_type="rnd_notice",
        title=f"공고 {n}",
        body="x",
        pub_date=date(2026, 9, 1),
        url=f"https://www.kaia.re.kr/x?id={n}",
        valid_until=deadline,
        raw={
            "notice": {
                "agency": "국토교통과학기술진흥원",
                "program": "국토교통연구기획",
                "deadline": deadline.isoformat() if deadline else None,
            }
        },
        **extra,
    )


def chunk(n: str, sim: float) -> Chunk:
    return Chunk(
        chunk_id=f"rnd_notice:{n}#0",
        doc_id=f"rnd_notice:{n}",
        ordinal=0,
        text="철도 상태기반 유지보수 기술개발",
        similarity=sim,
    )


async def test_returns_open_notices_only_top3_sorted_by_similarity():
    repo = InMemoryRepository()
    repo.today = lambda: TODAY
    docs = [
        notice("a", date(2026, 11, 30)),
        notice("b", date(2026, 10, 27)),  # 마감 당일 → 접수 중
        notice("c", date(2026, 10, 26)),  # 만료 → 저장소가 거른다
        notice("d", None),
        notice("e", date(2027, 1, 1)),
        Document(doc_id="korail_web:p", source="korail_web", doc_type="policy", title="정책"),
    ]
    chunks = [chunk("a", 0.7), chunk("b", 0.9), chunk("c", 0.95), chunk("d", 0.5), chunk("e", 0.8)]
    chunks.append(
        Chunk(
            chunk_id="korail_web:p#0",
            doc_id="korail_web:p",
            ordinal=0,
            text="정책",
            similarity=0.99,
        )
    )
    repo.seed(docs, chunks)
    out = await NoticeMatcher(repo, today=lambda: TODAY)(REQ)
    assert [m.doc_id for m in out] == ["rnd_notice:b", "rnd_notice:e", "rnd_notice:a"]
    first = out[0]
    assert first.deadline == date(2026, 10, 27) and first.days_left == 0
    assert first.agency == "국토교통과학기술진흥원" and first.program == "국토교통연구기획"
    assert first.url.endswith("id=b") and first.similarity == 0.9 and first.trust == "untrusted"
    call = next(c for c in repo.calls if c[0] == "hybrid_search")
    assert call[1]["sources"] == ["rnd_notice"] and call[1]["k"] == 18


async def test_empty_without_notices():
    assert await NoticeMatcher(InMemoryRepository())(REQ) == []


def test_notices_never_enter_overlap_judgement():
    paper = Document(doc_id="openalex:W1", source="openalex", doc_type="paper", title="t")
    hits = [(notice("a", None), 0.99), (paper, 0.9)]
    assert overlap_candidates(hits) == [(paper, 0.9)] and "rnd_notice" in OVERLAP_EXCLUDED_DOC_TYPES
