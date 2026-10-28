"""[4] 실시간 자료 검색 유스케이스 (LiveSearch) — 가짜 자료원·메모리/임시 SQLite 저장소, 네트워크
없음."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from rra.adapters.persistence.file_cache import FileCache
from rra.adapters.persistence.source_availability import FileSourceAvailability
from rra.adapters.runs import AsyncioTaskRunner
from rra.application.ports import BudgetExhausted
from rra.application.services.scoped_repository import PublicOnlyRepository
from rra.application.usecases.live_search import LiveKeywordMaker, LiveSearch
from rra.domain.models import Chunk, Document, ProposalRequest
from rra.domain.models.live_search import LiveSearchConfig, LiveSourceConfig
from rra.domain.rules.live_search import match_existing
from rra.domain.rules.source_ip import SourceIpBlocked
from tests.fakes import FakeLLM, InMemoryRepository

KW_JSON = json.dumps(
    {"ko": ["열차 지연 예측", "운행 데이터", "머신러닝"], "en": ["train delay", "prediction"]},
    ensure_ascii=False,
)


def _req(**kw) -> ProposalRequest:
    base = {
        "title_hint": "열차 운행 지연 예측",
        "current_state": "열차 지연이 반복된다",
        "root_cause": "운행 데이터 분석 부족",
        "limitation": "수작업 분석",
        "goal": "머신러닝 기반 지연 예측",
    }
    return ProposalRequest(**{**base, **kw})


def _doc(doc_id: str, **kw) -> Document:
    base = {
        "source": doc_id.split(":")[0],
        "doc_type": "paper",
        "title": f"{doc_id} 열차 지연 예측 연구",
        "abstract": "열차 지연을 예측한다.",
        "text_basis": "abstract",
    }
    return Document(doc_id=doc_id, **{**base, **kw})


class FakeSource:
    def __init__(self, source, lang, docs=(), *, delay=0.0, error=None):
        self.source, self.lang = source, lang
        self.docs, self.delay, self.error = list(docs), delay, error
        self.calls: list[tuple[list[str], int]] = []

    async def fetch(self, queries, limit):
        self.calls.append((list(queries), limit))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return list(self.docs)[:limit]


class IdentityRepo(InMemoryRepository):
    """IdentityLookupPort 를 가진 메모리 저장소 (SQLite 와 같은 판정 함수)."""

    async def find_identities(self, docs):
        return match_existing(docs, list(self.docs.values()))


def _cfg(**kw) -> LiveSearchConfig:
    base = {
        "enabled": True,
        "per_source_timeout_seconds": 1.0,
        "overall_timeout_seconds": 2.0,
        "wait_seconds": 3.0,
    }
    return LiveSearchConfig(**{**base, **kw})


def _live(sources, *, repo=None, cfg=None, llm=None, cache=None, availability=None, **kw):
    return LiveSearch(
        cfg or _cfg(),
        repo if repo is not None else IdentityRepo(),
        AsyncioTaskRunner(),
        sources={s.source: s for s in sources},
        keywords=LiveKeywordMaker(primary=llm or FakeLLM([KW_JSON])),
        cache=cache,
        availability=availability,
        **kw,
    )


def _three(**over):
    sources = {
        "scienceon": FakeSource("scienceon", "ko", [_doc("scienceon:A1")]),
        "ntis": FakeSource("ntis", "ko", [_doc("ntis:P1", doc_type="rnd_project")]),
        "openalex": FakeSource("openalex", "en", [_doc("openalex:W1", lang="en")]),
    }
    sources.update(over)
    return list(sources.values())


async def test_all_sources_saved_public_live_and_keywords():
    repo = IdentityRepo()
    srcs = _three(
        openalex=FakeSource(
            "openalex", "en", [_doc("openalex:W1", authors=["Jane Doe"], visibility="internal")]
        )
    )
    live = _live(srcs, repo=repo)
    summary = await live.prepare("u1", _req())
    assert summary.status == "done"
    assert summary.keywords.ko[0] == "열차 지연 예측" and summary.keywords.origin == "argon"
    assert sorted(summary.doc_ids) == ["ntis:P1", "openalex:W1", "scienceon:A1"]
    saved = repo.docs["openalex:W1"]
    assert saved.visibility == "public" and saved.authors == []
    assert saved.raw["live"] is True and saved.raw["live_first_seen"] == summary.session
    assert {c.doc_id for c in repo.chunks} == set(summary.doc_ids)  # 청크(임베딩 대상)도 저장
    # 영문 키워드는 OpenAlex, 국문은 ScienceON·NTIS
    assert srcs[2].calls[0][0][0] == "train delay"
    assert srcs[0].calls[0][0] == ["열차 지연 예측", "운행 데이터", "머신러닝"]
    assert all(r.status == "ok" and r.count == 1 and r.new == 1 for r in summary.sources)


async def test_per_source_timeout_skips_only_that_source():
    slow = FakeSource("ntis", "ko", [_doc("ntis:P1")], delay=0.5)
    live = _live(_three(ntis=slow), cfg=_cfg(per_source_timeout_seconds=0.05))
    summary = await live.prepare("u1", _req())
    by = {r.source: r for r in summary.sources}
    assert by["ntis"].status == "timeout" and by["ntis"].notice
    assert by["scienceon"].status == "ok" and by["openalex"].status == "ok"
    assert summary.status == "partial"
    assert "ntis:P1" not in summary.doc_ids


async def test_overall_timeout():
    slow = FakeSource("openalex", "en", [_doc("openalex:W1")], delay=0.5)
    live = _live(
        _three(openalex=slow),
        cfg=_cfg(per_source_timeout_seconds=5.0, overall_timeout_seconds=0.1),
    )
    summary = await live.prepare("u1", _req())
    assert {r.source: r.status for r in summary.sources}["openalex"] == "timeout"


async def test_one_source_failing_keeps_others():
    broken = FakeSource("scienceon", "ko", error=RuntimeError("https://x?key=SECRET"))
    live = _live(_three(scienceon=broken))
    summary = await live.prepare("u1", _req())
    by = {r.source: r for r in summary.sources}
    assert by["scienceon"].status == "error" and by["scienceon"].notice is None
    assert "ntis:P1" in summary.doc_ids and "openalex:W1" in summary.doc_ids
    assert "SECRET" not in json.dumps(summary.payload(), ensure_ascii=False)


async def test_ntis_ip_block_recorded_then_skipped(tmp_path: Path):
    blocked = FakeSource("ntis", "ko", error=SourceIpBlocked("NTIS 오류: 접근 허용 IP가 아닙니다."))
    availability = FileSourceAvailability(tmp_path / "availability.json")
    live = _live(_three(ntis=blocked), availability=availability)
    first = await live.prepare("u1", _req())
    ntis = {r.source: r for r in first.sources}["ntis"]
    assert ntis.status == "ip_blocked" and "등록 IP" in (ntis.notice or "")
    assert availability.notice("ntis") == ntis.notice  # 웹 자료원 상태와 같은 문구
    assert first.status == "partial"
    # 다른 입력의 새 세션 — 최근 기록이 있으면 NTIS 를 호출하지 않는다
    second = await live.prepare("u1", _req(goal="다른 목표 문장"))
    assert {r.source: r.status for r in second.sources}["ntis"] == "ip_blocked"
    assert len(blocked.calls) == 1


async def test_ip_block_rechecked_after_window(tmp_path: Path):
    availability = FileSourceAvailability(tmp_path / "a.json", clock=lambda: 1000.0)
    availability.record(
        "ntis", "현재 IP 1.2.3.4 가 NTIS 등록 IP 에 없습니다. 활용신청에 추가하세요"
    )
    ntis = FakeSource("ntis", "ko", [_doc("ntis:P1", doc_type="rnd_project")])
    live = _live(
        _three(ntis=ntis),
        availability=availability,
        cfg=_cfg(ip_block_recheck_minutes=10),
        wall_clock=lambda: 1000.0 + 11 * 60,
    )
    summary = await live.prepare("u1", _req())
    assert {r.source: r.status for r in summary.sources}["ntis"] == "ok"
    assert availability.notice("ntis") is None  # 성공하면 안내를 지운다


async def test_dedupe_across_db_and_sources():
    repo = IdentityRepo()
    stored = _doc("scienceon:JAKO1", title="Track circuit fault diagnosis", doi="10.1/abc")
    repo.seed(
        [stored],
        [Chunk(chunk_id="scienceon:JAKO1#0", doc_id="scienceon:JAKO1", ordinal=0, text="x")],
    )
    same_db = _doc("openalex:W9", title="Another title", doi="10.1/ABC", lang="en")
    ntis_report = _doc(
        "ntis:R1", doc_type="report", title="궤도 회로 진단 보고서", raw={"project_no": "P-1"}
    )
    sci_report = _doc(
        "scienceon:TRKO1",
        doc_type="internal_report",
        title="궤도 회로 진단 보고서",
        raw={"project_no": "P1"},
    )
    srcs = _three(
        openalex=FakeSource("openalex", "en", [same_db]),
        ntis=FakeSource("ntis", "ko", [ntis_report]),
        scienceon=FakeSource(
            "scienceon",
            "ko",
            [
                sci_report,
                _doc("scienceon:JAKO1", doi="10.1/abc", title="Track circuit fault diagnosis"),
            ],
        ),
    )
    live = _live(srcs, repo=repo)
    summary = await live.prepare("u1", _req())
    assert "openalex:W9" not in repo.docs  # DB 의 같은 DOI 문서로 이어진다
    assert "scienceon:TRKO1" not in repo.docs  # NTIS 보고서와 같은 보고서
    assert summary.doc_ids == ["ntis:R1", "scienceon:JAKO1"]
    by = {r.source: r for r in summary.sources}
    assert by["openalex"].count == 1 and by["openalex"].new == 0
    assert by["scienceon"].new == 0 and by["ntis"].new == 1
    assert repo.docs["scienceon:JAKO1"].raw.get("live") is None  # 기존 문서는 덮어쓰지 않는다


async def test_cache_hit_within_ttl_and_miss_after(tmp_path: Path):
    now = [0.0]
    cache = FileCache(tmp_path / "cache", ttl_sec=24 * 3600, clock=lambda: now[0])
    srcs = _three()
    llm = FakeLLM([KW_JSON, KW_JSON, KW_JSON])
    live = _live(srcs, cache=cache, llm=llm)
    await live.prepare("u1", _req())
    now[0] = 23 * 3600
    second = await live.prepare("u2", _req())  # 다른 사용자, 같은 키워드 → 캐시
    assert all(r.cached for r in second.sources)
    assert sorted(second.doc_ids) == ["ntis:P1", "openalex:W1", "scienceon:A1"]
    assert [len(s.calls) for s in srcs] == [1, 1, 1]
    assert len(llm.calls) == 1  # 같은 입력의 키워드도 캐시 (Argon 호출 절약)
    now[0] = 25 * 3600
    third = await live.prepare("u3", _req())
    assert not any(r.cached for r in third.sources)
    assert [len(s.calls) for s in srcs] == [2, 2, 2]
    assert len(llm.calls) == 2
    # 캐시 파일에 사람 이름·키가 없다 — 정규화(이름 제거)된 문서만
    values = [
        json.loads(f.read_text(encoding="utf-8"))["value"]
        for f in (tmp_path / "cache").glob("*.json")
    ]
    assert sum(isinstance(v, dict) for v in values) == 1  # 키워드
    docs = [v for v in values if isinstance(v, list)]
    assert len(docs) == 3  # 자료원별 검색 결과
    for value in docs:
        for d in value:
            assert d["authors"] == [] and d["raw"]["live"] is True


async def test_same_session_reused_and_disabled_is_old_behaviour():
    srcs = _three()
    live = _live(srcs)
    a = live.start("u1", _req())
    b = live.start("u1", _req())
    assert a is b
    await live.wait(a)
    assert live.find("u1", _req()) is a
    off = _live(_three(), cfg=_cfg(enabled=False))
    assert off.start("u1", _req()) is None
    assert (await off.prepare("u1", _req())).status == "off"
    every_off = _live(
        _three(),
        cfg=_cfg(
            sources={n: LiveSourceConfig(enabled=False) for n in ("scienceon", "ntis", "openalex")}
        ),
    )
    assert (await every_off.prepare("u1", _req())).status == "off"


async def test_wait_returns_pending_then_done():
    slow = FakeSource("openalex", "en", [_doc("openalex:W1")], delay=0.3)
    live = _live(_three(openalex=slow))
    session = live.start("u1", _req())
    early = await live.wait(session, timeout=0.01)
    assert early.status == "pending" and early.doc_ids == []
    late = await live.wait(session)
    assert late.status == "done"


async def test_keywords_fallback_chain():
    req = _req()

    # Argon 예산 소진 → 로컬 → 성공
    class Exhausted:
        async def complete(self, *a, **k):
            raise BudgetExhausted("limit")

    local = FakeLLM([KW_JSON])
    kw = await LiveKeywordMaker(primary=Exhausted(), local=local)(req)
    assert kw.origin == "local" and kw.ko[0] == "열차 지연 예측"

    # 둘 다 실패(형식 오류·시간 초과) → 규칙
    class Slow:
        async def complete(self, *a, **k):
            await asyncio.sleep(1)
            return KW_JSON

    kw = await LiveKeywordMaker(primary=FakeLLM(["not json"]), local=Slow(), local_timeout=0.01)(
        req
    )
    assert kw.origin == "rule" and kw.ko
    # 개인정보는 LLM 입력에서 빠진다
    llm = FakeLLM([KW_JSON])
    await LiveKeywordMaker(primary=llm)(_req(current_state="담당자 김철수 010-2222-3333"))
    assert "010-2222-3333" not in llm.calls[0] and "김철수" not in llm.calls[0]


async def test_missing_source_and_no_english_keywords():
    llm = FakeLLM([json.dumps({"ko": ["열차 지연", "예측", "운행"], "en": []}, ensure_ascii=False)])
    srcs = [FakeSource("scienceon", "ko", [_doc("scienceon:A1")]), FakeSource("openalex", "en")]
    live = _live(srcs, llm=llm)
    summary = await live.prepare("u1", _req(title_hint="열차 운행 지연"))
    by = {r.source: r for r in summary.sources}
    assert by["ntis"].status == "error"  # 키 없음 등으로 조립되지 않은 자료원
    assert by["openalex"].status == "ok" and by["openalex"].count == 0 and by["openalex"].notice
    assert srcs[1].calls == []


async def test_guest_scope_unchanged_live_public_visible():
    repo = IdentityRepo()
    internal = _doc("own:X1", source="own", doc_type="internal_report", visibility="internal")
    repo.seed(
        [internal], [Chunk(chunk_id="own:X1#0", doc_id="own:X1", ordinal=0, text="열차 지연")]
    )
    live = _live(_three(), repo=repo)
    await live.prepare("guest-key", _req())
    guest = PublicOnlyRepository(repo)
    assert await guest.get_document("own:X1") is None  # internal 은 여전히 제외
    got = await guest.get_document("openalex:W1")
    assert got is not None and got.visibility == "public"


async def test_sqlite_find_identities_and_live_upsert(tmp_path: Path):
    from rra.adapters.persistence.sqlite_repo import SQLiteDocumentRepository
    from tests.fakes import DeterministicEmbedding

    repo = SQLiteDocumentRepository(tmp_path / "t.sqlite", DeterministicEmbedding())
    stored = _doc(
        "scienceon:JAKO1",
        title="Track Circuit: Fault Diagnosis",
        doi="10.1/abc",
        pub_date=date(2023, 1, 1),
    )
    report = _doc(
        "scienceon:TRKO1",
        doc_type="internal_report",
        title="궤도 회로 진단 보고서",
        raw={"project_no": "P1"},
        pub_date=date(2022, 1, 1),
    )
    await repo.upsert([stored, report], [])
    found = await repo.find_identities(
        [
            _doc("openalex:W1", title="x" * 10, doi="10.1/ABC"),
            _doc("openalex:W2", title="track circuit fault diagnosis", pub_date=date(2023, 3, 1)),
            _doc("openalex:W3", title="track circuit fault diagnosis", pub_date=date(2019, 3, 1)),
            _doc(
                "ntis:R1",
                doc_type="report",
                title="궤도 회로 진단 보고서",
                raw={"project_no": "P1"},
                pub_date=date(2022, 6, 1),
            ),
        ]
    )
    assert found == {
        "openalex:W1": "scienceon:JAKO1",
        "openalex:W2": "scienceon:JAKO1",
        "ntis:R1": "scienceon:TRKO1",
    }
    live = _live(_three(), repo=repo)
    summary = await live.prepare("u1", _req())
    assert summary.status == "done"
    saved = await repo.get_document("openalex:W1")
    assert saved is not None and saved.raw["live"] is True and saved.visibility == "public"
    hits = await repo.hybrid_search(["열차 지연 예측"], k=10)
    assert {"openalex:W1", "ntis:P1", "scienceon:A1"} <= {c.doc_id for c in hits}
    repo.close()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """이 파일의 테스트는 네트워크를 쓰지 않는다 — httpx 전송을 막아 둔다."""
    import httpx

    async def deny(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(httpx.AsyncClient, "send", deny)


async def test_partial_session_retried_after_five_minutes_and_store_failure():
    now = [0.0]
    broken = FakeSource("scienceon", "ko", error=RuntimeError("down"))
    live = _live(_three(scienceon=broken), clock=lambda: now[0])
    first = await live.prepare("u1", _req())
    assert first.status == "partial"
    now[0] = 60
    assert live.start("u1", _req()) is live.find("u1", _req())  # 5분 안 — 같은 세션
    assert len(broken.calls) == 1
    now[0] = 301
    again = await live.prepare("u1", _req())
    assert again.session == first.session and len(broken.calls) == 2  # 다시 검색

    class FailingRepo(IdentityRepo):
        async def upsert(self, docs, chunks):
            raise RuntimeError("disk full")

    failing = _live(_three(), repo=FailingRepo())
    summary = await failing.prepare("u1", _req())
    assert summary.doc_ids == [] and summary.status == "partial"
    assert all(r.status == "error" and r.notice for r in summary.sources)
