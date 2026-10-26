"""Streamlit — 유사과제 표 아래 추천 카드.

자동 추천, 다시 받기, 선택 → 미리보기 → 확정, 원래 아이디어로 진행.
"""

from __future__ import annotations

from tests.entrypoints.ui.fake_app import FakeRecommend, make_assistant
from tests.entrypoints.ui.test_app import app, button, login, service, submit_form  # noqa: F401


def test_cards_show_after_precheck_and_choice_fills_the_request(app):  # noqa: F811
    at = submit_form(login(app(blocking=False)))
    assert at.session_state["rra_rec"] is not None
    assert any("자동으로 추천" in c.value for c in at.caption)
    labels = [e.label for e in at.expander]
    assert any(x.startswith("추천 1. 검측 이력 기반") for x in labels)
    assert any(x.startswith("추천 2. 보수 우선순위") for x in labels)
    radio = at.radio(key="rec_pick")
    assert len(radio.options) == 2
    radio.set_value(radio.options[1])
    at = at.run()
    button(at, "이 방향으로 진행").click()
    at = at.run()
    assert at.session_state["rra_rec_preview"] is not None
    assert any("수정 전 미리보기" in m.value for m in at.markdown)
    at.text_input(key="rec_title").input("보수 우선순위 산정 모형 (수정)")
    at = at.run()
    button(at, "이 입력으로 확정").click()
    at = at.run()
    req = at.session_state["rra_request"]
    assert req.title_hint == "보수 우선순위 산정 모형 (수정)"
    assert req.differentiation == "기존 과제는 우선순위를 다루지 않음"
    assert "(추천 과제 보완)" in req.goal and at.session_state["rra_rec_chosen"] == 1
    assert "확정했습니다" in at.success[-1].value
    trace = [t.tool for t in at.session_state["rra_intake"].decisions]
    assert "rra_recommend" in trace


def test_original_idea_and_again_button(app):  # noqa: F811
    at = submit_form(login(app(blocking=False)))
    button(at, "원래 아이디어로 진행").click()
    at = at.run()
    assert "원래 아이디어" in at.success[-1].value and "rra_rec_chosen" not in at.session_state
    before = at.session_state["rra_rec"]
    button(at, "추천 다시 받기").click()
    at = at.run()
    assert at.session_state["rra_rec"] is not before and at.session_state["rra_rec"] is not None


def test_zero_recommendations_show_reason_only(app, monkeypatch):  # noqa: F811
    at = app()  # fixture 가 build_assistant 를 먼저 바꾸므로 그 뒤에 덮어쓴다
    monkeypatch.setattr(
        service,
        "build_assistant",
        lambda: make_assistant(recommend=FakeRecommend(count=0)),
    )
    at = submit_form(login(at))
    assert any("추천하지 않은 이유" in i.value for i in at.info)
    assert not any(b.label == "이 방향으로 진행" for b in at.button)
