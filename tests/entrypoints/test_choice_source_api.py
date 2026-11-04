"""② 선택 출처 REST (ADR 0056) — 생성 요청의 선택 기록이 줄마다 source 를 남기고, source 가 있든
없든 ② 응답(차단·해제·건수·비교표·활용 제안·과제안)과 생성 게이트는 같다. 가짜 모드."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

TOKEN = "choice-source-token"  # noqa: S105 — 테스트용
AUTH = {"Authorization": f"Bearer {TOKEN}"}
IDEA = {
    "current_state": "궤도 틀림이 반복 발생함 (중복)",
    "root_cause": "다짐 효과가 오래 가지 않음",
    "limitation": "주기적 보수로는 진행 속도를 반영하지 못함",
    "goal": "검측 이력 기반 보수 우선순위 산정",
    "title_hint": "궤도 보수 우선순위 산정",
}
ROOT = Path(__file__).resolve().parents[2]
# 응답 중 매번 달라지는 칸(세션 id·시각) — 비교에서 뺀다
VOLATILE = {"id", "at", "created_at", "elapsed_ms"}


@pytest.fixture
def parts(tmp_path, monkeypatch):
    from rra import composition
    from rra.adapters.logging.choice_log import MemoryChoiceLog
    from rra.settings import Settings

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


def _strip(value):
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


async def test_run_choice_log_writes_source_and_behaviour_is_identical(parts):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=parts["app"]), base_url="http://127.0.0.1:8000"
    ) as c:
        pre = (await c.post("/v1/precheck", json=IDEA, headers=AUTH)).json()
        first, second = pre["alerts"][0], pre["alerts"][1]
        assert first["blocking"] and first["judgment"] == "same"
        # 차단 행([유사함] 미리 고름)을 제안자가 [관련 없음] 으로 바꿈 → user,
        # 둘째 행은 미리 고른 값 그대로 → ai_prefill
        default = {d["doc_id"]: d["choice"] for d in pre["default_choices"]}
        plain = [
            {"doc_id": first["doc_id"], "choice": "unrelated"},
            {"doc_id": second["doc_id"], "choice": default.get(second["doc_id"], "similar")},
        ]
        tagged = [{**plain[0], "source": "user"}, {**plain[1], "source": "ai_prefill"}]
        with_src = {**IDEA, "similar_choices": tagged}
        without = {**IDEA, "similar_choices": plain}

        # ② 응답은 source 와 상관없이 같다 (선택 반영·비교표·활용 제안·과제안)
        for path in (
            "/v1/precheck/choices",
            "/v1/precheck/comparison",
            "/v1/precheck/differentiate",
        ):
            a = (await c.post(path, json=with_src, headers=AUTH)).json()
            b = (await c.post(path, json=without, headers=AUTH)).json()
            assert _strip(a) == _strip(b), path
        view = (await c.post("/v1/precheck/choices", json=with_src, headers=AUTH)).json()
        assert view["blocking"] is False and view["released"] is True
        recs_a = (await c.post("/v1/precheck/recommendations", json=with_src, headers=AUTH)).json()
        recs_b = (await c.post("/v1/precheck/recommendations", json=without, headers=AUTH)).json()
        assert _strip(recs_a) == _strip(recs_b)

        # 생성 요청 — 차단 행을 [관련 없음] 으로 골라 확인란 없이 202 (source 유무와 상관없이)
        r1 = await c.post("/v1/runs", json=with_src, headers=AUTH)
        assert r1.status_code == 202, r1.text
        after_first = list(parts["log"].records)
        r2 = await c.post("/v1/runs", json=without, headers=AUTH)
        assert r2.status_code == 202, r2.text
        # source 가 없으면 user, 서버 기본 선택(고르지 않은 행)은 기록하지 않는다
        assert {r["doc_id"]: r["source"] for r in after_first} == {
            first["doc_id"]: "user",
            second["doc_id"]: "ai_prefill",
        }
        second_batch = parts["log"].records[len(after_first) :]
        assert {r["doc_id"]: r["source"] for r in second_batch} == {
            first["doc_id"]: "user",
            second["doc_id"]: "user",
        }
        drop = {"source", "at"}
        assert [{k: v for k, v in r.items() if k not in drop} for r in after_first] == [
            {k: v for k, v in r.items() if k not in drop} for r in second_batch
        ]

        # 차단 행을 고르지 않으면(미리 고른 [유사함] 그대로) source 가 있어도 생성은 409
        blocked = {
            **IDEA,
            "similar_choices": [
                {"doc_id": first["doc_id"], "choice": "similar", "source": "ai_prefill"}
            ],
        }
        r3 = await c.post("/v1/runs", json=blocked, headers=AUTH)
        assert r3.status_code == 409


async def test_run_request_keeps_source_in_similar_choices(parts):
    """run 의 request(request.json = model_dump(mode="json"))에 선택이 남으면 source 도 함께."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=parts["app"]), base_url="http://127.0.0.1:8000"
    ) as c:
        pre = (await c.post("/v1/precheck", json=IDEA, headers=AUTH)).json()
        first = pre["alerts"][0]
        pick = {"doc_id": first["doc_id"], "choice": "unrelated", "source": "user"}
        r = await c.post("/v1/runs", json={**IDEA, "similar_choices": [pick]}, headers=AUTH)
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]
    (stored,) = [v for (_, rid), v in parts["store"].requests.items() if rid == run_id]
    assert stored.model_dump(mode="json")["similar_choices"] == [pick]
