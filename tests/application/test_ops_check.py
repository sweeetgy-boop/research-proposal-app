"""운영 점검(ops_check)·llm-check(llm_check) 유스케이스 — 가짜 포트. 네트워크·명령 없음."""

from rra.application.ports.ops_status import (
    LocalLlmProbePort,
    OpsStatusPort,
    OpsStatusWriterPort,
    TunnelProbe,
    TunnelProbePort,
)
from rra.application.usecases.llm_check import (
    LlmCheck,
    default_timeout,
    is_local_provider,
)
from rra.application.usecases.ops_check import OpsCheck


class FakeStatus:
    def __init__(self):
        self.records = []

    def record(self, kind, state):
        self.records.append((kind, state))

    def snapshot(self):
        return None


class FakeTunnel:
    def __init__(self, backend, funnel):
        self.result = TunnelProbe(backend_state=backend, funnel_on=funnel)

    def probe(self):
        return self.result


class FakeLocal:
    def __init__(self, responded):
        self.responded = responded

    def probe(self):
        return self.responded


def test_fakes_satisfy_the_runtime_checkable_ports():
    assert isinstance(FakeStatus(), OpsStatusPort) and isinstance(FakeStatus(), OpsStatusWriterPort)
    assert isinstance(FakeTunnel("Running", True), TunnelProbePort)
    assert isinstance(FakeLocal(True), LocalLlmProbePort)


def test_ops_check_records_both_states_and_reports_one_line():
    status = FakeStatus()
    result = OpsCheck(status=status, local=FakeLocal(False), tunnel=FakeTunnel("Running", True))()
    assert (result.tunnel, result.llm_local) == ("ok", "unavailable")
    assert status.records == [("tunnel", "ok"), ("llm_local", "unavailable")]
    assert result.line() == "tunnel=ok llm_local=unavailable"


def test_ops_check_without_tailscale_leaves_tunnel_unknown_and_unrecorded():
    status = FakeStatus()
    result = OpsCheck(status=status, local=FakeLocal(True), tunnel=None)()
    assert result.tunnel == "unknown" and result.llm_local == "ok"
    assert status.records == [("llm_local", "ok")]
    # 명령은 있지만 값을 못 얻은 경우도 같다 (이전 기록이 15분 뒤 저절로 unknown)
    status2 = FakeStatus()
    OpsCheck(status=status2, local=FakeLocal(None), tunnel=FakeTunnel(None, None))()
    assert status2.records == []


def test_ops_check_tunnel_down_when_funnel_off_or_backend_stopped():
    status = FakeStatus()
    assert (
        OpsCheck(status=status, local=FakeLocal(True), tunnel=FakeTunnel("Running", False))().tunnel
        == "down"
    )
    assert (
        OpsCheck(status=status, local=FakeLocal(True), tunnel=FakeTunnel("Stopped", True))().tunnel
        == "down"
    )


# ── llm-check ────────────────────────────────────────────
class StubLLM:
    def __init__(self, outcome):
        self.outcome = outcome
        self.closed = False

    async def complete(self, prompt, *, system=None, max_tokens=None, json_mode=False):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def aclose(self):
        self.closed = True


class CodedError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


async def _warn():
    return "served_model 경고"


def test_default_timeout_is_120_for_local_and_none_for_remote():
    assert default_timeout("mlx") == 120.0 and default_timeout("local") == 120.0
    assert default_timeout("gemini") is None and default_timeout("openai") is None
    assert is_local_provider("MLX") and not is_local_provider("gemini")


async def test_llm_check_success_records_ok_for_local_and_closes_client():
    status, llm = FakeStatus(), StubLLM("[]")
    result = await LlmCheck(llm, provider="mlx", status=status, served_check=_warn())("안녕")
    assert result.output == "[]" and result.failure is None and result.local_state == "ok"
    assert result.warning == "served_model 경고" and result.seconds >= 0
    assert status.records == [("llm_local", "ok")] and llm.closed


async def test_llm_check_unresponsive_local_records_unavailable_without_raising():
    for code in ("timeout", "connection", "server"):
        status, llm = FakeStatus(), StubLLM(CodedError(code))
        result = await LlmCheck(llm, provider="mlx", status=status)("안녕")
        assert result.output is None and result.failure is llm.outcome
        assert result.unresponsive and result.local_state == "unavailable"
        assert status.records == [("llm_local", "unavailable")] and llm.closed


async def test_llm_check_other_failures_do_not_touch_local_state():
    status, llm = FakeStatus(), StubLLM(CodedError("invalid"))
    result = await LlmCheck(llm, provider="mlx", status=status)("안녕")
    assert result.failure is llm.outcome and result.local_state is None and status.records == []


async def test_llm_check_remote_never_records_local_state():
    status = FakeStatus()
    ok = await LlmCheck(StubLLM("ok"), provider="gemini", status=status)("안녕")
    bad = await LlmCheck(StubLLM(CodedError("timeout")), provider="gemini", status=status)("안녕")
    assert ok.local_state is None and bad.local_state is None and not bad.unresponsive
    assert status.records == []
