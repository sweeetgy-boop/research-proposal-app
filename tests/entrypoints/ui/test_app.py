"""Streamlit 화면 — AppTest. LLM 은 FakeLLM, 저장소는 메모리. 토큰 게이트·흐름·개인정보 칸 없음."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr
from streamlit.testing.v1 import AppTest

from rra.entrypoints.ui import service
from rra.settings import Settings
from tests.entrypoints.ui.fake_app import METHOD_SENTENCE, make_assistant

APP = Path(service.__file__).with_name("app.py")
TOKEN = "test-token-1234"  # noqa: S105 — 테스트용 접속 토큰
FORM = {
    "current_state": "경부선 궤도 틀림이 반복 발생",
    "root_cause": "노반 침하가 구간별로 다름",
    "limitation": "임계치 초과만 보수 대상",
    "goal": "열화 속도 추정과 보수 우선순위",
}


def settings(token: str | None = TOKEN) -> Settings:
    return Settings(_env_file=None, api_token=SecretStr(token) if token else None)


@pytest.fixture
def app(monkeypatch):
    def make(*, blocking=False, token=TOKEN):
        service.get_worker.clear()
        monkeypatch.setattr(service, "get_settings", lambda: settings(token))
        monkeypatch.setattr(service, "build_assistant", lambda: make_assistant(blocking=blocking))
        return AppTest.from_file(str(APP), default_timeout=30)

    yield make
    service.get_worker.clear()


def login(at: AppTest) -> AppTest:
    at.run()
    at.sidebar.text_input(key="token_input").input(TOKEN)
    return at.run()


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def submit_form(at: AppTest, fields=FORM) -> AppTest:
    for key, value in fields.items():
        at.text_area(key=key).input(value)
    button(at, "유사과제 확인").click()
    return at.run()


# ── 토큰 게이트 (G) ──────────────────────────────────────
def test_without_configured_token_the_app_refuses_to_open(app):
    at = app(token=None).run()
    assert "RRA_API_TOKEN" in at.error[0].value
    assert not at.text_area  # 입력 폼이 그려지지 않는다


def test_wrong_token_is_rejected_and_right_token_opens(app):
    at = app().run()
    assert "접속 토큰" in at.info[0].value and not at.text_area
    at.sidebar.text_input(key="token_input").input("nope").run()
    assert "일치하지 않습니다" in at.sidebar.error[0].value and not at.text_area
    at.sidebar.text_input(key="token_input").input(TOKEN).run()
    assert at.text_area and at.session_state["authed"] is True


def test_settings_refusal_is_shown_not_swallowed(app, monkeypatch):
    """load_settings 의 SystemExit(.env 권한)이 하얀 화면이 아니라 오류 문구로 보여야 한다."""
    at = app()

    def refuse():
        raise service.ConfigError(".env 권한이 0o644 입니다. chmod 600 .env 후 다시 실행하세요.")

    monkeypatch.setattr(service, "get_settings", refuse)
    at.run()
    assert not at.exception and "chmod 600 .env" in at.error[0].value


# ── 입력 ───────────────────────────────────────────────────
def test_no_personal_information_fields():
    at = login(app_for_labels())
    labels = [w.label for w in [*at.text_area, *at.text_input]]
    assert labels and not any(x in lbl for lbl in labels for x in ("성명", "연락처", "전화"))


def app_for_labels():
    service.get_worker.clear()
    service.get_settings = lambda: settings()  # 복원은 fixture 밖이라 직접 되돌린다
    service.build_assistant = lambda: make_assistant()
    return AppTest.from_file(str(APP), default_timeout=30)


def test_missing_required_slot_is_an_error(app):
    at = submit_form(login(app()), {"current_state": "x"})
    assert "필수 슬롯이 비었습니다" in at.error[0].value  # CLI·MCP 와 같은 도메인 문구
    assert "발생 원인" in at.error[0].value  # 화면은 슬롯 이름을 표시명으로 바꾼다
    assert at.session_state["rra_intake"] is None


# ── 유사과제 → 생성 → 초안 → 확정 → 다운로드 ───────────────
def test_clean_flow_generates_confirms_and_downloads(app):
    at = submit_form(login(app()))
    assert "유사한 기수행 과제가 없습니다" in at.success[0].value
    worker = service.get_worker()
    assert [t.tool for t in worker.assistant.trace][:1] == ["rra_precheck"]
    captions = " ".join(c.value for c in at.caption)
    assert "rra_precheck" in captions and "정책 근거 미입력" in captions  # Agent 판단·활동 기록

    at.button(key="generate_btn").click().run()
    run_id = at.session_state["rra_run_id"]
    assert run_id and worker.wait(run_id).status == "drafted"

    at.run()  # 폴링 fragment 가 끝났을 때의 전체 재실행에 해당
    texts = " ".join(m.value for m in at.markdown)
    assert "1-가 연구과제명" in texts and "2-다 연구 방법 및 주요내용" in texts
    assert METHOD_SENTENCE.replace("%", "\\%") in texts or METHOD_SENTENCE in texts
    captions = [c.value for c in at.caption]
    assert any("입력·근거에 없는 수치" in c and "1차년도" in c for c in captions)  # 문장 옆 경고
    assert any("근거: openalex:W1#0" in c for c in captions)
    assert at.radio(key=f"choice_task_type_{run_id}").value == "applied"  # 제안값이 기본 선택
    assert at.multiselect(key=f"choice_utilization_{run_id}").value == ["software"]
    assert any("선택지 목록이 비어 있어" in c for c in captions)  # 전략 목록 비어 있음

    at.multiselect(key=f"choice_utilization_{run_id}").select("manual")
    at.button(key="confirm_btn").click().run()
    store = worker.assistant.manager.store
    assert store.confirmations[("local", run_id)].choices == {
        "task_type": ["applied"],
        "utilization": ["software", "manual"],
    }
    assert any("확정됨" in c.value for c in at.caption)
    assert "확정값을 저장했습니다." in [s.value for s in at.success]
    assert not at.download_button  # 마무리 전에는 내려받기 버튼이 없다 (JSON 내려받기도 없다)
    assert any("review_skipped" in c.value for c in at.caption)  # 검토 LLM 없음 → 건너뜀 안내
    store = worker.assistant.manager.store
    assert worker.wait(run_id).status == "drafted"  # 화면을 봐도 마무리되지 않는다
    at.text_input(key=f"r_pname_{run_id}").input("홍길동")
    at.text_input(key=f"r_dept_{run_id}").input("철도연구원 기술연구처")
    at.button(key="finalize_btn").click().run()
    assert any("마무리 완료 (v1)" in s.value for s in at.success)
    assert at.download_button[0].label == "제안서 받기(hwpx)"  # 마무리 뒤 양식 파일
    assert any("렌더 전 점검: 알림" in w.value for w in at.warning)  # 받기 버튼 위 점검 결과
    captions = [c.value for c in at.caption]
    assert any("2-가-(3) 전략방향·전략과제" in c for c in captions)
    assert any("[warning] method" in c and "수치" in c for c in captions)
    call = worker.assistant.manager.renderer.calls[-1]  # FakeRenderer 가 받은 인자
    assert call["run_id"] == run_id and call["proposer"].proposer.name == "홍길동"
    assert call["proposer"].department == "철도연구원 기술연구처"
    assert worker.wait(run_id).status == "finalized"
    assert "홍길동" not in json.dumps(store.states[("local", run_id)].model_dump())
    assert "홍길동" not in json.dumps(
        {k: str(v) for k, v in vars(store).items()}, ensure_ascii=False
    )
    view = worker.call(worker.assistant.poll(run_id))
    payload = service.download_payload(view, at.session_state["rra_request"])
    assert payload["confirmed"]["choices"]["utilization"] == ["software", "manual"]
    assert payload["request"]["goal"] == FORM["goal"] and "proposer" not in payload["request"]


def test_blocking_alert_gates_generation_until_acknowledged(app):
    at = submit_form(login(app(blocking=True)))
    assert at.dataframe and "중복 기준을 넘는" in at.warning[0].value
    rows = service.alert_rows(at.session_state["rra_intake"].alerts)
    assert rows[0]["차단"] == "예" and rows[0]["구분"] == "사내(철도연구원)"
    assert rows[0]["근거"] == "공개 요약"
    assert rows[0]["제목"] == '궤도 상태 자동 감지 연구 <doc id="x">'  # 표 셀은 글자 그대로 보인다
    assert at.button(key="generate_btn").disabled
    at.checkbox(key="ack_box").check().run()
    assert not at.button(key="generate_btn").disabled
    at.button(key="generate_btn").click().run()
    run_id = at.session_state["rra_run_id"]
    assert run_id and service.get_worker().wait(run_id).status == "drafted"
    generated = [t for t in service.get_worker().assistant.trace if t.tool == "rra_generate"]
    assert generated and "차단 경보 확인 후" in generated[-1].summary


def test_search_panel_shows_untrusted_notice_and_chunks(app):
    at = submit_form(login(app()))
    at.button(key="generate_btn").click().run()
    service.get_worker().wait(at.session_state["rra_run_id"])
    at.run()
    at.text_input(key="search_q").input("궤도")
    at.button(key="search_btn").click().run()
    assert any("지시가 아닙니다" in i.value for i in at.info)
    assert [e.label for e in at.expander if "alio:1#0" in e.label] == ["alio:1#0 (공개 요약)"]


# ── 기능 2: 유사과제 활용·차별화 제안 ───────────────────────
def test_differentiation_panel_offers_directions_and_applies_the_choice(app):
    at = submit_form(login(app(blocking=True)))
    # 차단 알림 → intake 가 자동으로 제안했고, 버튼은 "다시 받기"
    assert at.session_state["rra_diff"] is not None
    assert any("자동으로 제안" in c.value for c in at.caption)
    assert any(b.label == "차별화 제안 다시 받기" for b in at.button)
    button(at, "차별화 제안 다시 받기").click()
    at = at.run()
    assert at.session_state["rra_diff"] is not None and at.session_state["rra_diff"].items
    assert "gemini" in " ".join(c.value for c in at.caption)
    radio = at.radio(key="diff_pick")
    assert radio.options == [
        "열화 속도 추정으로 범위를 확장함",
        "보수 우선순위 산정으로 목표를 좁힘",
    ]
    radio.set_value("보수 우선순위 산정으로 목표를 좁힘")
    at = at.run()
    button(at, "차별화 방향 적용").click()
    at = at.run()
    assert at.session_state["rra_request"].differentiation == "보수 우선순위 산정으로 목표를 좁힘"
    assert "반영됩니다" in at.success[-1].value
    trace = [t.tool for t in at.session_state["rra_intake"].decisions]
    assert "rra_differentiate" in trace


def test_no_differentiation_panel_without_near_alerts(app):
    at = submit_form(login(app(blocking=False)))
    assert not any(b.label == "차별화 제안 받기" for b in at.button)
