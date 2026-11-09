"""평가 어댑터 (ADR 0058) — 결과 JSON·문제 묶음(600)·캐시 재생·L0 메모리 저장소."""

from __future__ import annotations

import json
import stat
from datetime import date

import pytest

from rra.adapters.eval import (
    CacheReplayLLM,
    JsonlProblemStore,
    JsonResultStore,
    L0Repository,
    load_corpus,
)
from rra.application.ports.eval_store import CacheMiss
from rra.domain.models import Document
from rra.domain.models.eval_problem import EvalProblem
from rra.domain.models.eval_result import EvalMetrics, EvalResult


def test_result_store_names_file_by_date_suite_label_and_round_trips(tmp_path):
    store = JsonResultStore(tmp_path, today=date(2026, 11, 9))
    result = EvalResult(
        suite="l1", seed=3, n=2, label="가 main/x", metrics=EvalMetrics(recall_at5=0.5)
    )
    path = store.write(result)
    assert path == tmp_path / "2026-11-09-l1-가-main-x.json"
    assert store.read(path) == result
    custom = store.write(result, path=tmp_path / "sub" / "x.json")
    assert custom.is_file() and json.loads(custom.read_text())["metrics"]["recall_at5"] == 0.5


def test_problem_store_paths_permissions_and_round_trip(tmp_path):
    store = JsonlProblemStore(tmp_path / "sealed", tmp_path / "practice")
    assert store.sealed_path("l1") == tmp_path / "sealed" / "l1.jsonl"
    assert store.practice_path("l1", 20261109) == tmp_path / "practice" / "l1-20261109.jsonl"
    problems = [
        EvalProblem(id="a", kind="novel", request={"goal": "g"}),
        EvalProblem(id="b", kind="reverse", request={}, answers=["own:1"]),
    ]
    path = store.save(store.sealed_path("l1"), problems)
    assert store.exists(path) and store.load(path) == problems
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not store.exists(store.practice_path("l1", 1))


class Inner:
    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        self.calls += 1
        return '{"items": []}'


async def test_cache_replay_hits_misses_and_records(tmp_path):
    replay = CacheReplayLLM(tmp_path)
    with pytest.raises(CacheMiss):
        await replay.complete("p", system="s", json_mode=True)
    assert replay.misses == 1 and replay.hits == 0
    inner = Inner()
    recorder = CacheReplayLLM(tmp_path, inner=inner)
    assert await recorder.complete("p", system="s", json_mode=True) == '{"items": []}'
    assert recorder.recorded == 1 and inner.calls == 1 and len(list(tmp_path.glob("*.json"))) == 1
    assert await replay.complete("p", system="s", json_mode=True) == '{"items": []}'
    assert replay.hits == 1
    # system·json_mode 가 다르면 다른 키
    with pytest.raises(CacheMiss):
        await replay.complete("p", system="other", json_mode=True)


def _docs():
    return [
        Document(
            doc_id="own:1",
            source="own",
            doc_type="rnd_project",
            title="궤도틀림 감지",
            abstract="궤도틀림 가속도 센서 감지 진동",
        ),
        Document(
            doc_id="alio:2",
            source="alio",
            doc_type="internal_report",
            title="역 주차 안내",
            body="주차장 빈자리 센서 안내",
        ),
        Document(
            doc_id="ntis:3",
            source="ntis",
            doc_type="rnd_project",
            title="터널 배수",
            abstract="터널 배수로 퇴적 라이다",
        ),
    ]


async def test_l0_repository_calibrated_similarity_sources_and_documents_of(tmp_path):
    repo = L0Repository(_docs())
    hits = await repo.find_similar("궤도틀림 가속도 센서 진동", k=3)
    assert [d.doc_id for d, _ in hits][0] == "own:1"
    top = hits[0][1]
    assert 0.78 <= hits[-1][1] <= top <= 1.0  # e5 분포처럼 바닥 0.78 위
    only = await repo.find_similar("궤도틀림", k=5, sources=["alio"])
    assert [d.doc_id for d, _ in only] == ["alio:2"]
    assert await repo.find_similar("", k=5) == [] and await repo.hybrid_search(["x"]) == []
    assert [d.doc_id for d in await repo.documents_of("ntis")] == ["ntis:3"]
    assert await repo.count_by_source() == {"own": 1, "alio": 1, "ntis": 1}
    assert (await repo.get_document("own:1")).title == "궤도틀림 감지"
    corpus = tmp_path / "c.jsonl"
    corpus.write_text(
        "".join(json.dumps(d.model_dump(mode="json"), ensure_ascii=False) + "\n" for d in _docs()),
        encoding="utf-8",
    )
    assert len(load_corpus(corpus)) == 3
