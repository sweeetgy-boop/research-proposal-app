"""② 유사과제 흐름 REST — 가짜 모드 전체 경로 (2026-10-28 레인 A).

AI 같음 판정(가짜 Argon) → [유사함]/[관련 없음] 선택 → 차단 해제 → 비교표(원문 추출) → 활용 제안 →
과제안(goal·method·scope) → [AI로 다듬기] → 생성 요청(선택·과제안 버전) → 선택 기록·idea_versions →
초안 기준 비교표. 실제 LLM·임베딩·reranker 없이(가짜 모드 + pipeline reranker 끔).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

TOKEN = "precheck-flow-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
IDEA = {
    "current_state": "궤도 틀림이 반복 발생함 (중복)",
    "root_cause": "다짐 효과가 오래 가지 않음",
    "limitation": "주기적 보수로는 진행 속도를 반영하지 못함",
    "goal": "검측 이력 기반 보수 우선순위 산정",
    "title_hint": "궤도 보수 우선순위 산정",
}
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def parts(tmp_path, monkeypatch):
    from rra import composition
    from rra.adapters.logging.choice_log import MemoryChoiceLog

    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    pipe = cfg / "pipeline.yaml"
    pipe.write_text(
        pipe.read_text(encoding="utf-8").replace("reranker: true", "reranker: false"),
        encoding="utf-8",
    )
    captured: dict = {"log": MemoryChoiceLog()}
    real = composition.build_fake_parts

    def capture(settings):
        out = real(settings)
        captured["store"] = out["store"]
        return out

    monkeypatch.setattr(composition, "build_fake_parts", capture)
    monkeypatch.setattr(composition, "build_choice_log", lambda settings=None: captured["log"])
    from rra.settings import Settings

    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never.sqlite",
        static_dir=tmp_path / "no-dist",
        config_dir=cfg,
    )
    captured["app"] = composition.build_api(settings, sse_poll_sec=0.01)
    return captured


async def test_precheck_flow_choices_comparison_cards_polish_and_run(parts):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=parts["app"]), base_url="http://127.0.0.1:8000"
    ) as c:
        pre = (await c.post("/v1/precheck", json=IDEA, headers=AUTH)).json()
        # AI 같음 판정: 가짜 Argon 이 첫 후보를 same → 차단, 나머지는 차단 아님
        assert pre["judgment"]["status"] == "ai" and pre["judgment"]["judged_by_label"] == "Argon"
        assert pre["judgment"]["retry_available"] is False
        first = pre["alerts"][0]
        assert first["blocking"] and first["judgment"] == "same" and first["judgment_label"] == "같다"
        assert first["judgment_reason"] and first["judged_by"] == "argon"
        assert all(not a["blocking"] for a in pre["alerts"][1:])
        assert pre["blocking"] and pre["gate_reason"].startswith("차단 경보를 확인해 주세요")
        assert "differentiation" not in pre  # [유사함] 을 고르기 전에는 활용 제안 없음
        cards = pre["recommendations"]["recommendations"]
        assert len(cards) == 2 and cards[0]["method"] and cards[0]["goal"]
        assert pre["core_keywords"]  # 핵심 키워드 (가짜 키워드 LLM)

        # 비교표 — 고른 행이 없으면 기존 과제 행 없음 + 안내
        cmp0 = (await c.post("/v1/precheck/comparison", json=IDEA, headers=AUTH)).json()
        assert cmp0["comparison"]["projects"] == []
        assert cmp0["comparison"]["empty_reason"] == "유사한 과제를 고르면 비교표가 만들어집니다"
        assert cmp0["comparison"]["proposal"]["title"] == "궤도 보수 우선순위 산정"
        assert cmp0["comparison"]["proposal"]["cells"]["method"].startswith("정보 없음")
        assert "현행 한계" not in str(cmp0["comparison"]["proposal"]["cells"])

        # 차단 행을 [관련 없음], 다른 행을 [유사함] → 차단 해제
        others = [a["doc_id"] for a in pre["alerts"][1:]]
        choices = [{"doc_id": first["doc_id"], "choice": "unrelated"}] + [
            {"doc_id": d, "choice": "similar"} for d in others[:1]
        ]
        chosen = {**IDEA, "similar_choices": choices}
        view = (await c.post("/v1/precheck/choices", json=chosen, headers=AUTH)).json()
        assert view["blocking"] is False and view["released"] is True and view["released_note"]
        assert view["gate_reason"] is None and view["similar_count"] == len(others[:1])

        cmp1 = (await c.post("/v1/precheck/comparison", json=chosen, headers=AUTH)).json()
        table = cmp1["comparison"]
        assert [p["doc_id"] for p in table["projects"]] == others[:1]
        assert table["extraction"] == "ai" and table["extraction_label"].startswith("기존 과제 칸은")
        assert table["projects"][0]["cells"]["scope"] == "정보 없음"

        diff0 = (await c.post("/v1/precheck/differentiate", json=IDEA, headers=AUTH)).json()
        assert diff0["differentiation"]["skipped_reason"] == "no_similar_selected"
        assert diff0["differentiation"]["skipped_label"].startswith("유사함으로 고른 과제가 없어")
        diff1 = (await c.post("/v1/precheck/differentiate", json=chosen, headers=AUTH)).json()
        assert [i["doc_id"] for i in diff1["differentiation"]["items"]] == others[:1]

        again = (await c.post("/v1/precheck/recommendations", json=chosen, headers=AUTH)).json()
        rec = again["recommendations"]
        assert rec["similar_doc_ids"] == others[:1] and len(rec["recommendations"]) == 2

        polished = (
            await c.post(
                "/v1/precheck/plan/polish",
                json={"request": chosen, "field": "goal", "text": "검측 이력 기반 보수 우선순위 산정"},
                headers=AUTH,
            )
        ).json()
        assert polished["changed"] is True and polished["by"] == "argon"
        assert polished["text"].startswith("검측 이력 기반 보수 우선순위 산정")

        retry = (await c.post("/v1/precheck/judgment", json=IDEA, headers=AUTH)).json()
        assert retry["judgment"]["status"] == "ai"

        card = cards[0]
        run_body = {
            **chosen,
            "title_hint": card["title"],
            "goal": card["goal"],
            "method": card["method"],
            "scope": card["scope"],
            "differentiation": card["differentiation"],
            "idea_versions": [
                {"kind": "original", "fields": {"goal": IDEA["goal"]}},
                {"kind": "card", "card_index": 0, "fields": {"title_hint": card["title"]}},
                {"kind": "edited", "fields": {"goal": "홍길동 010-1234-5678 확인 " + card["goal"]}},
            ],
        }
        r = await c.post("/v1/runs", json=run_body, headers=AUTH)
        assert r.status_code == 202, r.text  # 차단 행을 [관련 없음] 으로 골라 확인란 없이 생성
        run_id = r.json()["run_id"]
        for _ in range(200):
            state = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()
            if state["status"] not in ("queued", "running", "draft_reviewing"):
                break
            await asyncio.sleep(0.02)
        cmp2 = (await c.get(f"/v1/runs/{run_id}/comparison", headers=AUTH)).json()
        assert cmp2["comparison"]["proposal_source"] == "draft"

    records = parts["log"].records
    assert {r["doc_id"]: r["choice"] for r in records} == {
        first["doc_id"]: "unrelated",
        **{d: "similar" for d in others[:1]},
    }
    assert all(r["released"] for r in records) and all(len(r["idea"]) == 16 for r in records)
    assert "궤도" not in str(records)  # 원문·제목 없음 — doc_id·점수·해시만
    store = parts["store"]
    (versions,) = [v for v in store._idea_versions.values()]
    assert [v["kind"] for v in versions] == ["original", "card", "edited"]
    assert "010-1234-5678" not in str(versions)  # 개인정보 표식
