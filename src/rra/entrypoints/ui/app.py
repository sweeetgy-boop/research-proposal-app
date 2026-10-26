"""연구과제 제안서 작성 보조 — Streamlit 화면 (기획서 Ⅱ 활용 시나리오).

입력 → [유사과제 확인] → (차단 경보 확인) → [초안 생성] → 진행 표시
→ 초안(문장별 근거·경고) → 선택형 확정 → 결과 JSON 다운로드 → 자료 질의.
사이드바에 Agent 활동 기록·최근 run.

이 파일은 위젯과 호출 순서만 안다.
판단은 domain/rules/agent_policy, 실행은 application/services/assistant 에 있다.
"""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from rra.application.ports import RunBusy, RunNotFound
from rra.application.ports.renderer import RenderRejected
from rra.application.services import (
    ConfirmRejected,
    HumanConfirmationRequired,
    QueueFull,
    RenderUnavailable,
    RunNotResumable,
)
from rra.application.services.run_manager import FinalizeRejected
from rra.domain.models import Budget, ProposalRequest
from rra.domain.models.request import SHORT_MAX, SLOT_MAX, validation_message
from rra.domain.models.run import ACTIVE
from rra.domain.rules import agent_policy as policy
from rra.domain.rules.differentiation import needs_differentiation
from rra.domain.rules.overlap import SOURCE_LABELS
from rra.domain.rules.trust import UNTRUSTED_NOTICE
from rra.entrypoints.ui import service
from rra.entrypoints.ui.auth import require_token
from rra.entrypoints.ui.labels import (
    BASIS,
    PROBLEM,
    SOURCE,
    STATUS,
    STATUS_PROJECT,
    TIER,
    clean,
    plain,
    section_title,
)
from rra.entrypoints.views import (
    draft_payload,
    render_check_lines,
    render_check_payload,
    review_payload,
)

FIELDS = {
    "current_state": ("현재 상황·문제", True),
    "root_cause": ("발생 원인", True),
    "limitation": ("현행 대응의 한계", True),
    "goal": ("해결 목표", True),
    "title_hint": ("가제", False),
    "policy_basis": ("정책·계획 근거 (정책적 중요도의 유일한 근거)", False),
    "constraints": ("제약 (예산·기간·현장 조건)", False),
    "department": ("제안부서", False),
    "beneficiaries": ("활용 주체 부서", False),
    "remarks": ("특이사항", False),
}
# 제안자 성명·연락처는 받지 않는다 (개인정보 — 렌더 시점 입력).

st.set_page_config(page_title="연구과제 제안서 작성 보조", layout="wide")
try:
    settings = service.get_settings()
    require_token(settings)
    worker = service.get_worker()
except service.ConfigError as exc:
    st.error(f"설정 오류로 화면을 열 수 없습니다: {exc}")
    st.stop()
assistant = worker.assistant
ss = st.session_state
ss.setdefault("rra_request", None)
ss.setdefault("rra_intake", None)
ss.setdefault("rra_run_id", None)
ss.setdefault("rra_diff", None)


# ── 1. 입력 → [유사과제 확인] ─────────────────────────────
def intake_form() -> None:
    st.subheader("1. 과제 아이디어 입력")
    with st.form("intake"):
        cols = st.columns(2)
        for i, (key, (label, required)) in enumerate(FIELDS.items()):
            with cols[i % 2]:
                if key in ("title_hint", "department"):
                    st.text_input(label, key=key, max_chars=SHORT_MAX)
                else:
                    st.text_area(
                        f"{label}{' *' if required else ''}", key=key, max_chars=SLOT_MAX, height=90
                    )
        b1, b2 = st.columns(2)
        b1.text_input("예산과목", key="budget_account", max_chars=SHORT_MAX)
        b2.number_input("소요예산 (천원)", key="budget_amount", min_value=0, step=1000, value=0)
        submitted = st.form_submit_button("유사과제 확인", type="primary")
    if not submitted:
        return
    try:  # 필수 슬롯·길이 규칙은 도메인 모델이 검사한다 — 화면은 메시지로 바꾸기만 한다
        amount = int(ss.get("budget_amount") or 0)
        budget = Budget(account=ss.get("budget_account") or "", amount_thousand_krw=amount or None)
        req = ProposalRequest(**{k: ss.get(k) or "" for k in FIELDS}, budget=budget)
    except ValidationError as exc:
        labels = {k: label for k, (label, _) in FIELDS.items()}
        st.error(f"입력 오류 — {plain(validation_message(exc, labels))}")
        return
    ss["rra_request"] = req
    ss["rra_intake"] = worker.call(assistant.intake(req))
    ss["rra_run_id"] = None
    ss["rra_diff"] = None


# ── 2. 유사과제 표 + Agent 판단 ───────────────────────────
def alerts_panel() -> bool:
    """차단 경보 확인 여부를 돌려준다."""
    res = ss["rra_intake"]
    st.subheader("2. 유사과제 확인")
    if res.alerts:
        st.dataframe(service.alert_rows(res.alerts), hide_index=True, width="stretch")
    else:
        st.success("유사한 기수행 과제가 없습니다.")
    if res.uncollected:
        names = ", ".join(SOURCE_LABELS.get(s, s) for s in res.uncollected)
        st.caption(f"미수집 자료원(검토 범위 밖): {names}")
    with st.expander("Agent 판단", expanded=True):
        for d in res.decisions:
            mark = "⏸" if d.needs_human else ("🔧" if d.tool else "ℹ")
            st.caption(f"{mark} {d.condition} → {d.action}")
    acknowledged = False
    if policy.has_blocking(res.alerts):
        st.warning("중복 기준을 넘는 유사과제가 있습니다. 중복 여부의 최종 판단은 담당자가 합니다.")
        acknowledged = st.checkbox(
            "차단 경보를 확인했으며 그래도 초안 생성을 진행합니다", key="ack_box"
        )
    differentiation_panel()
    return acknowledged


# ── 2-나. 유사과제 활용·차별화 제안 (기능 2) ──────────────
def differentiation_panel() -> None:
    res = ss["rra_intake"]
    if not needs_differentiation(res.alerts):
        return
    st.markdown(
        "**유사과제 활용·차별화 제안** — 겹친 과제 결과를 이어받아 확장하는 방향을 제안합니다."
    )
    if st.button("차별화 제안 받기", key="diff_btn"):
        ss["rra_diff"] = worker.call(assistant.differentiate(ss["rra_request"], res.alerts))
    proposal = ss.get("rra_diff")
    if proposal is None:
        return
    if proposal.skipped_reason:
        st.info(f"차별화 제안을 만들지 못했습니다: {proposal.skipped_reason}")
        return
    where = "로컬 모델(대체)" if proposal.fallback_local else (proposal.provider or "LLM")
    st.caption(
        f"{where} · 전송 public {len(proposal.public_doc_ids)}건, internal "
        f"{len(proposal.internal_doc_ids)}건 · 폐기 {len(proposal.discarded)}건"
    )
    st.caption(UNTRUSTED_NOTICE)
    options: list[str] = []
    for item in proposal.items:
        status = f" · {STATUS_PROJECT.get(item.status or '', item.status)}" if item.status else ""
        with st.expander(
            f"{clean(item.title, 80)} ({TIER.get(item.tier, item.tier)}{status})", expanded=True
        ):
            st.write("겹치는 점: " + plain(item.overlap_summary))
            if item.build_on:
                st.write("이어받을 점: " + plain(item.build_on))
            for d in item.differentiation:
                st.write("→ " + plain(d))
                options.append(d)
    if not options:
        return
    pick = st.radio("차별화 방향 선택", options=options, index=None, key="diff_pick")
    text = st.text_area(
        "제안자가 정한 차별화 방향 (고른 방향을 고치거나 직접 적음)",
        value=pick or "",
        key="diff_text",
        max_chars=SLOT_MAX,
        height=80,
    )
    if st.button("차별화 방향 적용", key="diff_apply"):
        chosen = (text or pick or "").strip()
        ss["rra_request"] = ss["rra_request"].model_copy(update={"differentiation": chosen})
        st.success(
            "초안의 연구목적·연구방법·특이사항에 반영됩니다."
            if chosen
            else "차별화 방향을 비웠습니다."
        )


# ── 3. [초안 생성] → 진행 → 초안 ─────────────────────────
def generate_button(acknowledged: bool) -> None:
    res = ss["rra_intake"]
    can = policy.may_generate(res.alerts, acknowledged=acknowledged)
    if not st.button("초안 생성", key="generate_btn", type="primary", disabled=not can):
        return
    try:
        state = worker.call(
            assistant.proceed(
                ss["rra_request"],
                res.alerts,
                acknowledged=acknowledged,
                differentiation=ss.get("rra_diff"),
            )
        )
    except HumanConfirmationRequired as exc:
        st.error(str(exc))
        return
    except (QueueFull, RunBusy) as exc:
        st.error(f"지금은 생성할 수 없습니다: {exc}")
        return
    ss["rra_run_id"] = state.run_id
    st.rerun()


@st.fragment(run_every=2)
def progress_panel(run_id: str) -> None:
    """2초마다 state.json 을 읽어 다시 그린다. 끝나면 전체 화면을 다시 실행해 초안으로 넘어간다."""
    state = worker.call(assistant.poll(run_id)).state
    if state.status not in ACTIVE:
        st.rerun()
    done, total = state.progress
    st.progress(
        done / total if total else 0.0, text=f"{STATUS[state.status]} · {done}/{total} 단계"
    )
    for step in state.steps:
        if step.status == "done":
            extra = ""
            if step.name.startswith("section:"):
                extra = f" — 문장 {step.sentences}, 폐기 {step.dropped}, 파싱 {step.parse}"
            st.caption(f"✅ {step.name}{extra}")
        elif step.started_at:
            st.caption(f"⏳ {step.name} …")
        else:
            st.caption(f"▫ {step.name}")


def draft_panel(view, run_id: str) -> None:
    payload = draft_payload(view)
    titles = assistant.rules.titles
    by_sentence: dict[tuple[str, int], list[dict]] = {}
    by_section: dict[str, list[dict]] = {}
    for p in payload["problems"]:
        if p.get("sentence") is None:
            by_section.setdefault(p["section"], []).append(p)
        else:
            by_sentence.setdefault((p["section"], p["sentence"]), []).append(p)
    if view.legacy:
        st.info("이전 양식으로 만든 run — 조회만 가능합니다.")
    for sec in payload["sections"]:
        key = sec["key"]
        st.markdown(f"#### {section_title(key, titles)}")
        for p in by_section.get(key, []):
            show = st.warning if p["severity"] == "warning" else st.error
            show(f"{PROBLEM.get(p['code'], p['code'])}: {plain(p['message'])}")
        if not sec["sentences"]:
            st.caption("(빈칸)")
        for i, s in enumerate(sec["sentences"]):
            st.markdown(plain(s["text"]))
            meta = SOURCE.get(s["source"], s["source"])
            if s["evidence"]:
                meta += " · 근거: " + ", ".join(s["evidence"])
            st.caption(meta)
            for p in by_sentence.get((key, i), []):
                st.caption(f"⚠ {PROBLEM.get(p['code'], p['code'])}: {plain(p['message'])}")
    if payload["citations"]:
        with st.expander("인용 문서"):
            for c in payload["citations"]:
                st.caption(f"{c['id']} — {plain(c['title'] or '(제목 없음)', 120)}")
    confirm_panel(payload, view, run_id)
    review_panel(view)
    finalize_panel(view, run_id)


# ── 5. 검토 결과 (읽기 전용) ──────────────────────────────
def review_panel(view) -> None:
    """Argon 검토 결과는 읽기 전용 탭으로만 보여 준다 (편집·재검토는 CLI·API 에서)."""
    summary = view.state
    if summary.review_skipped and summary.review_rounds == 0:
        st.caption("검토: 검토 LLM 이 없어 건너뜀(review_skipped) — 바로 마무리할 수 있습니다.")
        return
    if view.review is None:
        if summary.status == "reviewing":
            st.caption("검토 진행 중…")
        return
    with st.expander(f"검토 결과 ({view.review.round}차, 읽기 전용)", expanded=False):
        payload = review_payload(view.review, clean=clean)
        if payload["scores"]:
            st.dataframe(
                [
                    {
                        "기준": s["criterion"],
                        "점수": f"{s['score']}/5" + (" ⚠" if s["weak"] else ""),
                        "근거": s["reason"],
                    }
                    for s in payload["scores"]
                ],
                hide_index=True,
                width="stretch",
            )
        t = payload["transfer"]
        st.caption(
            f"보낸 문장 {t['sentences_sent']} · 검토 제외 {t['sentences_excluded']} · "
            f"공개 자료 {len(t['public_doc_ids'])} · 사내 자료 {len(t['internal_doc_ids'])}"
        )
        for c in payload["comments"]:
            where = c["sentence_id"] or c["section"]
            mark = "수정안" if c["usable"] else ("폐기" if c["status"] == "discarded" else "의견")
            st.markdown(
                f"**{c['id']}** [{c['issue_type']}] {where} — {mark}: {plain(c['comment'])}"
            )
            if c["revised_text"]:
                st.caption(f"→ {plain(c['revised_text'])}")


# ── 6. 최종 마무리 및 다운로드 ────────────────────────────
def finalize_panel(view, run_id: str) -> None:
    """선택형 확정(확정값 없으면 제안값)·제안자 정보·렌더 전 점검·다운로드를 한 화면에서.

    내부적으로 finalize 를 호출한다 — 양식 파일은 이 경로로만 만들어진다. 제안자 정보는 저장하지
    않는다.
    """
    st.subheader("5. 최종 마무리 및 다운로드")
    if view.legacy or view.state.status not in ("done", "reviewed", "editing", "finalized"):
        st.caption("완료된 현행 양식 run 만 마무리할 수 있습니다 (검토 중에는 불가).")
        return
    with st.expander("양식 하단 정보 (파일에만 들어가고 저장되지 않습니다)", expanded=False):
        c = st.columns(4)
        proposed_on = c[0].text_input("제안일자 (비면 오늘)", key=f"r_on_{run_id}", max_chars=20)
        department = c[1].text_input("제안부서", key=f"r_dept_{run_id}", max_chars=100)
        p_rank = c[2].text_input("제안자 직급", key=f"r_prank_{run_id}", max_chars=100)
        p_name = c[3].text_input("제안자 성명", key=f"r_pname_{run_id}", max_chars=100)
        h = st.columns(4)
        p_phone = h[0].text_input("제안자 연락처", key=f"r_pphone_{run_id}", max_chars=100)
        h_rank = h[1].text_input("부서장 직급", key=f"r_hrank_{run_id}", max_chars=100)
        h_name = h[2].text_input("부서장 성명", key=f"r_hname_{run_id}", max_chars=100)
        h_phone = h[3].text_input("부서장 연락처", key=f"r_hphone_{run_id}", max_chars=100)
    proposer = service.proposer_info(
        proposed_on, (p_rank, p_name, p_phone), (h_rank, h_name, h_phone), department=department
    )
    if st.button("최종 마무리 및 다운로드", key="finalize_btn"):
        try:
            result = worker.call(
                assistant.manager.finalize(assistant.user, run_id, proposer=proposer)
            )
        except (RenderRejected, FinalizeRejected, ConfirmRejected) as exc:
            st.error(f"마무리할 수 없습니다: {plain(exc)}")
            return
        except RenderUnavailable as exc:
            st.error(plain(exc))
            return
        ss["rra_finalized"] = {
            "run_id": run_id,
            "version": result.version,
            "data": result.data,
            "lines": render_check_lines(
                render_check_payload(result.check, titles=assistant.rules.titles, clean=clean)
            ),
            "confirmed": result.confirmation.choices,
        }
    done = ss.get("rra_finalized")
    if not done or done["run_id"] != run_id:
        return
    st.success(
        f"마무리 완료 (v{done['version']}) — 확정: "
        + ", ".join(f"{k}={'/'.join(v)}" for k, v in done["confirmed"].items())
    )
    if done["lines"]:  # 렌더 전 점검 — 알림이 있어도 받을 수 있다
        st.warning(done["lines"][0])
        for line in done["lines"][1:]:
            st.caption(line)
    st.download_button(
        "제안서 받기(hwpx)",
        data=done["data"],
        file_name=f"proposal-{run_id}-v{done['version']}.hwpx",
        mime="application/hwp+zip",
        key="download_hwpx_btn",
    )


# ── 4. 선택형 확정 ────────────────────────────────────────
def confirm_panel(payload: dict, view, run_id: str) -> None:
    st.subheader("4. 선택형 항목 확정")
    if ss.pop("rra_confirmed_flash", None) == run_id:
        st.success("확정값을 저장했습니다.")
    picks: dict[str, list[str]] = {}
    for sec in payload["sections"]:
        choices = sec.get("choices")
        if choices is None:
            continue
        key = sec["key"]
        spec = assistant.rules.choices[key]
        options = {o["id"]: o["label"] for o in choices["options"]}
        label = section_title(key, assistant.rules.titles)
        if not options:
            st.caption(f"{label}: 선택지 목록이 비어 있어 확정할 수 없습니다.")
            continue
        current = choices["confirmed"] if choices["confirmed"] is not None else choices["proposed"]
        default = [c["id"] for c in current if c["id"] in options]
        wkey = f"choice_{key}_{run_id}"
        if spec.max == 1:
            picked = st.radio(
                label,
                list(options),
                index=list(options).index(default[0]) if default else None,
                format_func=options.get,
                key=wkey,
                horizontal=True,
            )
            picks[key] = [picked] if picked else []
        else:
            picks[key] = st.multiselect(
                label,
                list(options),
                default=default,
                max_selections=spec.max,
                format_func=options.get,
                key=wkey,
            )
        if choices["confirmed"] is not None:
            st.caption("확정됨: " + ", ".join(c["label"] for c in choices["confirmed"]))
    confirmable = view.state.status in ("done", "invalid") and not view.legacy
    if st.button("확정 저장", key="confirm_btn", disabled=not confirmable):
        try:
            worker.call(assistant.confirm(run_id, {k: v for k, v in picks.items() if v}))
        except ConfirmRejected as exc:
            st.error(f"확정 거부: {exc}")
            return
        ss["rra_confirmed_flash"] = run_id  # rerun 뒤에도 한 번 보이게
        st.rerun()


def run_panel(run_id: str) -> None:
    try:
        view = worker.call(assistant.poll(run_id))
    except RunNotFound:
        st.error("run 을 찾을 수 없습니다.")
        ss["rra_run_id"] = None
        return
    state = view.state
    st.subheader(f"3. 초안 — run {run_id} · {STATUS.get(state.status, state.status)}")
    if state.status in ACTIVE:
        progress_panel(run_id)
        return
    if state.status == "interrupted":
        st.warning("생성이 중단되었습니다. 완료된 섹션은 저장되어 있습니다.")
        if st.button("이어서 생성", key="resume_btn"):
            try:
                worker.call(assistant.resume(run_id))
            except (RunNotResumable, RunBusy) as exc:
                st.error(str(exc))
                return
            st.rerun()
        return
    if state.status == "failed":
        st.error("저장된 입력이 깨져 생성에 실패했습니다. 입력부터 다시 시작하십시오.")
        return
    draft_panel(view, run_id)


# ── 6. 자료 질의 → rra_search ─────────────────────────────
def search_panel() -> None:
    st.subheader("자료 질의")
    c1, c2 = st.columns([4, 1])
    query = c1.text_input("질의", key="search_q", max_chars=500)
    k = c2.slider("결과 수", 1, 10, 5, key="search_k")
    if st.button("검색", key="search_btn") and query.strip():
        ss["rra_search_results"] = worker.call(assistant.ask(query, k=k))
    results = ss.get("rra_search_results")
    if results is None:
        return
    st.info(UNTRUSTED_NOTICE)
    if not results:
        st.caption("검색 결과 없음")
    for c in results:
        basis = BASIS.get(c.basis or "", "원문")
        with st.expander(f"{c.chunk_id} ({basis})"):
            st.text(clean(c.text, 1500))


# ── 사이드바: Agent 활동 기록 · 최근 run ──────────────────
def sidebar() -> None:
    with st.sidebar:
        st.header("Agent 활동 기록")
        trace = assistant.trace[-20:]
        if not trace:
            st.caption("아직 호출이 없습니다.")
        for tc in reversed(trace):
            tool = tc.tool or "—"
            st.caption(f"{tc.at[11:19]} · {tc.condition} → {tool} · {plain(tc.summary, 160)}")
        st.header("최근 생성 기록")
        runs = worker.sync(assistant.list_runs, 10)
        ids = [r.run_id for r in reversed(runs)]
        status_of = {r.run_id: STATUS.get(r.status, r.status) for r in runs}
        pick = st.selectbox(
            "run", ids, index=None, key="pick_run", format_func=lambda r: f"{r} · {status_of[r]}"
        )
        if st.button("불러오기", key="load_run", disabled=pick is None):
            ss["rra_run_id"], ss["rra_request"], ss["rra_intake"] = pick, None, None
            st.rerun()


st.title("연구과제 제안서 작성 보조")
st.caption(
    "별지 제2호서식 초안 — 문장마다 근거 id, 규칙 경고는 문장 옆에. 선택형 항목은 담당자가 확정함."
)
intake_form()
if ss["rra_intake"] is not None and ss["rra_request"] is not None:
    ack = alerts_panel()
    if ss["rra_run_id"] is None:
        generate_button(ack)
if ss["rra_run_id"] is not None:
    run_panel(ss["rra_run_id"])
    search_panel()
sidebar()  # 마지막에 그려야 이번 실행의 Tool 호출까지 활동 기록에 보인다
