"""작성·편집 AI 경로 (레인 B, 2026-10-28) — 가짜 모드 전체 흐름.

③ 보강 질문(Argon 먼저) → 정책적 중요도 작성안(방향별, 근거 겹침 없음) → 고른 안으로 생성 →
2-가-(1) 이 작성안 그대로(근거 = 원문 대조 통과 구간) → ④ AI 다시 쓰기·보완 질문(Argon) → 변경 세기.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from rra.settings import Settings
from tests.entrypoints.test_api import AUTH, SLOTS, TOKEN

IDEA = {
    "current_state": "궤도 틀림이 반복 발생함",
    "root_cause": "다짐 효과가 오래 가지 않음",
    "limitation": "주기적 보수로는 진행 속도를 반영하지 못함",
    "goal": "검측 이력 기반 보수 우선순위 산정",
}


def _app(tmp_path, **kw):
    from rra.composition import build_api

    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never.sqlite",
        static_dir=tmp_path / "no-dist",
        **kw,
    )
    return build_api(settings, sse_poll_sec=0.01)


@pytest.fixture
async def client(tmp_path):
    app = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _wait(c, run_id, want=("drafted",)):
    status = None
    for _ in range(3000):  # 병렬 실행(-n auto) 부하에서도 기다리게 (최대 ~30초)
        status = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["status"]
        if status in want:
            return status
        await asyncio.sleep(0.01)
    return status


async def test_clarify_asks_argon_questions_and_a_policy_question_when_no_basis(client):
    r = await client.post("/v1/precheck/clarify", json=IDEA, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["policy_needed"] is True
    topics = [q["topic"] for q in body["questions"]]
    assert topics[0] == "policy" and "target" in topics and 2 <= len(topics) <= 4
    assert all(q["topic_label"] and q["question"] for q in body["questions"])
    assert body["source"] == "argon" and body["transfer"]["remote_calls"] == 1
    # 정책 근거가 있으면 정책 질문은 없다
    r = await client.post(
        "/v1/precheck/clarify", json={**IDEA, "policy_basis": "철도 안전 강화"}, headers=AUTH
    )
    assert "policy" not in [q["topic"] for q in r.json()["questions"]]


async def test_policy_cards_one_per_direction_with_disjoint_evidence(client):
    r = await client.post("/v1/ideas/policy-cards", json=IDEA, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    dirs = [c["direction"] for c in body["cards"]]
    assert dirs == ["government", "company", "audit"]  # 근거가 받쳐 주는 만큼만 (지역·사회 없음)
    docs = [s["doc_id"] for c in body["cards"] for s in c["sources"]]
    assert len(docs) == len(set(docs))  # 근거 겹침 없음
    card = body["cards"][0]
    assert card["direction_label"] == "정부 계획" and 1 <= len(card["sentences"]) <= 3
    src = card["sources"][0]
    assert src["title"] and src["year"] == 2025 and src["quote"] and src["url"]
    assert all(e == src["chunk_id"] for s in card["sentences"] for e in s["evidence"])
    # [다른 안 보기] — 본 문서를 빼면 남은 근거가 없다 → 해당 없음
    seen = [s["doc_id"] for c in body["cards"] for s in c["sources"]]
    r = await client.post(
        "/v1/ideas/policy-cards", json={**IDEA, "exclude_doc_ids": seen}, headers=AUTH
    )
    assert r.json()["status"] == "empty" and r.json()["status_label"].startswith("해당 없음")


async def test_chosen_card_becomes_policy_importance_with_verified_evidence(client):
    cards = (await client.post("/v1/ideas/policy-cards", json=IDEA, headers=AUTH)).json()["cards"]
    card = cards[1]  # 공사 전략
    forged = {**card["sources"][0], "chunk_id": "korail_web:nope#0", "doc_id": "korail_web:nope"}
    choice = {
        "mode": "card",
        "card_ids": [card["id"]],
        "sentences": [
            *card["sentences"],
            {"text": "위조 근거 문장임.", "evidence": ["korail_web:nope#0"]},
        ],
        "sources": [*card["sources"], forged],
    }
    r = await client.post(
        "/v1/runs", json={**IDEA, "acknowledged": True, "policy_choice": choice}, headers=AUTH
    )
    assert r.status_code in (200, 201, 202), r.text
    run_id = r.json()["run_id"]
    assert await _wait(client, run_id) == "drafted"
    draft = (await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
    sec = next(s for s in draft["sections"] if s["key"] == "policy_importance")
    texts = [s["text"] for s in sec["sentences"]]
    assert texts[: len(card["sentences"])] == [s["text"] for s in card["sentences"]]
    ok_id = card["sources"][0]["chunk_id"]
    assert sec["sentences"][0]["evidence"] == [ok_id]
    assert sec["sentences"][-1]["evidence"] == []  # 원문 대조 실패(위조) 근거는 빠진다 — 보안 A
    codes = {p["code"] for p in draft["problems"] if p["section"] == "policy_importance"}
    assert "evidence_forbidden" not in codes and "policy_basis_needed" not in codes


async def test_no_policy_basis_leaves_notice_and_submit_check_flag(client):
    r = await client.post(
        "/v1/runs",
        json={**IDEA, "acknowledged": True, "policy_choice": {"mode": "none"}},
        headers=AUTH,
    )
    run_id = r.json()["run_id"]
    assert await _wait(client, run_id) == "drafted"
    draft = (await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
    flagged = [p for p in draft["problems"] if p["code"] == "policy_basis_needed"]
    assert flagged and flagged[0]["message"].startswith("정책 근거 확인 필요")
    check = (await client.get(f"/v1/runs/{run_id}/submit-check", headers=AUTH)).json()
    item = next(i for i in check["items"] if i["key"] == "policy_basis")
    assert item["ok"] is False and "정책 근거 확인 필요" in item["detail"]
    alerts = next(i for i in check["items"] if i["key"] == "unresolved_alerts")
    assert "policy_basis_needed" not in alerts["detail"]  # 내부 코드를 보이지 않는다
    # ④ 빈 2-가-(1) — run 에서 작성안 → 고르기 → 새 버전, 알림이 사라진다
    cards = (await client.post(f"/v1/runs/{run_id}/policy-cards", json={}, headers=AUTH)).json()[
        "cards"
    ]
    choice = {
        "mode": "card",
        "card_ids": [cards[0]["id"]],
        "sentences": cards[0]["sentences"],
        "sources": cards[0]["sources"],
    }
    r = await client.post(f"/v1/runs/{run_id}/policy-choice", json={"choice": choice}, headers=AUTH)
    assert r.status_code == 200, r.text
    sec = next(s for s in r.json()["sections"] if s["key"] == "policy_importance")
    assert sec["sentences"] and sec["sentences"][0]["evidence"] == [
        cards[0]["sources"][0]["chunk_id"]
    ]
    draft = (await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
    bad = ("policy_basis_needed", "evidence_forbidden")
    assert not [p for p in draft["problems"] if p["code"] in bad]
    changes = (await client.get(f"/v1/runs/{run_id}/changes", headers=AUTH)).json()
    labels = {i["type"] for i in changes["items"]}
    assert {"policy_choice", "sentence_add"} <= labels and changes["total"] >= 2
    # run 에서 고른 정책 근거는 AI 다시 쓰기의 요지가 된다 — 더는 "정책 근거 없음" 사유가 아니다
    url = f"/v1/runs/{run_id}/sections/policy_importance/rewrite"
    body = (await client.post(url, headers=AUTH)).json()
    assert body["reason"] is None and body["new_count"] >= 1


async def test_polish_keeps_proposer_text_inside_quotes(client):
    cards = (await client.post("/v1/ideas/policy-cards", json=IDEA, headers=AUTH)).json()["cards"]
    choice = {"mode": "card", "sentences": cards[0]["sentences"], "sources": cards[0]["sources"]}
    r = await client.post(
        "/v1/ideas/policy-cards/polish",
        json={**IDEA, "choice": choice, "text": "○ 궤도 안전을 높이는 정부 방향과 이어짐."},
        headers=AUTH,
    )
    body = r.json()
    assert r.status_code == 200 and body["choice"]["mode"] == "edited"
    assert body["choice"]["sentences"][0]["text"] == "궤도 안전을 높이는 정부 방향과 이어짐."


async def test_rewrite_and_section_questions_use_argon_with_reasons(client):
    run_id = (await client.post("/v1/runs", json=SLOTS, headers=AUTH)).json()["run_id"]
    assert await _wait(client, run_id) == "drafted"
    for _ in range(3000):  # 자동 1차 검토(v2) 가 끝날 때까지
        if (await client.get(f"/v1/runs/{run_id}/review", headers=AUTH)).status_code == 200:
            break
        await asyncio.sleep(0.01)
    r = await client.post(f"/v1/runs/{run_id}/sections/method/rewrite", headers=AUTH)
    body = r.json()
    assert r.status_code == 200 and body["new_count"] >= 1 and body["reason"] is None
    assert body["writer"]["label"] == "Argon" and body["mode"] == "rewrite"
    # 정책 근거 없는 2-가-(1) — 후보 0 이면 사유(작성안으로 연결)
    r = await client.post(f"/v1/runs/{run_id}/sections/policy_importance/rewrite", headers=AUTH)
    body = r.json()
    assert body["new_count"] == 0 and body["reason"] == "policy_basis_needed"
    assert "작성안" in body["reason_label"] and body["mode"] == "new"
    # 보완 질문 — Argon 이 묻는다, 같은 버전은 보관한 결과
    q = (
        await client.get(f"/v1/runs/{run_id}/sections/tech_importance/questions", headers=AUTH)
    ).json()
    assert q["source"] == "argon" and len(q["questions"]) >= 2 and q["cached"] is False
    assert q["questions"][0]["element"] == "국외 동향"
    q2 = (
        await client.get(f"/v1/runs/{run_id}/sections/tech_importance/questions", headers=AUTH)
    ).json()
    assert q2["cached"] is True and q2["questions"] == q["questions"]
    # 답 저장 → 변경 세기의 보완 메모 + 다시 쓰기 프롬프트에 들어간다
    r = await client.post(
        f"/v1/runs/{run_id}/sections/tech_importance/answers",
        json={"answers": {"국외 동향": "독일 DB 가 2023년 예측 정비를 도입함"}},
        headers=AUTH,
    )
    assert r.status_code == 200
    changes = (await client.get(f"/v1/runs/{run_id}/changes", headers=AUTH)).json()
    assert {"type": "memo", "label": "보완 메모", "count": 1} in changes["items"]
    # 답이 다음 다시 쓰기 프롬프트의 [제안자 보완 메모] 로 들어간다 ([답 반영해 다시 쓰기])
    r = await client.post(f"/v1/runs/{run_id}/sections/tech_importance/rewrite", headers=AUTH)
    assert r.status_code == 200 and r.json()["new_count"] >= 1


async def _drafted_with_review(c, body):
    run_id = (await c.post("/v1/runs", json=body, headers=AUTH)).json()["run_id"]
    assert await _wait(c, run_id) == "drafted"
    for _ in range(3000):  # 자동 1차 검토(v2)
        if (await c.get(f"/v1/runs/{run_id}/review", headers=AUTH)).status_code == 200:
            break
        await asyncio.sleep(0.01)
    return run_id


async def test_rewrite_regression_every_section_gets_a_candidate_or_a_reason(client):
    """0후보 회귀(레인 B 근본 원인): 정책 근거 없는 2-가-(1) 은 LLM 없이 빈 후보를 조용히 돌려줬다.
    이제 정책 근거가 있으면 모든 섹션이 후보 ≥ 1, 앱이 쓰는 특이사항만 '해당 없음' 사유."""
    cards = (await client.post("/v1/ideas/policy-cards", json=IDEA, headers=AUTH)).json()["cards"]
    choice = {"mode": "card", "sentences": cards[0]["sentences"], "sources": cards[0]["sources"]}
    run_id = await _drafted_with_review(
        client, {**IDEA, "acknowledged": True, "policy_choice": choice}
    )
    draft = (await client.get(f"/v1/runs/{run_id}/draft", headers=AUTH)).json()
    out = {}
    for sec in draft["sections"]:
        r = await client.post(f"/v1/runs/{run_id}/sections/{sec['key']}/rewrite", headers=AUTH)
        assert r.status_code == 200, (sec["key"], r.text)
        out[sec["key"]] = (r.json()["new_count"], r.json()["reason"])
    assert len(out) == 12 and out.pop("overlap_review") == (0, "app_section")
    assert [k for k, (n, why) in out.items() if n < 1 or why is not None] == [], out
    # 제안자가 고른 작성안 문장은 보존된다
    url = f"/v1/runs/{run_id}/sections/policy_importance/rewrite"
    rows = (await client.post(url, headers=AUTH)).json()["rows"]
    kept = [r["candidate"]["text"] for r in rows if r["candidate"] and r["candidate"]["preserved"]]
    assert kept == [s["text"] for s in cards[0]["sentences"]]
    # 선택값(선택형)은 AI 다시 쓰기가 바꾸지 않는다
    task = (await client.post(f"/v1/runs/{run_id}/sections/task_type/rewrite", headers=AUTH)).json()
    v = (
        await client.get(f"/v1/runs/{run_id}/draft?version={draft['version']}", headers=AUTH)
    ).json()
    current = next(s for s in v["sections"] if s["key"] == "task_type")
    assert task["choices"] == current["choices"]


async def test_rewrite_failure_reports_reason_instead_of_empty(tmp_path, monkeypatch):
    """원격·로컬이 모두 실패하면 500 이 아니라 사유(호출 실패)로 0 후보."""
    app = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        run_id = await _drafted_with_review(c, SLOTS)
        from rra.adapters.fake.llm import ScriptedComposeLLM

        async def boom(self, prompt, **kw):
            raise TimeoutError("down")

        monkeypatch.setattr(ScriptedComposeLLM, "complete", boom)
        r = await c.post(f"/v1/runs/{run_id}/sections/method/rewrite", headers=AUTH)
        assert r.status_code == 200 and r.json()["new_count"] == 0
        assert r.json()["reason"] == "error" and r.json()["reason_label"] == "호출 실패"
