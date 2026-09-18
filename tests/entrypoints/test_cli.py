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

    def __call__(self, req):
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
    assert cli.main(["precheck", *SLOT_ARGS[:6], "--goal", "가" * 2001]) == cli.EXIT_ERROR
    assert "오류:" in capsys.readouterr().err


def test_search_uses_the_same_untrusted_wrapping(monkeypatch, capsys, docs, chunks):
    from rra.application.usecases.precheck_overlap import PrecheckOverlap
    from tests.fakes import InMemoryRepository

    repo = InMemoryRepository()
    repo.upsert(docs, chunks)
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

    async def fake_fetch(settings):
        fetched.append(True)
        return tmp_path / "abc.csv"

    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    catalog = FakeCatalog(_alio_entries())
    monkeypatch.setattr("rra.composition.build_alio_catalog", lambda s: catalog)
    monkeypatch.setattr("rra.composition.fetch_alio_catalog", fake_fetch)
    assert cli.main(["alio", "catalog"]) == cli.EXIT_OK and not fetched
    assert "대상 기관 2건 (korail 1건, kr 1건)" in capsys.readouterr().out
    cli.main(["alio", "catalog", "--fetch"])
    assert fetched and "abc.csv" in capsys.readouterr().out


def test_alio_status(monkeypatch, capsys):
    monkeypatch.setattr("rra.composition.load_settings", lambda: None)
    monkeypatch.setattr(
        "rra.composition.alio_inbox_status",
        lambda s: {"pending": 3, "done": 5, "quarantine": 1},
    )
    assert cli.main(["alio", "status"]) == cli.EXIT_OK
    assert "대기 3 / 완료 5 / 격리 1" in capsys.readouterr().out


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
        InMemoryRepository,
        InMemoryRunStore,
    )

    repo = InMemoryRepository()
    repo.upsert(docs, chunks)
    store = InMemoryRunStore()
    env = {"store": store, "llm": None, "closed": 0}

    class ClosingLLM(FakeLLM):
        async def aclose(self):
            env["closed"] += 1

    def build(settings, **kw):
        llm = env["llm"]
        rules = LintRules(required_sections=GEN_KEYS, evidence_required=["prior_work"])
        gen = GenerateProposal(llm, repo, FakePromptLibrary(), rules, GEN_KEYS)
        return RunManager(gen, store, FakeSlot(), FakeRunLog())

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
    run_env["use"](
        ["설명:\n```json\n" + _sentence("문제") + "\n```", _sentence("선행", ["alio:1#0"])]
    )
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
