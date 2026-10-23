"""[4] 완료 기준 — 임베딩 계산(블로킹 CPU)이 돌아가는 동안에도 검색·precheck 요청이 처리된다.

SlowEmbedding 은 실물 어댑터처럼 계산을 스레드로 넘긴다. 저장소도 SQLite 접근을 스레드로 넘기므로
느린 질의 하나가 이벤트 루프를 잡고 있지 않다 — 같은 루프의 다른 코루틴이 먼저 끝난다.
"""

import asyncio
import time

import pytest

from rra.adapters.persistence import SQLiteDocumentRepository
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.rules.lint import LintRules
from tests.fakes import FakeLLM, FakePromptLibrary, SlowEmbedding

DELAY = 0.4


@pytest.fixture
async def repo(tmp_path, docs, chunks):
    emb = SlowEmbedding(delay=DELAY)
    r = SQLiteDocumentRepository(tmp_path / "rra.sqlite", emb, prefer_extension=False)
    await r.upsert(docs, chunks)
    yield r
    r.close()


async def timed(coro):
    t0 = time.perf_counter()
    result = await coro
    return result, time.perf_counter() - t0


async def test_search_and_precheck_proceed_while_a_slow_embedding_runs(repo, req):
    slow = asyncio.create_task(timed(repo.hybrid_search([f"{SlowEmbedding.SLOW_MARK} 궤도"], k=5)))
    await asyncio.sleep(0.02)  # 느린 임베딩이 스레드에서 돌기 시작하도록

    fast_search, t_search = await timed(repo.hybrid_search(["궤도"], k=5))
    alerts, t_precheck = await timed(PrecheckOverlap(repo)(req))
    counts, t_count = await timed(repo.count_by_source())

    assert not slow.done(), "빠른 요청들이 끝났는데 느린 임베딩은 아직 돌고 있어야 한다"
    (slow_result, t_slow) = await slow

    assert isinstance(fast_search, list) and isinstance(slow_result, list)
    assert isinstance(alerts, list) and sum(counts.values()) == 3
    assert t_slow >= DELAY
    assert max(t_search, t_precheck, t_count) < DELAY / 2  # 루프가 막혀 있었다면 DELAY 이상 걸린다
    assert repo.embedding.slow_calls == 1


async def test_retrieve_does_not_block_other_requests(repo, req):
    rules = LintRules(template="t", sections=["title"], required_sections=["title"])
    gen = GenerateProposal(
        FakeLLM(), repo, FakePromptLibrary(), rules, ["title"], check_overlap=True
    )
    slow_req = req.model_copy(update={"title_hint": SlowEmbedding.SLOW_MARK})

    t0 = time.perf_counter()
    retrieve = asyncio.create_task(gen.retrieve(slow_req))
    await asyncio.sleep(0.02)
    alerts, t_precheck = await timed(PrecheckOverlap(repo)(req))
    assert not retrieve.done()
    snapshot = await retrieve
    assert isinstance(snapshot.retrieved_ids, set) and isinstance(alerts, list)
    assert t_precheck < DELAY / 2
    assert time.perf_counter() - t0 < DELAY * 2.5  # 직렬 실행(3×DELAY)보다 짧다


async def test_concurrent_writes_and_reads_are_serialized_safely(repo, docs, chunks):
    """스레드풀에서 쓰기·읽기가 섞여도 RLock 으로 직렬화되어 깨지지 않는다."""
    writes = [repo.upsert(docs, chunks) for _ in range(3)]
    reads = [repo.hybrid_search(["궤도"], k=5) for _ in range(5)]
    results = await asyncio.gather(*writes, *reads)
    assert all(isinstance(r, list) for r in results[3:])
    assert await repo.count_by_source() == {d.source: 1 for d in docs} | {
        s: n for s, n in (await repo.count_by_source()).items()
    }
