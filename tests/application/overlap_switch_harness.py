"""② 스위치 off 회귀 하네스 (레인 E, ADR 0059) — 가짜 저장소·결정적 reranker·FakeLLM 으로 골든셋
12건(`tests/golden/*.yaml` 10 + `not_similar/` 2) + 시범 합성 아이디어(역사 비둘기)를 돌려 ② 결과
전체를 JSON 으로
뽑는다. 스냅샷은 main(434581b, 스위치 도입 전) 코드로 한 번 만들어
`tests/fixtures/overlap_switch_off_snapshot.json`
에 고정하고, 바뀐 코드가 세 스위치 false 에서 **같은 바이트**를 내는지 `test_overlap_switch_off.py`
가 검사한다.

스냅샷에 담는 것(모두 결정적): 저장소 호출 목록(검색 질의·k·자료원 — 검색 패턴), REST ② 행
(`alerts_payload`),
관련 연구, 핵심어·출처, 판정 요약, AI 판정 프롬프트(판정 입력). LLM·임베딩·네트워크 없음.

스냅샷 다시 만들기(스위치 도입 전 코드에서만!):
    PYTHONPATH=src .venv/bin/python -m tests.application.overlap_switch_harness --write
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from rra import config_loader as cl
from rra.application.usecases.judge_sameness import SameJudge
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Chunk, Document, ProposalRequest
from rra.domain.models.live_search import LiveKeywords
from rra.domain.rules.overlap import OwnUnit
from rra.entrypoints.views import alerts_payload, judgment_payload, related_research_payload
from rra.settings import Settings
from tests.fakes import FakeLLM, InMemoryRepository

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
SNAPSHOT = ROOT / "tests" / "fixtures" / "overlap_switch_off_snapshot.json"
REQUEST_KEYS = ("title_hint", "current_state", "root_cause", "limitation", "goal")
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
GENERIC_FILLER = (
    "철도 안전 개선 방안 연구. 정책 마련이 필요한 상황이며 현황 분석과 효율 향상 대책을 검토함."
)

# 시범 합성 아이디어 — 역사 비둘기 (2026-11 운영 사례를 재구성, 실명·실제 문서 없음)
PIGEON = {
    "title_hint": "지상역 승강장 캐노피 비둘기 침입 비살상 퇴치 장치 개발",
    "current_state": "수도권 지상역 승강장 캐노피에 비둘기가 둥지를 틀어 배설물 오염과 민원이 "
    "반복된다.",
    "root_cause": "캐노피 철골 틈이 둥지 자리가 되고, 그물·침 설치는 미관과 유지보수 문제로 "
    "일부 역만 적용됐다.",
    "limitation": "청소 인력으로 사후 대응만 하고 있어 오염이 재발하고 위생 민원이 줄지 않는다.",
    "goal": "초음파·조명 자극을 조합한 비살상 퇴치 장치를 개발해 시범역에서 둥지 수와 오염 민원을 "
    "줄인다.",
    "expected_similar": ["own:pigeon-net"],
    "must_not_block": ["alio:sum-pigeon-clean"],
}


def settings() -> Settings:
    return Settings(_env_file=None, config_dir=ROOT / "config")


def cases() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for p in sorted(GOLDEN.glob("*.yaml")):
        out.append((p.stem, yaml.safe_load(p.read_text(encoding="utf-8"))))
    for p in sorted((GOLDEN / "not_similar").glob("*.yaml")):
        out.append((f"not_similar/{p.stem}", yaml.safe_load(p.read_text(encoding="utf-8"))))
    out.append(("pilot/pigeon", PIGEON))
    return out


def request_of(case: dict[str, Any]) -> ProposalRequest:
    return ProposalRequest(**{k: case.get(k) or "" for k in REQUEST_KEYS})


def _source(doc_id: str) -> str:
    return doc_id.split(":", 1)[0]


def _doc_type(source: str, research: bool = False) -> str:
    if source == "ntis":
        return "report" if research else "rnd_project"
    if source == "korail_web":
        return "procurement"
    if source == "alio":
        return "internal_report"
    if source in ("scienceon", "openalex"):
        return "paper"
    return "rnd_project"


def corpus(name: str, case: dict[str, Any]) -> list[Document]:
    """사례마다 합성 문서: 정답(제목·본문이 아이디어에서 나옴, 두 번째는 연작 판) · 일반어 교란 문서
    ·
    유사하지 않음 문서(일반어만 겹침) · 관련 연구(논문)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    title = case["title_hint"]
    docs: list[Document] = []
    expected = list(case.get("expected_similar") or [])[:2]
    for i, doc_id in enumerate(expected):
        src = _source(doc_id)
        if i == 0:
            docs.append(
                Document(
                    doc_id=doc_id,
                    source=src,
                    doc_type=_doc_type(src),
                    title=f"{title} 연구",
                    body=f"{case['goal']} {case['current_state']}",
                    department="철도연구원" if src == "alio" else None,
                    orgs=["korail"] if src in ("alio", "own") else [],
                    raw={"status": "completed"} if src == "own" else {},
                )
            )
        else:
            docs.append(
                Document(
                    doc_id=doc_id,
                    source=src,
                    doc_type=_doc_type(src),
                    title=f"2024년도 {title} 연구",
                    body=f"{case['root_cause']} {case['goal']}",
                    orgs=["korail"] if src in ("alio", "own") else [],
                )
            )
    docs.append(
        Document(
            doc_id=f"alio:sum-{slug}-gen",
            source="alio",
            doc_type="internal_report",
            title="철도 안전 개선 방안 연구",
            body=GENERIC_FILLER,
            text_basis="summary",
            orgs=["korail"],
        )
    )
    for doc_id in case.get("must_not_block") or []:
        src = _source(doc_id)
        docs.append(
            Document(
                doc_id=doc_id,
                source=src,
                doc_type=_doc_type(src),
                title="해외 철도차량 조달정책 분석 및 터널 여굴 채움재 진동 저감",
                body=f"{GENERIC_FILLER} {case['limitation']}",
                orgs=["korail"] if src in ("alio", "own") else [],
            )
        )
    docs.append(
        Document(
            doc_id=f"scienceon:{slug}-p",
            source="scienceon",
            doc_type="paper",
            title=f"{title}에 관한 연구 동향",
            abstract=case["root_cause"],
        )
    )
    docs.append(
        Document(
            doc_id=f"openalex:W-{slug}",
            source="openalex",
            doc_type="paper",
            title="Railway infrastructure monitoring with onboard sensors",
            abstract="A survey of onboard sensing for railway infrastructure.",
        )
    )
    return docs


class OverlapScorer:
    """결정적 reranker — 질의 토큰이 문서 토큰에 얼마나 덮이는지(overlap coefficient)."""

    model_name = "fake/overlap-scorer"

    def __init__(self):
        self.calls: list[tuple[int, int]] = []

    async def score_documents(self, query, docs):
        q = set(_TOKEN.findall(query.lower()))
        out = []
        for d, _ in docs:
            text = " ".join(p for p in (d.title, d.abstract, d.body) if p).lower()
            toks = set(_TOKEN.findall(text))
            out.append(round(len(q & toks) / len(toks), 4) if toks else 0.0)
        self.calls.append((len(docs), len(q)))
        return out


def verdict_answer(case: dict[str, Any], ids: list[str]) -> str:
    expected = set(case.get("expected_similar") or [])
    items = []
    for i in ids:
        if i in expected:
            items.append({"doc_id": i, "verdict": "same", "reason": "대상·문제·방법이 같음"})
        elif i.startswith("alio:sum-") and i.endswith("-gen"):
            items.append({"doc_id": i, "verdict": "different", "reason": "일반어만 겹침"})
        else:
            items.append({"doc_id": i, "verdict": "partial", "reason": "대상만 일부 겹침"})
    return json.dumps({"items": items}, ensure_ascii=False)


class CaseLLM(FakeLLM):
    """프롬프트의 <doc id="…"> 순서대로 판정을 돌려주는 가짜 Argon."""

    def __init__(self, case: dict[str, Any]):
        super().__init__([])
        self.case = case

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        self.calls.append(prompt)
        ids = re.findall(r'<doc id="([^"]+)">', prompt)
        return verdict_answer(self.case, ids)


async def keyword_source(req: ProposalRequest) -> LiveKeywords:
    return LiveKeywords(ko=[req.title_hint or req.goal], origin="argon")


def chunks_of(docs: list[Document]) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"{d.doc_id}#0",
            doc_id=d.doc_id,
            ordinal=0,
            text=" ".join(p for p in (d.title, d.abstract, d.body) if p),
        )
        for d in docs
    ]


def build(case: dict[str, Any], docs: list[Document], **extra) -> tuple[PrecheckOverlap, Any, Any]:
    s = settings()
    repo = InMemoryRepository()
    repo.seed(docs, chunks_of(docs))
    llm = CaseLLM(case)
    judge = SameJudge(primary=llm, repo=repo, provider="fake", model="fake-argon")
    pre = PrecheckOverlap(
        repo,
        own=OwnUnit(org="korail", departments=frozenset({"철도연구원"})),
        keywords=cl.keyword_rule(s),
        reranker=OverlapScorer(),
        mix=None,
        candidates=cl.overlap_candidates(s),
        rerank=cl.rerank_rule(s),
        series=cl.series_rule(s),
        same_judge=judge,
        keyword_source=keyword_source,
        **extra,
    )
    return pre, repo, llm


async def run_case(name: str, case: dict[str, Any], **extra) -> dict[str, Any]:
    docs = corpus(name, case)
    pre, repo, llm = build(case, docs, **extra)
    req = request_of(case)
    rule = await pre.rule_stage(req, remember=True)
    judged = await pre.judgment(req)
    follow = await pre(req)  # 후속 경로(비교표·게이트) — 메모
    return {
        "name": name,
        "repo_calls": [[kind, args] for kind, args in repo.calls],
        "rule": alerts_payload(rule.alerts),
        "judged": alerts_payload(judged.alerts),
        "follow_up_blocking": [a.doc_id for a in follow if a.blocking],
        "related_research": related_research_payload(judged.related_research),
        "core_keywords": list(judged.core_keywords),
        "keyword_origin": judged.keyword_origin,
        "judgment": judgment_payload(judged.judgment),
        "judge_prompts": list(llm.calls),
    }


async def run_all(**extra) -> list[dict[str, Any]]:
    return [await run_case(name, case, **extra) for name, case in cases()]


def dumps(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    rows = asyncio.run(run_all())
    if "--write" in argv:
        SNAPSHOT.write_text(dumps(rows), encoding="utf-8")
        print(f"wrote {SNAPSHOT} ({len(rows)} cases)")
    else:
        print(dumps(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
