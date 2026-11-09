"""새로움 확인(WideNoveltyCheck)·유추 검색(ProblemAnalogySearch) — 가짜 자료원·메모리
저장소, 네트워크 없음 (ADR 0057, 계약 docs/contracts/novel-recommend.md 3.1·3.2·7)."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from rra.application.usecases.live_search import LiveKeywordMaker, LiveSearch
from rra.application.usecases.novel_contract import AnalogySearch, NoveltyCheck
from rra.application.usecases.novelty import (
    NOTE_STORED_ONLY,
    ProblemAnalogySearch,
    ProblemKeywords,
    WideNoveltyCheck,
    precheck_rule_check,
)
from rra.domain.models import Document, OverlapAlert, ProposalRequest
from rra.domain.models.live_search import LiveKeywords, LiveSearchConfig
from rra.domain.models.novel import COVERAGE_NOTE
from rra.domain.rules.live_search import match_existing
from rra.domain.rules.novelty import AnalogySettings, LiveWidening
from rra.domain.rules.relevance import RelevanceFloor
from tests.fakes import FakeLLM, FakeTaskRunner, InMemoryRepository

KW_JSON = json.dumps(
    {
        "ko": ["철도역사 비둘기 퇴치", "승강장 조류 침입 방지", "비둘기 분변"],
        "en": ["pigeon deterrent railway station", "bird intrusion prevention"],
    },
    ensure_ascii=False,
)


def _req(**kw) -> ProposalRequest:
    base = {
        "title_hint": "철도역사 비둘기 침입 방지",
        "current_state": "승강장 지붕에 비둘기가 침입해 분변 피해가 크다",
        "root_cause": "역사 구조물에 둥지를 틀기 쉽다",
        "limitation": "그물 설치만으로는 퇴치 효과가 짧다",
        "goal": "비둘기 침입을 막는 퇴치 기술",
    }
    return ProposalRequest(**{**base, **kw})


def _doc(doc_id: str, title: str = "", **kw) -> Document:
    base = {
        "source": doc_id.split(":")[0],
        "doc_type": "paper",
        "title": title or f"{doc_id} 조류 침입 방지",
        "abstract": "조류 침입을 막는다.",
        "text_basis": "abstract",
    }
    return Document(doc_id=doc_id, **{**base, **kw})


def _alert(doc_id: str, *, blocking: bool = True) -> OverlapAlert:
    return OverlapAlert(
        doc_id=doc_id, title=doc_id, tier="national_rnd", similarity=0.9, blocking=blocking
    )


class Repo(InMemoryRepository):
    async def find_identities(self, docs):
        return match_existing(docs, list(self.docs.values()))


class Source:
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


class Availability:
    """최근 IP 거부가 기록된 자료원 (TimedAvailabilityPort)."""

    def __init__(self, blocked=()):
        self.blocked = {s: "IP 미등록" for s in blocked}
        self.at = time.time()

    def record(self, source, notice):
        if notice is None:
            self.blocked.pop(source, None)
        else:
            self.blocked[source] = notice

    def notice(self, source):
        return self.blocked.get(source)

    def notices(self):
        return dict(self.blocked)

    def recorded_at(self, source):
        return self.at if source in self.blocked else None


def _base_cfg(**kw) -> LiveSearchConfig:
    base = {
        "enabled": True,
        "per_source_timeout_seconds": 1.0,
        "overall_timeout_seconds": 2.0,
        "wait_seconds": 3.0,
    }
    return LiveSearchConfig(**{**base, **kw})


def _wide_live(sources, *, repo, availability=None, base=None, widening=None):
    cfg = (
        widening
        or LiveWidening(
            per_source_timeout_seconds=0.3, overall_timeout_seconds=0.5, wait_seconds=2.0
        )
    ).live_config(base or _base_cfg())
    return LiveSearch(
        cfg,
        repo,
        FakeTaskRunner(),
        sources={s.source: s for s in sources},
        keywords=LiveKeywordMaker(primary=FakeLLM([KW_JSON] * 5)),
        availability=availability,
    )


class RuleCheck:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[list[str] | None] = []

    async def __call__(self, req, core):
        self.calls.append(core)
        return list(self.rows)


def _seed_projects(repo: Repo) -> None:
    repo.seed(
        [_doc("own:p1", doc_type="internal_report", visibility="internal"), _doc("ntis:p0")],
        [],
    )


# ── 새로움 확인 ────────────────────────────────────────────
async def test_contract_protocols():
    repo = Repo()
    check = WideNoveltyCheck(repo, rule_check=RuleCheck([]))
    search = ProblemAnalogySearch(repo)
    assert isinstance(check, NoveltyCheck) and isinstance(search, AnalogySearch)


async def test_no_live_coverage_is_stored_only_and_honest():
    repo = Repo()
    _seed_projects(repo)
    rule = RuleCheck([_alert("ntis:new")])
    check = WideNoveltyCheck(
        repo, rule_check=rule, live=None, stored_sources=["own", "alio", "ntis", "g2b"]
    )
    out = await check(_req(), [])
    cov = out.coverage
    assert cov.live is False and cov.note == NOTE_STORED_ONLY
    # 문서가 없는 자료원(alio·g2b)은 확인한 범위에 넣지 않는다
    assert cov.searched == ["own", "ntis"]
    assert cov.searched_labels == ["사내 과제 현황", "NTIS 국가R&D 과제"]
    assert cov.unavailable == [
        {"source": "scienceon", "status": "off"},
        {"source": "ntis", "status": "off"},
        {"source": "openalex", "status": "off"},
        {"source": "kipris_kr", "status": "off"},
    ]
    # 새 자료가 없으면 판정을 다시 돌리지 않는다 — 되돌림 없음
    assert out.new_alerts == [] and rule.calls == []


async def test_live_disabled_like_fake_mode_never_raises():
    repo = Repo()
    _seed_projects(repo)
    live = _wide_live([Source("scienceon", "ko")], repo=repo, base=_base_cfg(enabled=False))
    check = WideNoveltyCheck(repo, rule_check=RuleCheck([]), live=live, stored_sources=["ntis"])
    out = await check(_req(), [])
    assert out.coverage.live is False and out.coverage.searched == ["ntis"]
    assert {u["status"] for u in out.coverage.unavailable} == {"off"}


async def test_widened_search_ip_block_timeout_and_no_key():
    repo = Repo()
    _seed_projects(repo)
    ntis = Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")])
    scienceon = Source("scienceon", "ko", [_doc("scienceon:A1")])
    live = _wide_live([ntis, scienceon], repo=repo, availability=Availability(["ntis"]))
    check = WideNoveltyCheck(repo, rule_check=RuleCheck([]), live=live, stored_sources=["own"])
    out = await check(_req(), [], core_keywords=["비둘기 퇴치"])
    cov = out.coverage
    assert ntis.calls == []  # IP 거부가 최근 기록됨 → 호출하지 않는다
    assert cov.live is True and cov.note == COVERAGE_NOTE
    assert cov.searched == ["own", "scienceon"]  # 응답이 온 자료원만
    assert {"source": "ntis", "status": "ip_blocked"} in cov.unavailable
    assert {"source": "openalex", "status": "no_key"} in cov.unavailable  # 어댑터 없음(키 없음)
    # 넓힌 질의: 키워드 5개까지 보낼 수 있고 자료원당 상한은 넓힌 값
    queries, limit = scienceon.calls[0]
    assert len(queries) == 3 and limit == 30  # 키워드 3개(가짜 LLM), top_n 기본


async def test_timeout_and_error_statuses():
    repo = Repo()
    live = _wide_live(
        [
            Source("scienceon", "ko", [_doc("scienceon:A1")], delay=1.0),
            Source("ntis", "ko", error=RuntimeError("boom")),
            Source("openalex", "en", [_doc("openalex:W1", "Bird intrusion", lang="en")]),
        ],
        repo=repo,
    )
    check = WideNoveltyCheck(repo, rule_check=RuleCheck([]), live=live, stored_sources=["own"])
    cov = (await check(_req(), [])).coverage
    assert cov.searched == ["openalex"]  # 저장 자료(own) 문서 없음 → 넣지 않음
    assert {"source": "scienceon", "status": "timeout"} in cov.unavailable
    assert {"source": "ntis", "status": "error"} in cov.unavailable
    assert cov.live is True


async def test_unfinished_live_search_counts_as_timeout_and_is_not_memoized():
    repo = Repo()
    slow = Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")], delay=0.3)
    widening = LiveWidening(
        per_source_timeout_seconds=1.0, overall_timeout_seconds=1.0, wait_seconds=0.05
    )
    live = _wide_live([slow], repo=repo, widening=widening)
    rule = RuleCheck([_alert("ntis:P9")])
    check = WideNoveltyCheck(repo, rule_check=rule, live=live, stored_sources=["ntis"])
    out = await check(_req(), [])
    assert out.coverage.live is False and out.coverage.note == NOTE_STORED_ONLY
    assert {"source": "ntis", "status": "timeout"} in out.coverage.unavailable
    assert out.new_alerts == [] and rule.calls == []
    await asyncio.sleep(0.4)  # 검색이 끝난 뒤 다시 부르면 이번에는 확인한다 (메모하지 않았음)
    again = await check(_req(), [])
    assert again.coverage.live is True and [a.doc_id for a in again.new_alerts] == ["ntis:P9"]


async def test_widening_sends_more_queries():
    repo = Repo()
    src = Source("scienceon", "ko", [_doc("scienceon:A1")])
    kw = json.dumps(
        {"ko": ["가 나", "다 라", "마 바", "사 아", "자 차"], "en": []}, ensure_ascii=False
    )
    cfg = LiveWidening(max_queries=5, wait_seconds=2.0).live_config(_base_cfg())
    live = LiveSearch(
        cfg,
        repo,
        FakeTaskRunner(),
        sources={"scienceon": src},
        keywords=LiveKeywordMaker(primary=FakeLLM([kw])),
    )
    await live.prepare("u", _req())
    assert len(src.calls[0][0]) == 5
    narrow = LiveSearch(
        _base_cfg(),
        Repo(),
        FakeTaskRunner(),
        sources={"scienceon": (src2 := Source("scienceon", "ko", [_doc("scienceon:A1")]))},
        keywords=LiveKeywordMaker(primary=FakeLLM([kw])),
    )
    await narrow.prepare("u", _req())
    assert len(src2.calls[0][0]) == 3  # 기존 설정(max_queries 기본 3)은 그대로


async def test_new_blocking_alert_reverts_and_keeps_original_out():
    repo = Repo()
    _seed_projects(repo)
    live = _wide_live([Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")])], repo=repo)
    rule = RuleCheck([_alert("ntis:p0"), _alert("ntis:P9"), _alert("ntis:near", blocking=False)])
    check = WideNoveltyCheck(repo, rule_check=rule, live=live, stored_sources=["ntis"])
    out = await check(_req(), [_alert("ntis:p0", blocking=False)], core_keywords=["비둘기 퇴치"])
    assert [a.doc_id for a in out.new_alerts] == ["ntis:P9"]  # 새로 걸린 차단 행만
    assert rule.calls == [["비둘기 퇴치"]]  # ② 와 같은 핵심어로
    assert "ntis:P9" in repo.docs and repo.docs["ntis:P9"].raw.get("live") is True


async def test_public_account_drops_internal_new_alerts():
    repo = Repo()
    _seed_projects(repo)  # own:p1 internal
    live = _wide_live([Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")])], repo=repo)
    rows = [_alert("own:p1"), _alert("ntis:P9")]
    public = WideNoveltyCheck(repo, rule_check=RuleCheck(rows), live=live, include_internal=False)
    assert [a.doc_id for a in (await public(_req(), [])).new_alerts] == ["ntis:P9"]
    staff = WideNoveltyCheck(repo, rule_check=RuleCheck(rows), live=live)
    assert [a.doc_id for a in (await staff(_req(), [])).new_alerts] == ["own:p1", "ntis:P9"]


async def test_rule_check_failure_does_not_revert():
    repo = Repo()
    live = _wide_live([Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")])], repo=repo)

    async def broken(req, core):
        raise RuntimeError("x")

    out = await WideNoveltyCheck(repo, rule_check=broken, live=live)(_req(), [])
    assert out.new_alerts == [] and out.coverage.live is True


async def test_same_input_reuses_outcome():
    repo = Repo()
    src = Source("ntis", "ko", [_doc("ntis:P9", doc_type="rnd_project")])
    live = _wide_live([src], repo=repo)
    rule = RuleCheck([_alert("ntis:P9")])
    check = WideNoveltyCheck(repo, rule_check=rule, live=live)
    first = await check(_req(), [], core_keywords=["a"])
    second = await check(_req(), [], core_keywords=["a"])
    assert first is second and len(rule.calls) == 1 and len(src.calls) == 1
    # 입력이 다르면 검색은 다시 하지만, 받은 문서가 모두 DB 에 이미 있으면(새 문서 0) ② 가 이미 본
    # 범위라 규칙 판정은 다시 돌리지 않는다 (2026-11-09 응답 시간)
    out = await check(_req(goal="다른 목표"), [], core_keywords=["a"])
    assert len(src.calls) == 2 and len(rule.calls) == 1 and out.coverage.live is True
    # 새 문서가 들어오면 다시 판정한다
    src.docs.append(_doc("ntis:P10", doc_type="rnd_project"))
    await check(_req(goal="또 다른 목표"), [], core_keywords=["a"])
    assert len(rule.calls) == 2


async def test_precheck_rule_check_uses_rule_stage_without_research():
    seen = {}

    class Precheck:
        async def rule_stage(self, req, **kw):
            seen.update(kw)

            class R:
                alerts = [_alert("ntis:X")]

            return R()

    rows = await precheck_rule_check(Precheck())(_req(), ["k"])
    assert [a.doc_id for a in rows] == ["ntis:X"]
    assert seen == {"core_keywords": ["k"], "research": False}


# ── 유추 검색 ──────────────────────────────────────────────
def _analogy_docs() -> list[tuple[Document, float]]:
    return [
        (_doc("scienceon:R1", "도시철도 승강장 비둘기 퇴치"), 0.95),  # 철도 — 뺀다
        (_doc("own:O1", "비둘기 침입 방지 사내 과제"), 0.94),  # 철도 전용 자료원 — 뺀다
        (
            _doc(
                "scienceon:K1",
                "공항 조류 침입 방지를 위한 퇴치 장치",
                raw={"journal": "한국항공운항학회지"},
                url="https://example.org/k1",
                pub_date=None,
            ),
            0.9,
        ),
        (_doc("scienceon:K2", "농가 축사 소독 체계", abstract="소독"), 0.88),  # 문제어 없음
        (
            _doc(
                "openalex:W1",
                "Bird strike prevention at airports",
                abstract="Deterrents reduce bird intrusion.",
                lang="en",
                raw={"venue": "Journal of Wildlife Management"},
            ),
            0.82,
        ),
        (_doc("scienceon:K3", "건물 외벽 비둘기 침입 방지망", visibility="internal"), 0.81),
        (_doc("scienceon:K4", "과수원 조류 퇴치 음향 장치"), 0.79),  # 하한과 같음 — 남긴다
        (_doc("scienceon:K5", "양식장 조류 퇴치"), 0.7899),  # 하한 아래
    ]


async def test_analogies_exclude_rail_floor_and_label():
    repo = Repo()
    repo.similar = _analogy_docs()
    search = ProblemAnalogySearch(repo)
    out = await search(_req(), core_keywords=["철도역사 비둘기 퇴치", "승강장 조류 침입 방지"])
    ids = [a.doc_id for a in out]
    assert ids == ["scienceon:K1", "openalex:W1", "scienceon:K3", "scienceon:K4"]
    k1 = out[0]
    assert k1.domain_label == "학술지 한국항공운항학회지"
    assert k1.why_relevant.startswith("철도 밖에서 같은 문제(") and "침입" in k1.why_relevant
    assert k1.source_label == "ScienceON 국내 논문·보고서" and k1.url == "https://example.org/k1"
    assert k1.live is False and k1.similarity == 0.9
    assert out[1].domain_label == "게재처 Journal of Wildlife Management"
    # 저장 자료 질의 — 장소·철도 말 없이 문제어만, 철도 전용 자료원은 검색 대상에서 뺀다
    call = next(c for name, c in repo.calls if name == "find_similar")
    assert "비둘기" in call["text"] and "침입" in call["text"]
    for word in ("철도", "역사", "승강장"):
        assert word not in call["text"]
    assert "own" not in call["sources"]


async def test_analogies_public_account_drops_internal_and_caps_five():
    repo = Repo()
    many = [
        (_doc(f"scienceon:M{i}", f"공항 {i} 조류 침입 방지"), 0.9 - i * 0.001) for i in range(8)
    ]
    repo.similar = [*_analogy_docs(), *many]
    out = await ProblemAnalogySearch(repo, include_internal=False)(_req())
    assert len(out) == 5
    assert "scienceon:K3" not in [a.doc_id for a in out]


async def test_analogy_floor_follows_evidence_floor():
    repo = Repo()
    repo.similar = _analogy_docs()
    strict = ProblemAnalogySearch(repo, floor=RelevanceFloor(min_similarity=0.85))
    assert [a.doc_id for a in await strict(_req())] == ["scienceon:K1"]


async def test_analogy_live_uses_problem_queries_and_marks_live():
    repo = Repo()
    live_doc = _doc(
        "openalex:W7", "Pigeon deterrent systems for buildings", lang="en", abstract="pigeon"
    )
    repo.similar = [(live_doc, 0.86), *_analogy_docs()]
    ko = Source("scienceon", "ko", [_doc("scienceon:K1", "공항 조류 침입 방지")])
    en = Source("openalex", "en", [live_doc])
    maker = ProblemKeywords()
    cfg = AnalogySettings().live.live_config(_base_cfg())
    live = LiveSearch(
        cfg,
        repo,
        FakeTaskRunner(),
        sources={"scienceon": ko, "openalex": en},
        keywords=maker,
        keyword_cache=False,
    )

    async def base_keywords(req):
        return LiveKeywords(
            ko=["철도역사 비둘기 퇴치"],
            en=["pigeon deterrent railway station", "bird intrusion"],
            origin="argon",
        )

    search = ProblemAnalogySearch(
        repo, live=live, problem_keywords=maker, keyword_source=base_keywords
    )
    out = await search(_req())
    ko_queries = ko.calls[0][0]
    en_queries = en.calls[0][0]
    assert ko_queries[0] == "비둘기 퇴치"
    assert all("철도" not in q and "역사" not in q and "승강장" not in q for q in ko_queries)
    assert en_queries == ["pigeon deterrent", "bird intrusion"]
    by_id = {a.doc_id: a for a in out}
    assert by_id["openalex:W7"].live is True and by_id["scienceon:K1"].live is True
    assert by_id["openalex:W1"].live is False  # 이번 실시간 검색에서 받은 자료가 아님
    assert "pigeon" in by_id["openalex:W7"].why_relevant


async def test_analogy_live_requires_problem_keyword_instance():
    repo = Repo()
    plain = LiveSearch(_base_cfg(), repo, FakeTaskRunner(), sources={}, keywords=LiveKeywordMaker())
    with pytest.raises(ValueError):
        ProblemAnalogySearch(repo, live=plain)
    cached = LiveSearch(_base_cfg(), repo, FakeTaskRunner(), sources={}, keywords=ProblemKeywords())
    with pytest.raises(ValueError):  # keyword_cache=True 면 평소 키워드를 가져다 쓴다
        ProblemAnalogySearch(repo, live=cached)


async def test_analogy_stored_only_when_live_off_and_keyword_failure():
    repo = Repo()
    repo.similar = _analogy_docs()
    maker = ProblemKeywords()
    live = LiveSearch(
        _base_cfg(enabled=False),
        repo,
        FakeTaskRunner(),
        sources={},
        keywords=maker,
        keyword_cache=False,
    )

    async def broken(req):
        raise RuntimeError("x")

    out = await ProblemAnalogySearch(repo, live=live, keyword_source=broken)(_req())
    assert [a.doc_id for a in out][:2] == ["scienceon:K1", "openalex:W1"]
    assert all(a.live is False for a in out)


async def test_analogy_reuses_same_input():
    repo = Repo()
    repo.similar = _analogy_docs()
    search = ProblemAnalogySearch(repo)
    first = await search(_req())
    second = await search(_req())
    assert [a.doc_id for a in first] == [a.doc_id for a in second]
    # 자료원별 최소 보장(5 자료원) + 전체 1 = 6회, 두 번째는 메모 재사용이라 새 호출 없음
    calls = sum(1 for name, _ in repo.calls if name == "find_similar")
    assert calls == 1 + len(AnalogySettings().search_sources)


async def test_analogy_without_problem_terms_returns_empty():
    repo = Repo()
    repo.similar = _analogy_docs()
    req = _req(
        title_hint="철도역사 승강장",
        current_state="승강장",
        root_cause="역사",
        limitation="철도",
        goal="철도역사",
    )
    assert await ProblemAnalogySearch(repo)(req) == []
    assert not [c for c in repo.calls if c[0] == "find_similar"]


# ── LiveSearch 보조 (keywords_for·keyword_cache) ────────────
class DictCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


async def test_keywords_for_uses_cache_and_keyword_cache_flag():
    cache = DictCache()
    llm = FakeLLM([KW_JSON])
    live = LiveSearch(
        _base_cfg(),
        Repo(),
        FakeTaskRunner(),
        sources={},
        keywords=LiveKeywordMaker(primary=llm),
        cache=cache,
    )
    first = await live.keywords_for(_req())
    second = await live.keywords_for(_req())
    assert first.origin == "argon" and second == first and len(llm.calls) == 1
    # keyword_cache=False 인 인스턴스는 같은 캐시의 키워드를 읽지 않는다
    maker = ProblemKeywords()
    other = LiveSearch(
        _base_cfg(),
        Repo(),
        FakeTaskRunner(),
        sources={},
        keywords=maker,
        keyword_cache=False,
        cache=cache,
    )
    own = await other.keywords_for(_req())
    assert own.origin == "rule" and "철도역사" not in " ".join(own.ko)


async def test_analogy_per_source_floor_brings_in_a_source_crowded_out_of_the_global_top():
    """자료원별 최소 보장(2026-11-09): 전체 순위 60 안에 없던 KIPRIS 특허도 자료원별 상위로 후보에
    든다. per_source=0 이면 종전(전체 순위만)."""

    class RoutedRepo(Repo):
        async def find_similar(self, text, *, k=10, sources=None):
            self.calls.append(("find_similar", {"text": text, "k": k, "sources": sources}))
            if sources == ["kipris_kr"]:
                return [
                    (
                        _doc(
                            "kipris_kr:1020230000001",
                            "건물 외벽 조류 착좌 방지 와이어 장치",
                            source="kipris_kr",
                            doc_type="patent",
                        ),
                        0.85,
                    )
                ]
            if sources and len(sources) == 1:
                return []
            return _analogy_docs()[:k]

    repo = RoutedRepo()
    out = await ProblemAnalogySearch(repo)(_req())
    assert any(a.source == "kipris_kr" for a in out)
    repo2 = RoutedRepo()
    old = await ProblemAnalogySearch(repo2, settings=AnalogySettings(per_source=0))(_req())
    assert not any(a.source == "kipris_kr" for a in old)
    assert sum(1 for n, _ in repo2.calls if n == "find_similar") == 1


def test_unavailable_status_passes_rate_limited_through():
    from rra.application.usecases.novelty import _unavailable_status
    from rra.domain.rules.novel_recommendation import coverage_status_label

    assert _unavailable_status("rate_limited", "KIPRIS 오늘 호출 500/500 …") == "rate_limited"
    assert coverage_status_label("rate_limited") == "일일 호출 한도 초과로 확인 못 함"
