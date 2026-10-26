"""Streamlit — ①~⑥ stepper, ④ 섹션 편집·저장(새 버전), 버전 목록·복원, 검토 LLM 없으면 ⑥ 바로."""

from __future__ import annotations

from tests.entrypoints.ui.test_app import app, button, login, service, submit_form  # noqa: F401


def _generate(at):
    at.button(key="generate_btn").click().run()
    run_id = at.session_state["rra_run_id"]
    worker = service.get_worker()
    worker.wait(run_id)
    at.run()
    return at, run_id, worker


def test_stepper_and_edit_panel_save_makes_a_new_version(app):  # noqa: F811
    at = submit_form(login(app()))
    at, run_id, worker = _generate(at)
    captions = " ".join(c.value for c in at.caption)
    assert "● ④ 직접 수정·보완" in captions and "✓ ③ 초안 생성" in captions  # stepper
    assert any("검토 LLM 이 없어" in i.value for i in at.info)  # 검토 건너뜀 안내
    assert not any(b.label.startswith("Argon 최종 검토") for b in at.button)  # 키 없음 → ⑤ 없음
    # ④ 섹션 통문 편집 → 저장 → v2 (문장으로 나뉘고 같은 문장은 근거 유지)
    at.selectbox(key=f"edit_sec_{run_id}").select("method")
    at = at.run()
    key = next(k for k in at.session_state if k.startswith(f"edit_text_{run_id}_method"))
    at.text_area(key=key).input(
        "1차년도에 검측 이력을 분석해 보수 비용을 약 10% 절감함\n새로 쓴 문장임."
    )
    at.text_input(key=f"edit_memo_{run_id}").input("점검 수정")
    at.button(key=f"save_btn_{run_id}").click().run()
    store = worker.assistant.manager.store
    versions = store.list_versions(("local", run_id)[0], run_id)
    assert versions == [1, 2]
    v2 = store.load_version("local", run_id, 2)
    assert v2.origin == "edit" and v2.note == "점검 수정" and v2.changed_sections == ["method"]
    texts = [s.text for s in v2.section("method").sentences]
    assert texts[0].startswith("1차년도에") and texts[-1] == "새로 쓴 문장임."
    assert v2.section("method").sentences[-1].origin == "proposer_input"
    assert worker.wait(run_id).status == "editing"
    assert any("버전 2개" in e.label for e in at.expander)
    # 같은 내용 다시 저장 → 새 버전 없음
    at.button(key=f"save_btn_{run_id}").click().run()
    assert store.list_versions("local", run_id) == [1, 2]
    assert any("같은 내용" in i.value for i in at.info)


def test_restore_makes_a_new_version_and_finalize_still_works_without_review_llm(app):  # noqa: F811
    at = submit_form(login(app()))
    at, run_id, worker = _generate(at)
    at.selectbox(key=f"edit_sec_{run_id}").select("title")
    at = at.run()
    key = next(k for k in at.session_state if k.startswith(f"edit_text_{run_id}_title"))
    at.text_area(key=key).input("고친 제목")
    at.button(key=f"save_btn_{run_id}").click().run()
    at.selectbox(key=f"rest_{run_id}").select(1)
    at.button(key=f"restore_btn_{run_id}").click().run()
    store = worker.assistant.manager.store
    assert store.list_versions("local", run_id) == [1, 2, 3]
    assert store.load_version("local", run_id, 3).origin == "revert"
    assert store.load_version("local", run_id, 3).section("title").sentences[0].text != "고친 제목"
    at.text_input(key=f"r_pname_{run_id}").input("홍길동")
    at.button(key="finalize_btn").click().run()
    assert any("마무리 완료 (v3)" in s.value for s in at.success)
    assert worker.wait(run_id).status == "finalized"
    assert "홍길동" not in str(vars(store))
