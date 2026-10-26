"""llm-bench 유스케이스·보고 — FakeLLM 으로 지표 집계, Markdown 표."""

import json

from rra.application.usecases.bench import BenchGenerate
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Chunk, Document, ProposalRequest
from rra.domain.rules.lint import ChoiceSpec, LintRules
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
    "이건 JSON 이 아님",  # method 파싱 실패
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
        [Chunk(chunk_id="openalex:W1#0", doc_id="openalex:W1", ordinal=0, text="궤도 15% 개선")],
    )
    llm = CountingLLM(list(ANSWERS))
    gen = GenerateProposal(llm, repo, FakePromptLibrary(), RULES, KEYS)
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
    assert (
        idea.dropped == 1 and idea.foreign_script == 1 and idea.tech_sentences == ["근거 있음 文"]
    )
    assert idea.title == "제목" and set(idea.section_seconds) == set(KEYS)
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
    assert "기준 모델: qwen" in md
