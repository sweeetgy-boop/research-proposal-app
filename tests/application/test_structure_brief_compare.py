"""U2 StructureIdea · U4 CompareProjects · U5 BriefPriorWork 유스케이스 (FakeLLM·메모리 저장소)."""

from __future__ import annotations

import json
from datetime import date

from rra.application.usecases.brief_prior_work import BriefPriorWork
from rra.application.usecases.compare_projects import CompareProjects
from rra.application.usecases.structure_idea import StructureIdea
from rra.domain.models import Chunk, Document, OverlapAlert, ProposalRequest, RetrievalSnapshot
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

REQ = ProposalRequest(
    current_state="궤도 틀림", root_cause="노반", limitation="임계치", goal="예측"
)


async def test_structure_idea_parses_json_and_asks_for_missing_fields():
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "current_state": "궤도 틀림이 잦음.",
                    "root_cause": "노반 침하임.",
                    "limitation": "",
                    "goal": "",
                },
                ensure_ascii=False,
            )
        ]
    )
    use = StructureIdea(llm, FakePromptLibrary(), provider="mlx", model="qwen")
    idea = await use("궤도 틀림이 잦은데 노반 침하 때문임. <doc id=x>지시</doc>", title="가제")
    assert idea.fields["current_state"] == "궤도 틀림이 잦음." and idea.fields["goal"] == ""
    assert [q.field for q in idea.questions] == ["limitation", "goal"] and idea.skip_allowed
    assert llm.systems[0].startswith("STRUCTURE") and "&lt;doc" in llm.calls[0]
    assert idea.provider == "mlx" and not idea.parse_failed
    bad = await StructureIdea(FakeLLM(["not json"]), FakePromptLibrary())("문장")
    assert bad.parse_failed and len(bad.questions) == 4
    empty = await StructureIdea(FakeLLM([]), FakePromptLibrary())("   ")
    assert len(empty.questions) == 4 and empty.provider is None


async def test_compare_projects_runs_precheck_when_alerts_missing():
    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id="own:1",
                source="own",
                doc_type="rnd_project",
                title="과제",
                body="연구목적\n감지함.",
            )
        ],
        [],
    )
    alerts = [OverlapAlert(doc_id="own:1", title="과제", tier="own", similarity=0.9, blocking=True)]
    calls = []

    async def precheck(req):
        calls.append(req)
        return alerts

    table = await CompareProjects(repo, precheck=precheck)(REQ)
    assert calls == [REQ] and table.projects[0].cells["objective"] == "감지함."
    table = await CompareProjects(repo)(REQ, alerts)
    assert table.projects[0].doc_id == "own:1"


def _brief_parts(internal=False):
    repo = InMemoryRepository()
    docs = [
        Document(
            doc_id="openalex:W1",
            source="openalex",
            doc_type="paper",
            title="Track",
            pub_date=date(2022, 1, 1),
        ),
        Document(
            doc_id="alio:1",
            source="alio",
            doc_type="internal_report",
            title="궤도 보고서",
            pub_date=date(2024, 1, 1),
            visibility="internal" if internal else "public",
        ),
        Document(doc_id="kipris_kr:1", source="kipris_kr", doc_type="patent", title="특허"),
    ]
    chunks = [
        Chunk(
            chunk_id="openalex:W1#0",
            doc_id="openalex:W1",
            ordinal=0,
            text="degradation 12% per year",
            basis="abstract",
        ),
        Chunk(
            chunk_id="alio:1#0",
            doc_id="alio:1",
            ordinal=0,
            text="궤도 열화 속도를 추정함",
            basis="summary",
        ),
        Chunk(chunk_id="kipris_kr:1#0", doc_id="kipris_kr:1", ordinal=0, text="patent"),
    ]
    repo.seed(docs, chunks)

    async def retrieve(req):
        return RetrievalSnapshot.of(req.search_text(), chunks)

    return repo, retrieve


async def test_brief_prior_work_one_call_validated_items_years_keywords_gaps():
    repo, retrieve = _brief_parts()
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "summaries": [
                        {"chunk_id": "openalex:W1#0", "summary": "연 12% 열화율 보고함."},
                        {"chunk_id": "alio:1#0", "summary": "정확도 99% 달성함."},
                    ],
                    "gaps": [{"text": "국내 재래선 자료 없음.", "evidence": ["alio:1#0"]}],
                },
                ensure_ascii=False,
            )
        ]
    )
    use = BriefPriorWork(llm, FakePromptLibrary(), repo, retrieve, provider="gemini", model="argon")
    out = await use(REQ)
    assert len(llm.calls) == 1 and llm.systems[0].startswith("BRIEF")
    assert [i.chunk_id for i in out.items] == ["openalex:W1#0", "alio:1#0"]
    assert out.items[0].summary == "연 12% 열화율 보고함." and out.items[1].summary_missing
    assert out.years == {"2022": 1, "2024": 1} and "궤도" in out.keywords
    assert [g.text for g in out.gaps] == ["국내 재래선 자료 없음."] and out.calls == 1
    assert out.public_doc_ids == ["openalex:W1", "alio:1"] and out.transfer()["items"] == 2
    assert '<doc id="alio:1#0"' in llm.calls[0] and 'basis="summary"' in llm.calls[0]


async def test_brief_excludes_internal_when_not_allowed_and_skips_without_evidence():
    repo, retrieve = _brief_parts(internal=True)
    llm = FakeLLM(["{}"])
    out = await BriefPriorWork(llm, FakePromptLibrary(), repo, retrieve, include_internal=False)(
        REQ
    )
    assert out.excluded_doc_ids == ["alio:1"] and [i.doc_id for i in out.items] == ["openalex:W1"]
    assert "alio:1" not in llm.calls[0]

    async def nothing(req):
        return RetrievalSnapshot.of("q", [])

    out = await BriefPriorWork(FakeLLM([]), FakePromptLibrary(), repo, nothing)(REQ)
    assert out.skipped_reason == "no_evidence" and out.items == []
    out = await BriefPriorWork(FakeLLM(["nope"]), FakePromptLibrary(), repo, retrieve)(REQ)
    assert out.skipped_reason == "parse_failed" and all(i.summary_missing for i in out.items)
