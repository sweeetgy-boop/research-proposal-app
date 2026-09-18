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


def test_unimplemented_commands_report_clearly(capsys):
    assert cli.main(["generate"]) == cli.EXIT_USAGE
    assert "아직 구현 전" in capsys.readouterr().err


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
        fetched={"openalex": 5}, normalized={"openalex": 4}, skipped={"openalex": 1},
        deduped=1, stored=3, chunks=3,
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
