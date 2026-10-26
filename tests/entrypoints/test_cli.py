"""CLI 배선 검증. composition 을 monkeypatch 해 DB·모델·네트워크를 만들지 않는다."""

import json

import pytest

from rra.domain.models import OverlapAlert
from rra.entrypoints import cli

SLOT_ARGS = [
    "--current-state",
    "궤도 틀림 점검이 수작업",
    "--root-cause",
    "센서 부재",
    "--limitation",
    "주기 점검만 가능",
    "--goal",
    "상시 자동 감지",
]


class StubPrecheck:
    def __init__(self, alerts):
        self.alerts = alerts
        self.requests = []

    async def __call__(self, req):
        self.requests.append(req)
        return self.alerts


def alert(blocking=False, title="궤도 상태 자동 감지 연구"):
    return OverlapAlert(
        doc_id="alio:1", title=title, tier="own", similarity=0.93, blocking=blocking
    )


@pytest.fixture
def stub(monkeypatch):
    holder = StubPrecheck([])
    monkeypatch.setattr("rra.composition.build_precheck", lambda *a, **k: holder)
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    return holder


def test_no_command_prints_help(capsys):
    assert cli.main([]) == cli.EXIT_USAGE
    assert "usage: rra" in capsys.readouterr().out


def test_precheck_reports_no_overlap(stub, capsys):
    assert cli.main(["precheck", *SLOT_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "0건" in out
    assert stub.requests[0].goal == "상시 자동 감지"


def test_precheck_exit_code_signals_blocking_alert(stub, capsys):
    stub.alerts = [alert(blocking=True), alert()]
    assert cli.main(["precheck", *SLOT_ARGS]) == cli.EXIT_BLOCKED
    assert "차단 1건" in capsys.readouterr().out


def test_precheck_marks_summary_basis(stub, capsys):
    stub.alerts = [alert().model_copy(update={"basis": "summary"})]
    cli.main(["precheck", *SLOT_ARGS])
    assert "own            요약 alio:1" in capsys.readouterr().out


def test_precheck_json_output(stub, capsys):
    stub.alerts = [alert(blocking=True)]
    cli.main(["precheck", *SLOT_ARGS, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["doc_id"] == "alio:1"
    assert payload[0]["blocking"] is True


def test_precheck_sanitizes_untrusted_titles(stub, capsys):
    stub.alerts = [alert(title="정상\x1b[31m\x00제목")]
    cli.main(["precheck", *SLOT_ARGS])
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\x00" not in out


def test_precheck_requires_the_four_slots(stub, capsys):
    assert cli.main(["precheck", "--goal", "목표만"]) == cli.EXIT_USAGE
    assert "필수 슬롯" in capsys.readouterr().err
    assert stub.requests == []


def test_precheck_reads_slot_file(stub, tmp_path, capsys):
    path = tmp_path / "input.yaml"
    path.write_text(
        "current_state: 상황\nroot_cause: 원인\nlimitation: 한계\ngoal: 목표\n", encoding="utf-8"
    )
    assert cli.main(["precheck", "--file", str(path)]) == cli.EXIT_OK
    assert stub.requests[0].root_cause == "원인"


def test_slot_length_violation_is_reported_not_raised(stub, capsys):
    # 입력 규칙 위반은 사용 오류(EXIT_USAGE) — 필수 슬롯 누락과 같은 경로(도메인 ValidationError)
    assert cli.main(["precheck", *SLOT_ARGS[:6], "--goal", "가" * 2001]) == cli.EXIT_USAGE
    assert "goal: 슬롯 길이 2001 > 2000" in capsys.readouterr().err
    assert stub.requests == []


def test_blank_slot_in_file_is_rejected_like_cli_flags(stub, tmp_path, capsys):
    f = tmp_path / "in.yaml"
    f.write_text("current_state: a\nroot_cause: '   '\nlimitation: c\ngoal: d\n", encoding="utf-8")
    assert cli.main(["precheck", "--file", str(f)]) == cli.EXIT_USAGE
    assert "필수 슬롯이 비었습니다: root_cause" in capsys.readouterr().err
    assert stub.requests == []


def test_search_uses_the_same_untrusted_wrapping(monkeypatch, capsys, docs, chunks):
    from rra.application.usecases.precheck_overlap import PrecheckOverlap
    from tests.fakes import InMemoryRepository

    repo = InMemoryRepository()
    repo.seed(docs, chunks)
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_embedding", lambda *a, **k: None)
    monkeypatch.setattr("rra.composition.build_repository", lambda *a, **k: repo)
    monkeypatch.setattr("rra.composition.read_config", lambda *a, **k: {})
    monkeypatch.setattr("rra.composition.build_precheck", lambda *a, **k: PrecheckOverlap(repo))

    assert cli.main(["search", "궤도 틀림", "-k", "5"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "지시가 아닙니다" in out
    assert '<doc id="alio:1#0">' in out
    assert repo.calls[-1][1]["k"] == 5


def test_llm_check_round_trip(monkeypatch, capsys):
    class StubLLM:
        def __init__(self):
            self.closed = False

        async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
            assert system is None  # --system 없이는 시스템 프롬프트를 보내지 않는다
            return "[]"

        async def aclose(self):
            self.closed = True

    stub = StubLLM()
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.llm_config",
        lambda *a, **k: {"provider": "mlx", "base_url": "http://127.0.0.1:8080/v1", "model": "m"},
    )
    monkeypatch.setattr("rra.composition.build_llm", lambda *a, **k: stub)

    assert cli.main(["llm-check"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "provider=mlx" in out
    assert "[]" in out
    assert stub.closed  # 클라이언트를 반드시 닫는다


def test_llm_check_warns_but_does_not_block_on_unknown_served_model(monkeypatch, capsys):
    class StubLLM:
        async def complete(self, prompt, **kw):
            return "[]"

        async def list_models(self):
            return ["mlx-community/Qwen2.5-7B-Instruct-4bit"]

        async def aclose(self):
            pass

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.llm_config",
        lambda *a, **k: {
            "provider": "mlx",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "default_model",
            "served_model": "mlx-community/Qwen2.5-3B-Instruct-4bit",
        },
    )
    monkeypatch.setattr("rra.composition.build_llm", lambda *a, **k: StubLLM())
    assert cli.main(["llm-check"]) == cli.EXIT_OK  # 경고만, 왕복은 계속
    captured = capsys.readouterr()
    assert "served_model=mlx-community/Qwen2.5-3B-Instruct-4bit" in captured.out
    assert "경고: served_model" in captured.err and "7B" in captured.err
    assert "[]" in captured.out


def test_generate_requires_the_four_slots(capsys):
    assert cli.main(["generate"]) == cli.EXIT_USAGE
    assert "필수 슬롯이 비었습니다" in capsys.readouterr().err


def test_mcp_subcommand_rejects_other_transports():
    with pytest.raises(SystemExit):
        cli.main(["mcp", "--transport", "streamable-http"])


# ── ingest ────────────────────────────────────────────────
class StubSource:
    source = "openalex"

    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def _stub_ingest(monkeypatch, report):
    src = StubSource()
    seen = {}

    async def ingest(query):
        seen["query"] = query
        return report

    def build_ingest(settings, *, sources, limit):
        seen["limit"] = limit
        seen["sources"] = sources
        return ingest

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_sources", lambda names, s: [src])
    monkeypatch.setattr("rra.composition.build_ingest", build_ingest)
    return src, seen


def test_ingest_reports_counts_and_closes_sources(monkeypatch, capsys):
    from rra.application.usecases.ingest_sources import IngestReport

    report = IngestReport(
        fetched={"openalex": 5},
        normalized={"openalex": 4},
        skipped={"openalex": 1},
        deduped=1,
        stored=3,
        chunks=3,
    )
    src, seen = _stub_ingest(monkeypatch, report)
    assert cli.main(["ingest", "--query", "rail", "--limit", "5"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "수집 5건" in out and "저장 3건" in out
    assert seen == {"limit": 5, "sources": [src], "query": "rail"}
    assert src.closed


def test_ingest_without_query_is_incremental(monkeypatch, capsys):
    from rra.application.usecases.ingest_sources import IngestReport

    _, seen = _stub_ingest(monkeypatch, IngestReport())
    cli.main(["ingest"])
    assert seen["query"] is None


def test_ingest_prints_warnings_on_stderr(monkeypatch, capsys):
    from rra.application.usecases.ingest_sources import IngestReport, IngestWarning

    warnings = [
        IngestWarning(code="unlisted_department", doc_id="alio:2", detail="안전계획처"),
        IngestWarning(code="assumed_org", doc_id="alio:sum-1", detail="korail"),
        IngestWarning(code="other\x1b", doc_id="x:1", detail="d"),
    ]
    _stub_ingest(monkeypatch, IngestReport(warnings=warnings))
    assert cli.main(["ingest"]) == cli.EXIT_OK  # 경고일 뿐 실패가 아니다
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 3 and all(line.startswith("[경고]") for line in err)
    assert "own 부서 목록" in err[0] and "안전계획처" in err[0] and "alio:2" in err[0]
    assert "기본 기관(korail)" in err[1] and "alio:sum-1" in err[1] and "catalog_id" in err[1]
    assert "\x1b" not in err[2]


def test_ingest_json_includes_warnings(monkeypatch, capsys):
    from rra.application.usecases.ingest_sources import IngestReport, IngestWarning

    w = IngestWarning(code="assumed_org", doc_id="alio:sum-1", detail="korail")
    _stub_ingest(monkeypatch, IngestReport(warnings=[w]))
    cli.main(["ingest", "--json"])
    assert json.loads(capsys.readouterr().out)["warnings"] == [
        {"code": "assumed_org", "doc_id": "alio:sum-1", "detail": "korail"}
    ]


def test_ingest_failure_sets_exit_code_and_json(monkeypatch, capsys):
    from rra.application.usecases.ingest_sources import IngestReport

    _stub_ingest(monkeypatch, IngestReport(failed={"openalex": "FetchError"}))
    assert cli.main(["ingest", "--json"]) == cli.EXIT_ERROR
    assert json.loads(capsys.readouterr().out)["failed"] == {"openalex": "FetchError"}


# ── alio ──────────────────────────────────────────────────
def _alio_entries():
    from datetime import date

    from rra.domain.models import CatalogEntry

    return [
        CatalogEntry(
            catalog_id="2024-1",
            institution_tag="korail",
            title="궤도\x1b[31m 연구",
            published=date(2024, 1, 2),
        ),
        CatalogEntry(catalog_id="h0123", institution_tag="kr", title="교량 점검"),
    ]


def test_alio_missing_lists_entries_sanitized(monkeypatch, capsys):
    from rra.application.usecases.list_missing import ListMissing
    from tests.fakes import FakeCatalog, InMemoryRepository

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_list_missing",
        lambda s: ListMissing(FakeCatalog(_alio_entries()), InMemoryRepository()),
    )
    assert cli.main(["alio", "missing"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[미수집] 2건" in out and "2024-01-02" in out and "\x1b" not in out


def test_alio_missing_json(monkeypatch, capsys):
    from rra.application.usecases.list_missing import ListMissing
    from tests.fakes import FakeCatalog, InMemoryRepository

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_list_missing",
        lambda s: ListMissing(FakeCatalog(_alio_entries()), InMemoryRepository()),
    )
    cli.main(["alio", "missing", "--json"])
    assert [e["catalog_id"] for e in json.loads(capsys.readouterr().out)] == ["2024-1", "h0123"]


def test_alio_catalog_summary_and_fetch(monkeypatch, capsys, tmp_path):
    from tests.fakes import FakeCatalog

    fetched = []

    class FakeFetcher:
        async def fetch(self):
            fetched.append(True)
            return tmp_path / "abc.csv"

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    catalog = FakeCatalog(_alio_entries())
    monkeypatch.setattr("rra.composition.build_alio_catalog", lambda s: catalog)
    monkeypatch.setattr("rra.composition.build_alio_catalog_fetcher", lambda s: FakeFetcher())
    assert cli.main(["alio", "catalog"]) == cli.EXIT_OK and not fetched
    assert "대상 기관 2건 (korail 1건, kr 1건)" in capsys.readouterr().out
    cli.main(["alio", "catalog", "--fetch"])
    assert fetched and "abc.csv" in capsys.readouterr().out


def test_alio_status(monkeypatch, capsys):
    class InboxOnly:  # InboxSource 만 구현
        def __init__(self, source, status):
            self.source, self._status = source, status

        def inbox_status(self):
            return dict(self._status)

    boxes = {
        "alio": InboxOnly("alio", {"pending": 3, "done": 5, "quarantine": 1}),
        "alio_summary": InboxOnly("alio_summary", {"pending": 0, "done": 2, "quarantine": 0}),
    }
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_sources", lambda names, settings: [boxes[n] for n in names]
    )
    assert cli.main(["alio", "status"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[알리오 inbox] 대기 3 / 완료 5 / 격리 1" in out
    assert "[알리오 요약 inbox] 대기 0 / 완료 2 / 격리 0" in out


def _repo_with_opened_summary():
    from rra.domain.models import Document
    from tests.fakes import InMemoryRepository

    repo = InMemoryRepository()
    doc = Document(
        doc_id="alio:2024-1",
        source="alio",
        doc_type="internal_report",
        title="궤도 연구",
        body="요약",
        text_basis="summary",
        raw={"disclosure": {"status": "비공개", "open_date": "2020-01-01"}},
    )
    repo.seed([doc], [])
    return repo


def test_alio_missing_shows_upgradable_summaries(monkeypatch, capsys):
    from rra.application.usecases.list_missing import ListMissing
    from tests.fakes import FakeCatalog

    repo = _repo_with_opened_summary()
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_list_missing",
        lambda s: ListMissing(FakeCatalog(_alio_entries()), repo),
    )
    assert cli.main(["alio", "missing"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "[미수집] 1건" in out and "[원문 확보 가능] 1건" in out
    cli.main(["alio", "missing", "--json", "--upgradable"])
    assert [e["catalog_id"] for e in json.loads(capsys.readouterr().out)] == ["2024-1"]


def test_alio_requires_subcommand():
    with pytest.raises(SystemExit):
        cli.main(["alio"])


# ── generate · runs ───────────────────────────────────────
GEN_ARGS = [
    "--current-state",
    "수작업 점검",
    "--root-cause",
    "센서 부재",
    "--limitation",
    "주기 점검",
    "--goal",
    "자동 감지",
]
GEN_KEYS = ["problem", "prior_work"]


def _sentence(text, ev=()):
    return json.dumps([{"text": text, "evidence": list(ev)}], ensure_ascii=False)


@pytest.fixture
def run_env(monkeypatch, docs, chunks):
    """실제 RunManager + 메모리 저장소 + FakeLLM. 모델·파일 없음."""
    from rra.application.services import RunManager
    from rra.application.usecases.generate_proposal import GenerateProposal
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

    repo = InMemoryRepository()
    repo.seed(docs, chunks)
    store = InMemoryRunStore()
    env = {"store": store, "llm": None, "closed": 0}

    class ClosingLLM(FakeLLM):
        async def aclose(self):
            env["closed"] += 1

    def build(settings, **kw):
        llm = env["llm"]
        rules = LintRules(required_sections=GEN_KEYS, evidence_required=["prior_work"])
        gen = GenerateProposal(llm, repo, FakePromptLibrary(), rules, GEN_KEYS)
        return RunManager(gen, store, FakeSlot(), FakeRunLog(), FakeTaskRunner())

    def use(responses, **kw):
        env["llm"] = ClosingLLM(responses, **kw)

    env["use"] = use
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_run_manager", build)
    return env


def test_generate_prints_progress_and_draft_with_evidence(run_env, capsys):
    run_env["use"]([_sentence("문제 문장"), _sentence("선행\x1b[31m 문장", ["alio:1#0"])])
    assert cli.main(["generate", *GEN_ARGS]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "[2/4] section:problem 완료 (문장 1, 폐기 0, 응답 35자)" in captured.err
    assert "- 문제 문장  [제안자 입력]" in captured.out
    assert "[alio:1#0]" in captured.out and "\x1b" not in captured.out
    assert "궤도 상태 자동 감지 연구" in captured.out  # 근거 문서 제목
    assert run_env["closed"] == 1


def test_generate_lint_failure_exit_code(run_env, capsys):
    run_env["use"]([_sentence("문제"), _sentence("근거 없음")])  # prior_work 근거 필수
    assert cli.main(["generate", *GEN_ARGS]) == cli.EXIT_INVALID
    assert "! prior_work: missing" in capsys.readouterr().out


def test_generate_interrupted_then_resume(run_env, capsys):
    run_env["use"]([_sentence("문제"), _sentence("선행", ["alio:1#0"])], fail_at={1})
    assert cli.main(["generate", *GEN_ARGS, "--json"]) == cli.EXIT_ERROR
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "interrupted"
    assert [s["key"] for s in payload["sections"]] == ["problem"]
    assert "--resume " + payload["run_id"] in captured.err

    run_env["use"]([_sentence("선행", ["alio:1#0"])])
    assert cli.main(["generate", "--resume", payload["run_id"], "--json"]) == cli.EXIT_OK
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["status"] == "done"
    assert resumed["sections"][1]["sentences"][0] == {
        "text": "선행",
        "evidence": ["alio:1#0"],
        "source": "retrieved",
    }


def test_runs_list_and_show(run_env, capsys):
    run_env["use"]([_sentence("문제"), _sentence("선행", ["alio:1#0"])])
    cli.main(["generate", *GEN_ARGS, "--json"])
    run_id = json.loads(capsys.readouterr().out)["run_id"]

    assert cli.main(["runs", "list"]) == cli.EXIT_OK
    assert f"{run_id}  done" in capsys.readouterr().out
    assert cli.main(["runs", "show", run_id, "--json"]) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["citations"][0]["doc_id"] == "alio:1"


def test_generate_progress_shows_parse_failure_reason(run_env, capsys):
    bad = "설명:\n```json\n" + _sentence("문제") + "\n```"
    run_env["use"]([bad, bad, _sentence("선행", ["alio:1#0"])])  # 교정 재요청도 같은 오류
    cli.main(["generate", *GEN_ARGS])
    assert "section:problem 완료 (문장 0, 폐기 0, 응답 " in (err := capsys.readouterr().err)
    assert "파싱 실패: fence)" in err


def test_runs_show_unknown_or_malformed_id(run_env, capsys):
    run_env["use"]([])
    assert cli.main(["runs", "show", "../../etc"]) == cli.EXIT_ERROR
    assert "오류" in capsys.readouterr().err


def test_resume_of_finished_run_is_an_error(run_env, capsys):
    run_env["use"]([_sentence("문제"), _sentence("선행", ["alio:1#0"])])
    cli.main(["generate", *GEN_ARGS, "--json"])
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    assert cli.main(["generate", "--resume", run_id]) == cli.EXIT_ERROR
    assert "재개할 수 없습니다" in capsys.readouterr().err


# ── 양식 개정: 선택 확정 · 입력 재사용 · 예산 ───────────────────
FORM_KEYS = ["title", "task_type"]


def _choice(ids, text="사유"):
    return json.dumps({"choices": ids, "sentences": [{"text": text, "evidence": []}]})


@pytest.fixture
def form_env(monkeypatch, docs, chunks):
    from rra.application.services import RunManager
    from rra.application.usecases.generate_proposal import GenerateProposal
    from rra.domain.rules.lint import ChoiceSpec, LintRules
    from tests.fakes import (
        FakeLLM,
        FakePromptLibrary,
        FakeRenderer,
        FakeRunLog,
        FakeSlot,
        FakeTaskRunner,
        InMemoryRepository,
        InMemoryRunStore,
    )

    repo = InMemoryRepository()
    repo.seed(docs, chunks)
    store = InMemoryRunStore()
    renderer = FakeRenderer()
    env = {"store": store, "llm": None, "renderer": renderer}

    class ClosingLLM(FakeLLM):
        async def aclose(self):
            pass

    def build(settings, **kw):
        rules = LintRules(
            template="v2",
            required_sections=FORM_KEYS,
            choices={"task_type": ChoiceSpec(options="task_types")},
        )
        gen = GenerateProposal(env["llm"], repo, FakePromptLibrary(), rules, FORM_KEYS)
        return RunManager(
            gen,
            store,
            FakeSlot(),
            FakeRunLog(),
            FakeTaskRunner(),
            renderer=renderer,
            line_limits={"proposer.name": 2},  # 렌더 전 점검: 한 줄 칸 초과 알림 (제목은 제한 없음)
        )

    env["use"] = lambda responses: env.__setitem__("llm", ClosingLLM(responses))
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_run_manager", build)
    return env


def test_generate_shows_proposed_choice_then_confirm(form_env, capsys):
    form_env["use"]([_sentence("제목"), _choice(["applied"])])
    assert cli.main(["generate", *GEN_ARGS]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "선택 — 제안: applied / 확정: 미확정" in out
    run_id = out.split("[run ", 1)[1].split("]", 1)[0]

    assert cli.main(["runs", "confirm", run_id, "--task-type", "development"]) == cli.EXIT_OK
    assert "task_type: development" in capsys.readouterr().out
    assert cli.main(["runs", "show", run_id, "--json"]) == cli.EXIT_OK
    task = json.loads(capsys.readouterr().out)["sections"][1]["choices"]
    assert task["proposed"] == [{"id": "applied", "label": "응용연구"}]
    assert task["confirmed"] == [{"id": "development", "label": "개발연구"}]


def test_runs_finalize_writes_owner_only_file_and_keeps_proposer_out_of_runs(
    form_env, tmp_path, capsys
):
    import os

    form_env["use"]([_sentence("제목"), _choice(["applied"])])
    cli.main(["generate", *GEN_ARGS])
    run_id = capsys.readouterr().out.split("[run ", 1)[1].split("]", 1)[0]
    cli.main(["runs", "confirm", run_id, "--task-type", "applied"])
    capsys.readouterr()
    out = tmp_path / "out" / "p.hwpx"
    code = cli.main(
        [
            "runs",
            "finalize",
            run_id,
            "--out",
            str(out),
            "--proposer-name",
            "홍길동",
            "--proposer-phone",
            "010-9",
            "--proposed-on",
            "2026-10-23",
            "--department",
            "기술연구처",
        ]
    )
    printed = capsys.readouterr().out
    assert code == cli.EXIT_OK and "저장:" in printed
    assert "상태: finalized (v1) 확정: task_type=applied" in printed
    # 렌더 전 점검이 먼저 찍히고, 알림이 있어도 저장은 된다
    assert "렌더 전 점검: 알림 1건 (렌더는 진행합니다)" in printed
    assert "칸 길이 초과(한 줄 칸): 제안자 성명 3자 > 2자" in printed
    assert printed.index("렌더 전 점검") < printed.index("저장:")
    assert out.is_file() and os.stat(out).st_mode & 0o777 == 0o600
    body = json.loads(out.read_bytes())
    assert body["proposer"]["proposer"]["name"] == "홍길동" and body["confirmed"]["task_type"] == [
        "applied"
    ]
    store = form_env["store"]
    dumped = json.dumps({k: str(v) for k, v in vars(store).items()}, ensure_ascii=False)
    assert "홍길동" not in dumped and "010-9" not in dumped  # run 폴더(저장소)에 없다
    assert form_env["renderer"].calls[-1]["proposer"].proposer.name == "홍길동"
    assert form_env["renderer"].calls[-1]["proposer"].department == "기술연구처"
    assert cli.main(["runs", "versions", run_id]) == cli.EXIT_OK
    assert " v1   local" in capsys.readouterr().out
    assert cli.main(["runs", "reopen", run_id]) == cli.EXIT_OK
    assert "상태 editing" in capsys.readouterr().out
    assert cli.main(["runs", "review", run_id]) == cli.EXIT_OK  # 검토 LLM 없음 → 건너뜀
    assert "건너뜀 기록(review_skipped)" in capsys.readouterr().out


def test_runs_finalize_refusal_is_a_usage_error(form_env, tmp_path, capsys):
    from rra.application.ports.renderer import RenderRejected

    class Refusing:
        def render(self, draft, *, confirmation=None, proposer=None):
            raise RenderRejected("확정되지 않은 선택형 항목: task_type")

    form_env["renderer"].render = Refusing().render
    form_env["use"]([_sentence("제목"), _choice(["applied"])])
    cli.main(["generate", *GEN_ARGS])
    run_id = capsys.readouterr().out.split("[run ", 1)[1].split("]", 1)[0]
    out = tmp_path / "p.hwpx"
    assert cli.main(["runs", "finalize", run_id, "--out", str(out)]) == cli.EXIT_USAGE
    assert "마무리 거부: 확정되지 않은" in capsys.readouterr().err and not out.exists()


def test_confirm_rejects_values_outside_the_rules(form_env, capsys):
    form_env["use"]([_sentence("제목"), _choice(["applied"])])
    cli.main(["generate", *GEN_ARGS, "--json"])
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    assert cli.main(["runs", "confirm", run_id, "--strategy", "D1-1"]) == cli.EXIT_USAGE
    assert "확정 거부" in capsys.readouterr().err
    assert cli.main(["runs", "confirm", run_id]) == cli.EXIT_USAGE


def test_generate_stores_budget_and_extra_fields_but_no_personal_info(form_env, capsys):
    form_env["use"]([_sentence("제목"), _choice(["basic"])])
    args = [*GEN_ARGS, "--policy-basis", "국가철도망 구축계획", "--department", "기술연구처"]
    args += ["--budget-account", "연구개발비", "--budget-amount", "50000", "--json"]
    assert cli.main(["generate", *args]) == cli.EXIT_OK
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    req = form_env["store"].requests[("local", run_id)]
    assert req.policy_basis == "국가철도망 구축계획" and req.department == "기술연구처"
    assert req.budget.account == "연구개발비" and req.budget.amount_thousand_krw == 50000


def test_generate_reads_budget_from_file(form_env, tmp_path, capsys):
    import yaml

    path = tmp_path / "in.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "current_state": "수작업",
                "root_cause": "센서 부재",
                "limitation": "주기 점검",
                "goal": "자동 감지",
                "title_hint": "궤도 감지",
                "budget": {"account": "연구개발비", "amount_thousand_krw": 30000},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    form_env["use"]([_sentence("제목"), _choice(["basic"])])
    assert cli.main(["generate", "--file", str(path), "--json"]) == cli.EXIT_OK
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    req = form_env["store"].requests[("local", run_id)]
    assert req.title_hint == "궤도 감지" and req.budget.amount_thousand_krw == 30000


def test_legacy_run_resume_points_to_reuse_input(form_env, req, capsys):
    from rra.domain.models.run import plan_steps

    store = form_env["store"]
    old = store.create("local", req, plan_steps(["background", "prior_work"]), "t")
    old.status = "interrupted"
    store.save_state(old)

    form_env["use"]([])
    assert cli.main(["generate", "--resume", old.run_id]) == cli.EXIT_ERROR
    assert f"--reuse-input {old.run_id}" in capsys.readouterr().err

    assert cli.main(["runs", "show", old.run_id]) == cli.EXIT_OK
    assert "이전 양식으로 만든 run" in capsys.readouterr().out

    form_env["use"]([_sentence("제목"), _choice(["basic"])])
    assert cli.main(["generate", "--reuse-input", old.run_id, "--json"]) == cli.EXIT_OK
    fresh = json.loads(capsys.readouterr().out)
    assert fresh["run_id"] != old.run_id and fresh["template"] == "v2" and not fresh["legacy"]
    assert store.requests[("local", fresh["run_id"])].goal == req.goal


def test_resume_and_reuse_input_are_exclusive(capsys):
    with pytest.raises(SystemExit):
        cli.main(["generate", "--resume", "a", "--reuse-input", "b"])


# ── sources check · 키 없는 ingest ─────────────────────────
def test_sources_check_prints_presence_only(monkeypatch, capsys):
    async def fake_run():
        return [
            {
                "source": "ntis",
                "credentials": {"RRA_NTIS_KEY": True},
                "host": "www.ntis.go.kr",
                "host_allowed": True,
                "roundtrip": "ok",
                "result": {"total": 12, "record_tag_candidates": ["HIT"]},
            },
            {
                "source": "scienceon",
                "credentials": {"RRA_SCIENCEON_MAC": False},
                "host": "apigateway.kisti.re.kr",
                "host_allowed": True,
                "roundtrip": "skipped",
            },
        ]

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_sources_check", lambda settings, names: fake_run)
    assert cli.main(["sources", "check"]) == cli.EXIT_ERROR  # 하나라도 ok 가 아니면 1
    out = capsys.readouterr().out
    assert "RRA_NTIS_KEY=있음" in out and "RRA_SCIENCEON_MAC=없음" in out
    assert '"record_tag_candidates": ["HIT"]' in out


def test_ingest_without_key_reports_variable_name(monkeypatch, capsys):
    from rra.settings import Settings

    monkeypatch.setattr("rra.composition.load_settings", lambda: Settings(_env_file=None))
    assert cli.main(["ingest", "--source", "ntis"]) == cli.EXIT_ERROR
    assert "RRA_NTIS_KEY" in capsys.readouterr().err


def test_precheck_shows_shared_keywords(stub, capsys):
    stub.alerts = [
        alert(blocking=True).model_copy(update={"keywords": ["궤도", "틀림"]}),
        alert().model_copy(update={"similarity": 0.83}),
    ]
    cli.main(["precheck", *SLOT_ARGS])
    out = capsys.readouterr().out
    assert "[키워드: 궤도, 틀림]" in out and "[키워드 없음]" in out


# ── runs purge (보안 I 보존기간) ───────────────────────────
def test_runs_purge_dry_run_then_delete(monkeypatch, capsys):
    from datetime import UTC, datetime

    from rra.application.usecases.purge_runs import PurgeRuns
    from rra.domain.models import ProposalRequest
    from tests.fakes import InMemoryRunStore

    store = InMemoryRunStore()
    req = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
    old = store.create("local", req, ["a"], "2026-01-01T00:00:00+00:00")
    old.status, old.updated_at = "done", "2026-01-01T00:00:00+00:00"
    store.save_state(old)
    fresh = store.create("local", req, ["a"], "2026-10-20T00:00:00+00:00")
    fresh.status = "done"
    store.save_state(fresh)
    purge = PurgeRuns(store, 180, clock=lambda: datetime(2026, 10, 23, tzinfo=UTC))
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr("rra.composition.build_purge_runs", lambda settings: purge)

    assert cli.main(["runs", "purge", "--dry-run"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "삭제 대상 1건" in out and f"- local/{old.run_id}" in out
    assert ("local", old.run_id) in store.states

    assert cli.main(["runs", "purge", "--json"]) == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert [r["run_id"] for r in report["deleted"]] == [old.run_id] and not report["dry_run"]
    assert set(store.states) == {("local", fresh.run_id)}


def test_reindex_and_db_backup_commands(monkeypatch, capsys, tmp_path):
    from pathlib import Path

    from rra.application.usecases.maintain_db import BackupDatabase, ReindexDocuments

    class Maint:
        async def reindex(self):
            return {"chunks": 12, "dim": 768, "model": "intfloat/multilingual-e5-base"}

        async def backup(self, out):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"db")
            return Path(out)

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.build_db_maintenance",
        lambda settings: (ReindexDocuments(Maint()), BackupDatabase(Maint())),
    )
    assert cli.main(["reindex"]) == cli.EXIT_OK
    assert (
        "재색인 완료: 청크 12개, 차원 768, 모델 intfloat/multilingual-e5-base"
        in capsys.readouterr().out
    )
    assert cli.main(["db", "backup", "--out", str(tmp_path / "bk"), "--keep", "3"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "백업: " in out and "rra-" in out and "보관 1벌, 삭제 0벌" in out
    assert len(list((tmp_path / "bk").glob("rra-*.sqlite"))) == 1


def test_llm_check_provider_gemini_without_key_is_a_usage_error(monkeypatch, capsys):
    from rra.settings import Settings

    monkeypatch.delenv("RRA_GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("rra.composition.load_settings", lambda: Settings(_env_file=None))
    assert cli.main(["llm-check", "--provider", "gemini"]) == cli.EXIT_USAGE
    out, err = capsys.readouterr()
    assert "provider=gemini" in out and "api_key=RRA_GEMINI_API_KEY 없음" in out
    assert "reasoning_effort=low json_mode=auto" in out
    assert "LLM 사용 불가" in err and "RRA_GEMINI_API_KEY" in err


def test_api_schema_exports_openapi_without_token_or_db(monkeypatch, tmp_path, capsys):
    from rra.settings import Settings

    monkeypatch.setattr(
        "rra.composition.load_settings",
        lambda: Settings(_env_file=None, runs_dir=tmp_path / "runs", db_path=tmp_path / "x.sqlite"),
    )
    out = tmp_path / "docs" / "openapi.json"
    assert cli.main(["api", "schema", "--out", str(out)]) == cli.EXIT_OK
    assert "저장:" in capsys.readouterr().out
    schema = json.loads(out.read_text(encoding="utf-8"))
    paths = set(schema["paths"])
    for p in (
        "/v1/session",
        "/v1/sources/status",
        "/v1/precheck",
        "/v1/search",
        "/v1/runs",
        "/v1/runs/{run_id}",
        "/v1/runs/{run_id}/events",
        "/v1/runs/{run_id}/draft",
        "/v1/runs/{run_id}/versions",
        "/v1/runs/{run_id}/revert",
        "/v1/runs/{run_id}/review",
        "/v1/runs/{run_id}/edits",
        "/v1/runs/{run_id}/render-check",
        "/v1/runs/{run_id}/finalize",
        "/v1/runs/{run_id}/reopen",
        "/healthz",
    ):
        assert p in paths, p
    assert "/v1/runs/{run_id}/file" not in paths
    assert not (tmp_path / "x.sqlite").exists()
