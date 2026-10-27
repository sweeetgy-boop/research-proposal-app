"""대체 작성(ADR 0027) — 로컬 교정 재요청까지 실패한 섹션만 외부 LLM 이 쓴다. FakeLLM 만.

- 필수 섹션의 빈 목록은 실패 → 교정 재요청(EMPTY_HINT) → 그래도 비면 대체 작성
- 대체 작성 문장의 근거 id 는 "보여 준 청크" 집합과 대조한다(보안 A)
- 검토 정책 include_internal=False 면 internal 청크는 보여 주지 않는다(전송 범위 = 검토)
- 일일 예산(BudgetExhausted)·네트워크 실패는 실패 섹션으로 남긴다 (fallback_error)
- RunManager 는 state.fallback_sections·step.fallback·manifest fallback_sections 에 기록(본문 없음)
"""

import json

import pytest

from rra.adapters.logging.file_run_log import check_manifest
from rra.application.ports.auth import BudgetExhausted
from rra.application.services import RunManager
from rra.application.usecases.generate_proposal import GenerateProposal
from rra.domain.models import Chunk, Document
from rra.domain.rules.lint import LintRules
from tests.fakes import (
    FakeLLM,
    FakePromptLibrary,
    FakeRunLog,
    FakeSlot,
    FakeTaskRunner,
    InMemoryRepository,
    InMemoryRunStore,
)

KEYS = ["problem", "prior_work"]
USER = "local"
INTERNAL_DOCS = [
    Document(
        doc_id="own:9",
        source="own",
        doc_type="internal_report",
        title="사내",
        body="내부",
        visibility="internal",
    )
]
INTERNAL_CHUNKS = [
    Chunk(chunk_id="own:9#0", doc_id="own:9", ordinal=0, text="내부 자료", visibility="internal")
]


def js(text, ev=()):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


class ExhaustedLLM:
    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        raise BudgetExhausted("오늘 상한")


class BrokenLLM:
    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        raise ConnectionError("https://generativelanguage.googleapis.com 응답 없음 — 키 포함 금지")


@pytest.fixture
def repo(docs, chunks):
    r = InMemoryRepository()
    r.seed(docs, chunks)
    return r


def make(llm, repo, fallback=None, *, include_internal=True, required=KEYS):
    rules = LintRules(required_sections=list(required), evidence_required=["prior_work"])
    return GenerateProposal(
        llm,
        repo,
        FakePromptLibrary(),
        rules,
        KEYS,
        fallback_llm=fallback,
        fallback_provider="gemini",
        fallback_model="gemini-4-argon",
        fallback_include_internal=include_internal,
    )


async def test_empty_required_section_is_retried_then_written_by_fallback(req, repo):
    local = FakeLLM(["[]", "[]"])  # 첫 응답 빈 목록 → 교정 재요청도 빈 목록
    remote = FakeLLM([js("대체 작성 문장", ["alio:1#0"])])
    uc = make(local, repo, remote)
    snap = await uc.retrieve(req)
    composed = await uc.compose_section("prior_work", req, snap)
    assert composed.retries == 1 and "sentences 가 비어 있었음" in local.calls[1]
    assert composed.section.sentences[0].text == "대체 작성 문장"
    assert composed.fallback == {
        "provider": "gemini",
        "model": "gemini-4-argon",
        "reason": "empty",
        "public_doc_ids": sorted({c.doc_id for c in uc.chunks_for("prior_work", snap)}),
        "internal_doc_ids": [],
        "calls": 1,
    }
    assert composed.fallback_error is None and len(remote.calls) == 1
    assert "[자료]" in remote.calls[0] and "[형식 교정" not in remote.calls[0]


async def test_fallback_is_not_used_when_local_succeeds_or_section_is_optional(req, repo):
    remote = FakeLLM([js("쓰면 안 됨")])
    uc = make(FakeLLM([js("문제"), js("선행", ["alio:1#0"])]), repo, remote)
    snap = await uc.retrieve(req)
    for key in KEYS:
        composed = await uc.compose_section(key, req, snap)
        assert composed.fallback is None and composed.retries == 0
    assert remote.calls == []
    # 필수가 아닌 섹션의 빈 목록은 실패가 아니다 → 재요청·대체 없음
    uc = make(FakeLLM(["[]"]), repo, remote, required=["prior_work"])
    composed = await uc.compose_section("problem", req, await uc.retrieve(req))
    assert composed.retries == 0 and composed.fallback is None and remote.calls == []


async def test_fallback_evidence_is_checked_against_the_shown_chunks(req, repo):
    """대체 작성이 보여 주지 않은 id(스냅샷 밖·보여 주지 않은 internal)를 인용하면 폐기한다."""
    repo.seed(INTERNAL_DOCS, INTERNAL_CHUNKS)
    bad = '```\n[{"text": "깨진'
    remote = FakeLLM(
        [
            json.dumps(
                [
                    {"text": "보여 준 근거", "evidence": ["alio:1#0"]},
                    {"text": "숨긴 internal 인용", "evidence": ["own:9#0"]},
                    {"text": "스냅샷 밖", "evidence": ["ntis:zzz#0"]},
                ],
                ensure_ascii=False,
            )
        ]
    )
    uc = make(FakeLLM([bad, bad]), repo, remote, include_internal=False)
    snap = await uc.retrieve(req)
    assert "own:9#0" in snap.retrieved_ids  # 스냅샷에는 있지만 전송 범위 밖
    composed = await uc.compose_section("prior_work", req, snap)
    assert [s.text for s in composed.section.sentences] == ["보여 준 근거"]
    assert len(composed.dropped) == 2
    assert composed.fallback["reason"] == "json"
    assert composed.fallback["internal_doc_ids"] == [] and "own:9" not in remote.calls[0]
    assert "own:9" not in composed.fallback["public_doc_ids"]


async def test_fallback_includes_internal_when_policy_allows(req, repo):
    repo.seed(INTERNAL_DOCS, INTERNAL_CHUNKS)
    remote = FakeLLM([js("내부 인용", ["own:9#0"])])
    uc = make(FakeLLM(["[]", "[]"]), repo, remote, include_internal=True)
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.section.sentences[0].evidence == ["own:9#0"]
    assert composed.fallback["internal_doc_ids"] == ["own:9"]


async def test_budget_or_network_failure_leaves_the_section_failed(req, repo):
    for remote, reason in ((ExhaustedLLM(), "budget"), (BrokenLLM(), "ConnectionError")):
        uc = make(FakeLLM(["[]", "[]"]), repo, remote)
        composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
        assert composed.section.sentences == [] and composed.fallback is None
        assert composed.fallback_error == reason
    # 대체 작성 응답도 깨지면 그 사유
    uc = make(FakeLLM(["[]", "[]"]), repo, FakeLLM(["자유 텍스트"]))
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.fallback is None and composed.fallback_error == "json"


async def test_run_manager_records_fallback_in_state_step_and_manifest(req, repo):
    local = FakeLLM([js("문제"), "[]", "[]"])
    remote = FakeLLM([js("대체 선행", ["alio:1#0"])])
    uc = make(local, repo, remote)
    log = FakeRunLog()
    mgr = RunManager(uc, InMemoryRunStore(), FakeSlot(), log, FakeTaskRunner(), clock=lambda: "t")
    state = await mgr.submit(USER, req)
    final = await mgr.wait(USER, state.run_id)
    assert final.status == "drafted" and final.failed_sections == []
    assert final.step("section:prior_work").fallback == "gemini/gemini-4-argon"
    assert final.step("section:problem").fallback is None
    (rec,) = [x for x in final.fallback_sections]
    assert rec["key"] == "prior_work" and rec["reason"] == "empty" and rec["calls"] == 1
    manifest = log.records[-1][1]
    check_manifest(manifest)  # 허용목록 통과
    assert manifest["fallback_sections"][0]["provider"] == "gemini"
    assert "대체 선행" not in json.dumps(manifest, ensure_ascii=False)
    view = await mgr.get_draft(USER, final.run_id)
    from rra.entrypoints.views import draft_payload

    payload = draft_payload(view)
    assert payload["fallback_sections"] == [
        {"key": "prior_work", "provider": "gemini", "model": "gemini-4-argon", "reason": "empty"}
    ]
    assert payload["failed_sections"] == []


async def test_all_sentences_dropped_is_retried_with_the_reasons_then_fallback(req, repo):
    """재측정 10 의 task_type 꼴: 파싱은 ok 인데 검증(근거 범위·고유명)에서 전부 폐기 → 폐기 사유를
    붙여 교정 재요청 → 그래도 폐기면 대체 작성."""
    outside = js("스냅샷 밖 인용", ["ntis:nope#0"])
    local = FakeLLM([outside, outside])
    remote = FakeLLM([js("대체", ["alio:1#0"])])
    uc = make(local, repo, remote)
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.retries == 1
    assert "검증에서 전부 폐기됐음" in local.calls[1] and "근거 불일치" in local.calls[1]
    assert composed.fallback is not None and composed.fallback["reason"] == "dropped"
    assert composed.section.sentences[0].text == "대체"
    # 대체 작성 없이 두 번 다 폐기되면 실패 섹션(dropped) — 첫 결과·폐기 사유를 남긴다
    uc = make(FakeLLM([outside, outside]), repo, None)
    composed = await uc.compose_section("prior_work", req, await uc.retrieve(req))
    assert composed.section.sentences == [] and composed.retries == 1
    assert composed.parse.ok and len(composed.dropped) == 1 and composed.fallback_error is None
