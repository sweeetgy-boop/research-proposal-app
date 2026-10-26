"""llm-bench 유스케이스·보고 — FakeLLM 으로 지표 집계, Markdown 표."""

import json

from rra.application.usecases.bench import BenchGenerate
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Chunk, Document, ProposalRequest
from rra.domain.rules.lint import ChoiceSpec, LintRules
from rra.domain.rules.relevance import RelevanceFloor
from rra.entrypoints.views import bench_markdown
from tests.fakes import FakeLLM, FakePromptLibrary, InMemoryRepository

KEYS = ["title", "task_type", "tech_importance", "method"]
RULES = LintRules(
    sections=KEYS,
    required_sections=["title"],
    evidence_required=["tech_importance"],
    number_checked=["method"],
    choices={"task_type": ChoiceSpec(options="task_types")},
)
ANSWERS = [
    '[{"text": "제목", "evidence": []}]',
    '{"choices": ["applied"], "sentences": []}',
    '[{"text": "근거 있음 文", "evidence": ["openalex:W1#0"]}, '
    '{"text": "근거 없음", "evidence": []}]',
    "이건 JSON 이 아님",  # method 파싱 실패 → 교정 재요청
    "두 번째도 JSON 아님",  # 재요청도 실패 → 기존 처리
]


class CountingLLM(FakeLLM):
    def __init__(self, answers):
        super().__init__(answers)
        self.fallbacks = 2
        self.max_prompt_tokens = 1234
        self.max_completion_tokens = 300

    @property
    def calls_n(self):
        return len(self.calls)


async def test_bench_collects_metrics_per_idea_and_totals():
    repo = InMemoryRepository()
    repo.seed(
        [
            Document(
                doc_id="openalex:W1", source="openalex", doc_type="paper", title="t", abstract="a"
            )
        ],
        [
            Chunk(
                chunk_id="openalex:W1#0",
                doc_id="openalex:W1",
                ordinal=0,
                text="궤도 15% 개선",
                similarity=0.9,
            ),
            Chunk(
                chunk_id="openalex:W2#0",
                doc_id="openalex:W2",
                ordinal=0,
                text="far away",
                similarity=0.5,
            ),
        ],
    )
    llm = CountingLLM(list(ANSWERS))
    gen = GenerateProposal(llm, repo, FakePromptLibrary(), RULES, KEYS)
    gen.relevance = RelevanceFloor(min_similarity=0.79, min_keyword_hits=0)
    ticks = iter(float(i) for i in range(1000))
    bench = BenchGenerate(
        gen,
        label="fake",
        model="fake-4bit",
        profile="qwen",
        context_length=32768,
        rss_sampler=lambda: 4321.0,
        clock=lambda: next(ticks),
        now=lambda: "2026-10-26T00:00:00",
    )
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    result = await bench([("idea1", req)])
    idea = result.ideas[0]
    assert idea.sections_llm == 4 and idea.parse_ok == 3 and idea.parse_failed == ["method:json"]
    assert idea.parse_ok_strict == 3 and idea.parse_lenient == [] and idea.retries == 1
    assert idea.parse_retried_ok == [] and result.retries == 1 and result.totals()["retries"] == 1
    assert (
        idea.dropped == 1 and idea.foreign_script == 1 and idea.tech_sentences == ["근거 있음 文"]
    )
    assert idea.title == "제목" and set(idea.section_seconds) == set(KEYS)
    assert idea.evidence_chunks == 1 and idea.dropped_chunks == 1 and idea.cited_chunks == 1
    assert idea.empty_sections == [] and result.totals()["dropped_chunks"] == 1
    assert result.totals()["empty_sections"] == 0 and result.totals()["evidence_chunks"] == 1
    assert result.json_success_rate == 0.75 and result.fallbacks == 2
    assert result.max_prompt_tokens == 1234 and result.max_rss_mb == 4321.0
    assert result.totals()["dropped"] == 1 and result.total_seconds > 0
    d = result.to_dict()
    assert (
        d["label"] == "fake" and d["ideas"][0]["name"] == "idea1" and d["json_success_rate"] == 0.75
    )
    json.dumps(d)  # 직렬화 가능

    md = bench_markdown(
        [d, {**d, "label": "other", "fallbacks": 0}], date="2026-10-26", baseline="qwen"
    )
    assert "| 지표 | fake | other |" in md and "| 프롬프트 폴백 횟수 | 2 | 0 |" in md
    assert "75.0% (3/4)" in md and "근거 있음 文" in md and "method:json" in md
    assert "(a) 첫 응답이 지시 모양" in md and "(b) 관용 처리·재요청·폴백 포함" in md
    assert "| 형식 교정 재요청 횟수 | 1 | 1 |" in md
    assert "| 관련도 하한 통과 근거 청크 수 | 1 | 1 |" in md
    assert "| 관련도 하한 탈락 청크 수 | 1 | 1 |" in md
    assert "| 근거 없어 빈칸이 된 섹션 수 | 0 | 0 |" in md
    assert "| 인용된 근거 id 수 | 1 | 1 |" in md
    assert "| 근거 | 탈락 | 인용 | 빈칸 |" in md
    assert "기준 모델: qwen" in md
