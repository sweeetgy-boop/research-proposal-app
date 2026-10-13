"""실제 HTTP 서버 + 웹소켓 — streamlit run 을 자식 프로세스로 띄워 브라우저가 하는 일을 그대로 한다.

AppTest 는 서버·웹소켓·.streamlit/config.toml 을 거치지 않는다. 여기서는
/_stcore/health → XSRF 쿠키 → /_stcore/stream 핸드셰이크(Origin 127.0.0.1) → rerun_script
→ new_session·delta·script_finished 까지 확인한다. 다른 Origin 은 거부(1008)되어야 한다
(127.0.0.1 전용 원칙).
cwd 는 임시 폴더(.env 없음, config.toml 복사본) — 사용자 .env 권한에 흔들리지 않는다.
"""

from __future__ import annotations

import http.cookiejar
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

websockets = pytest.importorskip("websockets")
from websockets.sync.client import connect  # noqa: E402

from rra.entrypoints.ui import service  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
APP = Path(service.__file__).with_name("app.py")
TOKEN = "server-test-token"  # noqa: S105 — 테스트용


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    cwd = tmp_path_factory.mktemp("ui-server")
    (cwd / ".streamlit").mkdir()
    shutil.copy(ROOT / ".streamlit" / "config.toml", cwd / ".streamlit" / "config.toml")
    port = _free_port()
    env = {
        **os.environ,
        "RRA_API_TOKEN": TOKEN,
        "RRA_CONFIG_DIR": str(ROOT / "config"),
        "RRA_RUNS_DIR": str(cwd / "runs"),
        "RRA_DB_PATH": str(cwd / "rra.sqlite"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)  # noqa: S603
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            if proc.poll() is not None:
                raise RuntimeError(proc.stdout.read().decode(errors="replace"))
            try:
                if b"ok" in urllib.request.urlopen(f"{base}/_stcore/health", timeout=1).read():  # noqa: S310
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("streamlit 서버가 뜨지 않음")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _xsrf_cookie(base: str) -> str:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.open(f"{base}/_stcore/health", timeout=5).read()
    return next(c.value for c in jar if c.name == "_streamlit_xsrf")


def _session_messages(base: str, origin: str, *, limit_s: float = 30) -> list[tuple[str, str]]:
    """브라우저처럼 접속해 서버가 보내는 ForwardMsg 를 (종류, 요약) 으로 모은다."""
    from streamlit.proto.BackMsg_pb2 import BackMsg
    from streamlit.proto.ClientState_pb2 import ClientState
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    xsrf = _xsrf_cookie(base)
    out: list[tuple[str, str]] = []
    with connect(
        base.replace("http://", "ws://") + "/_stcore/stream",
        subprotocols=["streamlit", xsrf],
        origin=origin,
        additional_headers={"Cookie": f"_streamlit_xsrf={xsrf}"},
        open_timeout=10,
    ) as ws:
        hello = BackMsg()
        hello.rerun_script.CopyFrom(ClientState())  # 프런트엔드가 접속 직후 보내는 첫 메시지
        ws.send(hello.SerializeToString())
        deadline = time.time() + limit_s
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=max(0.1, deadline - time.time()))
            except TimeoutError:
                break
            msg = ForwardMsg()
            msg.ParseFromString(raw)
            kind = msg.WhichOneof("type")
            detail = ""
            if kind == "delta" and msg.delta.WhichOneof("type") == "new_element":
                el = msg.delta.new_element
                et = el.WhichOneof("type")
                body = getattr(getattr(el, et), "body", "") if et else ""
                label = getattr(getattr(el, et), "label", "") if et else ""
                detail = f"{et} {body or label}"
            out.append((kind, detail))
            if kind == "script_finished":
                break
    return out


def test_http_and_websocket_render_the_token_gate(server):
    html = urllib.request.urlopen(f"{server}/", timeout=5).read().decode()  # noqa: S310
    assert '<div id="root">' in html
    msgs = _session_messages(server, origin=server)
    kinds = [k for k, _ in msgs]
    assert kinds[0] == "new_session" and "script_finished" in kinds, msgs
    deltas = [d for k, d in msgs if k == "delta"]
    assert any("접속 토큰" in d for d in deltas), deltas  # 사이드바 토큰 입력 칸
    assert any("사이드바에 접속 토큰을 입력" in d for d in deltas), deltas
    assert not any(d.startswith("exception") for d in deltas), deltas


def test_localhost_origin_is_also_accepted(server):
    port = server.rsplit(":", 1)[1]
    kinds = [k for k, _ in _session_messages(server, origin=f"http://localhost:{port}")]
    assert "script_finished" in kinds


def test_foreign_origin_is_rejected_before_accept(server):
    with pytest.raises((websockets.exceptions.InvalidStatus, OSError)):
        with connect(
            server.replace("http://", "ws://") + "/_stcore/stream",
            subprotocols=["streamlit"],
            origin="http://evil.example",
            open_timeout=10,
        ):
            pass
