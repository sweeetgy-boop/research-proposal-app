"""레인 D REST — 화면 머리 제목·목록, 내려받기 파일 이름, run 입력 조회·변경 미리보기·다시 쓰기,
근거 일괄 승인, 제출 전 점검의 한국어 설명·선택형 제안값, 사용 기록 줄 목록 (가짜 LLM)."""

from __future__ import annotations

import json
from urllib.parse import unquote

import httpx
import pytest

from tests.entrypoints.test_api import AUTH, SLOTS, build

METHOD = json.dumps(
    [{"text": "새 제약에 맞춘 분석 일정임", "evidence": ["openalex:W1#0"]}], ensure_ascii=False
)
UTIL = json.dumps(
    {"choices": ["software"], "sentences": [{"text": "시설처가 적용함", "evidence": []}]},
    ensure_ascii=False,
)


@pytest.fixture
async def client():
    app, assistant = build()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    ) as c:
        c.assistant = assistant  # type: ignore[attr-defined]
        yield c


async def drafted(client) -> str:
    r = await client.post("/v1/runs", json={**SLOTS, "title_hint": "가제"}, headers=AUTH)
    assert r.status_code == 202
    rid = r.json()["run_id"]
    await client.assistant.manager.wait("local", rid)
    return rid


async def test_run_payloads_carry_the_research_title(client):
    rid = await drafted(client)
    st = (await client.get(f"/v1/runs/{rid}", headers=AUTH)).json()
    assert st["title"] == "궤도 틀림 열화 예측 연구" and st["created_at"]
    runs = (await client.get("/v1/runs", headers=AUTH)).json()["runs"]
    assert runs[0]["run_id"] == rid and runs[0]["title"] == "궤도 틀림 열화 예측 연구"
    flow = st["flow"]
    assert flow["draft_review_skipped"] and flow["draft_review_skipped_label"].startswith(
        "1차 검토"
    )


async def test_finalize_download_uses_title_and_version_in_rfc5987_filename(client):
    rid = await drafted(client)
    mgr = client.assistant.manager
    v = store_version(mgr, rid)
    r = await client.post(f"/v1/runs/{rid}/finalize", json={}, headers=AUTH)
    assert r.status_code == 200, r.text
    cd = r.headers["content-disposition"]
    assert cd.startswith(f"attachment; filename=\"proposal-{rid}-v{v}.hwpx\"; filename*=UTF-8''")
    assert unquote(cd.split("UTF-8''", 1)[1]) == f"궤도 틀림 열화 예측 연구_v{v}.hwpx"
    cd.encode("latin-1")  # 헤더는 ASCII 만 (한글은 퍼센트 인코딩)


def store_version(mgr, rid) -> int:
    return mgr.store.load_state("local", rid).draft_version


async def test_run_request_preview_and_regenerate_routes(client):
    rid = await drafted(client)
    got = (await client.get(f"/v1/runs/{rid}/request", headers=AUTH)).json()
    assert got["request"]["goal"] == SLOTS["goal"] and got["draft_version"] == 1
    changed = {**got["request"], "constraints": "연구기간 1년"}
    r = await client.post(
        f"/v1/runs/{rid}/request/preview", json={"request": changed}, headers=AUTH
    )
    body = r.json()
    assert r.status_code == 200 and body["fields"] == [
        {"field": "constraints", "label": "제약 조건"}
    ]
    assert [s["key"] for s in body["sections"]] == ["method", "utilization"]
    assert body["sections"][0]["title"] == "2-다 연구 방법 및 주요내용" and body["can_regenerate"]
    client.assistant.manager.generate.llm.responses = [METHOD, UTIL]
    r = await client.post(
        f"/v1/runs/{rid}/regenerate",
        json={"request": changed, "mode": "sections", "base_version": 1},
        headers=AUTH,
    )
    out = r.json()
    assert r.status_code == 200, r.text
    assert out["version"] == 2 and out["origin"] == "regenerate" and out["mode"] == "sections"
    assert [s["key"] for s in out["regenerated"]] == ["method", "utilization"]
    assert out["failed"] == [] and out["status"] == "editing"
    stale = await client.post(
        f"/v1/runs/{rid}/regenerate",
        json={"request": changed, "mode": "all", "base_version": 1},
        headers=AUTH,
    )
    assert stale.status_code == 409  # 기준 버전이 바뀜
    bad = await client.post(
        f"/v1/runs/{rid}/regenerate", json={"request": changed, "mode": "x"}, headers=AUTH
    )
    assert bad.status_code == 422
    assert (
        await client.get("/v1/runs/20260101000000-ffffffff/request", headers=AUTH)
    ).status_code == 404


async def test_bulk_approve_and_submit_check_labels(client):
    rid = await drafted(client)
    check = (await client.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)).json()
    items = {i["key"]: i for i in check["items"]}
    ev = items["evidence_approval"]
    assert ev["label"] == "근거 확인" and ev["bulk"] >= 1 and "/" not in ev["detail"]
    alerts = items["unresolved_alerts"]
    for row in alerts["by_label"]:
        assert (
            row["label"]
            and row["label"] != row["code"]
            and row["severity_label"] in ("오류", "주의")
        )
    assert "_" not in alerts["detail"]  # 코드가 아니라 설명
    choices = items["choices_confirmed"]["choices"]
    task = next(c for c in choices if c["key"] == "task_type")
    assert (
        task["proposed"] == ["applied"]
        and {"id": "applied", "label": "응용연구"} in task["options"]
    )
    r = await client.post(
        f"/v1/runs/{rid}/evidence-decisions/bulk-approve", json={"base_version": 1}, headers=AUTH
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    assert "근거 일괄 승인" in r.json()["note"]
    check = (await client.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)).json()
    ev = {i["key"]: i for i in check["items"]}["evidence_approval"]
    assert ev["ok"] and ev["bulk"] == 0
    usage = (await client.get(f"/v1/runs/{rid}/usage", headers=AUTH)).json()["usage"]
    assert usage["total_label"] == "전체 경과(사람 작업 포함)"
    labels = {s["key"]: s["label"] for s in usage["steps"]}
    assert labels.get("sections") == "섹션 작성" and labels.get("retrieve") == "근거 검색"


async def test_draft_problems_carry_korean_labels(client):
    rid = await drafted(client)
    d = (await client.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()
    for p in d["problems"]:
        assert p["label"] and p["severity_label"] in ("오류", "주의", "참고")
    rc = (await client.get(f"/v1/runs/{rid}/render-check", headers=AUTH)).json()
    for p in rc["unresolved"]:
        assert p["label"] and p["severity_label"]


def test_openapi_lists_lane_d_paths():
    app, _ = build()
    paths = set(app.openapi()["paths"])
    for p in (
        "/v1/runs/{run_id}/request",
        "/v1/runs/{run_id}/request/preview",
        "/v1/runs/{run_id}/regenerate",
        "/v1/runs/{run_id}/evidence-decisions/bulk-approve",
    ):
        assert p in paths, p
