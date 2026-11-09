"""② 스위치 on 동작 (레인 E, ADR 0059) — facets: 축별 질의 RRF 검색·판정 facet_overlap·REST 행
칸, idf_weighting: 가중 합 판정, synonyms: 질의 확장 규칙만. FakeLLM·가짜 저장소만. 차단 규칙은
바뀌지 않는다."""

from __future__ import annotations

import json

from rra.application.usecases.facet_split import FacetSplitter
from rra.application.usecases.judge_sameness import FACET_SYSTEM, SameJudge
from rra.domain.models.facets import Facets
from rra.domain.rules.idf import IdfWeightingRule, IdfWeights
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap_switches import OverlapSwitches
from rra.entrypoints.views import alerts_payload
from tests.application import overlap_switch_harness as h
from tests.fakes import FakeLLM

PIGEON_NAME, PIGEON = "pilot/pigeon", h.PIGEON
FACETS_ON = OverlapSwitches(facets=True)


class RecordingLLM(FakeLLM):
    def __init__(self, answer):
        super().__init__([answer])
        self.systems: list[str] = []

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        self.systems.append(system or "")
        return await super().complete(
            prompt, system=system, max_tokens=max_tokens, json_mode=json_mode
        )


async def _split(req, core):
    return Facets(
        target="승강장 캐노피", problem="비둘기 침입 오염", method="비살상 퇴치 장치", source="rule"
    )


async def test_facets_on_searches_each_facet_query_and_fuses_without_changing_pool_size():
    docs = h.corpus(PIGEON_NAME, PIGEON)
    pre, repo, llm = h.build(PIGEON, docs, switches=FACETS_ON, facet_split=_split)
    off_pre, off_repo, _ = h.build(PIGEON, docs)
    req = h.request_of(PIGEON)
    on = await pre.rule_stage(req)
    off = await off_pre.rule_stage(req)
    queries = {c[1]["text"] for c in repo.calls if c[0] == "find_similar"}
    assert {"승강장 캐노피", "비둘기 침입 오염", "비살상 퇴치 장치"} <= queries
    assert on.facets is not None and on.facets.source == "rule" and off.facets is None
    # 정답 문서는 그대로 상위·차단 — 축별 검색은 e5 후보 풀에만 영향(차단 규칙은 같다). 가짜
    # 저장소는 토큰 겹침이 0 인 문서를 돌려주지 않아 교란 문서가 풀에서 빠질 수 있다(실제 e5 는 늘
    # k 건을 준다).
    assert on.alerts[0].doc_id == off.alerts[0].doc_id == "own:pigeon-net"
    assert on.alerts[0].blocking and off.alerts[0].blocking
    assert {a.doc_id for a in on.alerts} <= {a.doc_id for a in off.alerts}
    assert len(on.alerts) <= len(off.alerts) <= pre.k
    # reranker 입력 수(= 검색 상한)는 종전과 같다
    on_k = [c[1]["k"] for c in repo.calls if c[0] == "find_similar"]
    off_k = [c[1]["k"] for c in off_repo.calls if c[0] == "find_similar"]
    assert sorted(set(on_k)) == sorted(set(off_k))


async def test_facets_on_requests_facet_overlap_and_rest_row_carries_it():
    answer = json.dumps(
        {
            "items": [
                {
                    "doc_id": "own:pigeon-net",
                    "verdict": "same",
                    "reason": "같음",
                    "facet_overlap": {"target": 2, "problem": 2, "method": 1, "place": 7},
                },
                {"doc_id": "alio:sum-pigeon-clean", "verdict": "different", "reason": "다름"},
            ]
        },
        ensure_ascii=False,
    )
    llm = RecordingLLM(answer)
    docs = h.corpus(PIGEON_NAME, PIGEON)
    pre, repo, _ = h.build(PIGEON, docs, switches=FACETS_ON, facet_split=_split)
    pre.same_judge = SameJudge(primary=llm, repo=repo, facets=True)
    result = await pre.run(h.request_of(PIGEON))
    assert FACET_SYSTEM.strip() in llm.systems[0]
    by = {a.doc_id: a for a in result.alerts}
    fo = by["own:pigeon-net"].facet_overlap
    assert fo is not None and fo.as_dict() == {"target": 2, "problem": 2, "method": 1, "place": 0}
    others = [a for a in result.alerts if a.doc_id != "own:pigeon-net"]
    assert all(a.facet_overlap is None for a in others)  # 선택 항목 — 없으면 None
    rows = {r["doc_id"]: r for r in alerts_payload(result.alerts)["alerts"]}
    assert rows["own:pigeon-net"]["facet_overlap"] == {
        "target": 2,
        "problem": 2,
        "method": 1,
        "place": 0,
    }
    assert all("facet_overlap" not in rows[a.doc_id] for a in others)
    assert by["own:pigeon-net"].blocking and not any(a.blocking for a in others)  # 차단 규칙 그대로


async def test_facet_split_failure_falls_back_to_single_query():
    async def boom(req, core):
        raise RuntimeError("x")

    docs = h.corpus(PIGEON_NAME, PIGEON)
    pre, repo, _ = h.build(PIGEON, docs, switches=FACETS_ON, facet_split=boom)
    off_pre, off_repo, _ = h.build(PIGEON, docs)
    req = h.request_of(PIGEON)
    assert [a.doc_id for a in (await pre.rule_stage(req)).alerts] == [
        a.doc_id for a in (await off_pre.rule_stage(req)).alerts
    ]
    assert repo.calls == off_repo.calls


async def test_facet_splitter_prefers_local_json_then_rule():
    good = FakeLLM(
        [
            json.dumps(
                {"facets": {"target": "캐노피", "problem": "비둘기", "method": "", "place": ""}}
            )
        ]
    )
    req = h.request_of(PIGEON)
    f = await FacetSplitter(local=good, keyword_rule=KeywordRule())(req, ["캐노피 비둘기"])
    assert f.source == "local" and f.target == "캐노피" and f.method == ""
    bad = FakeLLM(['{"facets": {"target": "x"}}'])  # 축 4개가 아님 → 규칙
    f = await FacetSplitter(local=bad, keyword_rule=KeywordRule())(
        req, ["승강장 캐노피", "비둘기 퇴치"]
    )
    assert f.source == "rule" and "캐노피" in f.target and "퇴치" in f.method
    f = await FacetSplitter(local=None, keyword_rule=KeywordRule())(req, None)  # 핵심어 없음 → 질의
    assert f.source == "rule" and not f.is_empty()


async def test_idf_weighting_uses_weighted_sum_only_when_switch_on():
    docs = h.corpus(PIGEON_NAME, PIGEON)
    terms = ["지상역", "승강장", "캐노피", "비둘기", "침입", "비살상", "퇴치", "장치", "개발"]
    # 모든 핵심어가 매우 흔한 낱말(idf 0.01)이고 "비둘기" 만 드물면: 비둘기가 없는 문서는 가중 합이
    # 모자란다
    idf = IdfWeights(values={**{t: 0.01 for t in terms}, "비둘기": 5.0}, documents=100, max_idf=5.0)
    pre, _, _ = h.build(
        PIGEON,
        docs,
        switches=OverlapSwitches(idf_weighting=True),
        idf=idf,
        idf_rule=IdfWeightingRule(min_weight_ratio=1.0),
    )
    on = await pre.rule_stage(h.request_of(PIGEON))
    by = {a.doc_id: a for a in on.alerts}
    assert by["own:pigeon-net"].blocking  # 비둘기 포함 → 가중 합 충분
    # 스위치가 꺼져 있으면 idf 를 줘도 쓰지 않는다
    pre_off, _, _ = h.build(PIGEON, docs, idf=idf)
    off = await pre_off.rule_stage(h.request_of(PIGEON))
    assert [a.blocking for a in off.alerts] == [a.blocking for a in on.alerts]
    assert off.facets is None
