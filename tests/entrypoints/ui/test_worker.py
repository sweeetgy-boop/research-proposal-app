"""화면 워커 — 자체 루프 스레드에서 유스케이스를 돌리고, 화면 스레드는 결과만 받는다."""

import threading

from rra.domain.models import ProposalRequest
from rra.entrypoints.ui.worker import Worker
from tests.entrypoints.ui.fake_app import make_assistant

REQ = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")


def test_calls_run_on_the_worker_thread_and_background_run_completes():
    worker = Worker(make_assistant)
    try:
        assert worker.sync(threading.get_ident) != threading.get_ident()
        a = worker.assistant
        res = worker.call(a.intake(REQ))
        state = worker.call(a.proceed(REQ, res.alerts, acknowledged=False))
        assert state.status == "queued"
        final = worker.wait(state.run_id)
        assert final.status == "drafted"
        assert worker.call(a.poll(state.run_id)).state.progress == (8, 8)  # + draft_review(건너뜀)
    finally:
        worker.close()
