"""Streamlit — Q1 입력 보강 질문: 질문이 있으면 생성 버튼을 막고, 답 반영 또는 건너뛰기 뒤
열린다."""

import pytest
from streamlit.testing.v1 import AppTest

from rra.entrypoints.ui import service
from tests.entrypoints.ui.fake_app import FakeClarify, make_assistant
from tests.entrypoints.ui.test_app import APP, TOKEN, login, settings, submit_form


@pytest.fixture
def app(monkeypatch):
    def make(questions=None):
        service.get_worker.clear()
        monkeypatch.setattr(service, "get_settings", lambda: settings(TOKEN))
        monkeypatch.setattr(
            service, "build_assistant", lambda: make_assistant(clarify=FakeClarify(questions))
        )
        return AppTest.from_file(str(APP), default_timeout=30)

    yield make
    service.get_worker.clear()


def test_questions_gate_generation_until_answered(app):
    at = submit_form(login(app()))
    assert at.text_area(key="clarify_0").label == "대상 노선은?"
    assert at.button(key="generate_btn").disabled
    at.text_area(key="clarify_0").input("경부선 전 구간")
    at.button(key="clarify_apply").click().run()
    assert at.session_state["rra_request"].supplement == "대상 노선은?: 경부선 전 구간"
    assert not at.button(key="generate_btn").disabled
    assert not [b for b in at.button if b.key == "clarify_apply"]
    captions = " ".join(c.value for c in at.caption)
    assert "rra_clarify" in captions  # Agent 활동 기록


def test_skip_keeps_the_request_and_no_questions_means_no_panel(app):
    at = submit_form(login(app()))
    at.button(key="clarify_skip").click().run()
    assert at.session_state["rra_request"].supplement == ""
    assert not at.button(key="generate_btn").disabled
    at2 = submit_form(login(app(questions=[])))
    assert not [t for t in at2.text_area if (t.key or "").startswith("clarify_")]
    assert not at2.button(key="generate_btn").disabled
