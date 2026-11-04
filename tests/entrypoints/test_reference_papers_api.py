"""참고 논문(reference, ADR 0053) REST — 가짜 모드(RRA_FAKE_LLM=1) 경로. 웹 e2e 가 쓰는 장면과 같다.

1. ② 관련 연구에 `scienceon:fake-1`(시드 논문)이 보이고, 그 id 가 참고 논문으로 읽힌다.
2. 아이디어 "(추천 없음)" + 참고 논문 0건 → 과제안 0건 · retry_used · hint "reference".
3. 같은 아이디어 + reference_ids=["scienceon:fake-1"] → 과제안 ≥1, 비교표 kind=reference 열,
   활용 제안 실행, [적용]·[더 만들기]·생성 요청이 reference_ids 를 지킨다.
참고 논문은 판정·차단·기본 선택·선택 기록에 쓰이지 않는다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

TOKEN = "reference-papers-token"  # noqa: S105 — 테스트용
AUTH = {"Authorization": f"Bearer {TOKEN}"}
# web/e2e/helpers.ts fillIdea 와 같은 입력
IDEA = {
    "current_state": "궤도 틀림이 반복 발생함",
    "root_cause": "다짐 효과가 오래 가지 않음",
    "limitation": "주기적 보수로는 진행 속도를 반영하지 못함",
    "goal": "검측 이력 기반 보수 우선순위 산정",
}
NONE_IDEA = {**IDEA, "current_state": "궤도 틀림이 반복 발생함 (추천 없음)"}
PAPER = "scienceon:fake-1"
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


def _client(parts):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=parts["app"]), base_url="http://127.0.0.1:8000"
    )


def _judged(body):
    keep = ("doc_id", "blocking", "judgment", "rule_blocking")
    return [{k: a.get(k) for k in keep} for a in body["alerts"]]


async def test_fake_related_research_paper_is_a_reference_that_does_not_touch_judgment(parts):
    async with _client(parts) as c:
        plain = (await c.post("/v1/precheck?stage=rule", json=IDEA, headers=AUTH)).json()
        assert PAPER in [r["doc_id"] for r in plain["related_research"]]
        assert PAPER not in [a["doc_id"] for a in plain["alerts"]]
        with_ref = {**IDEA, "reference_ids": [PAPER]}
        ref = (await c.post("/v1/precheck?stage=rule", json=with_ref, headers=AUTH)).json()
        assert _judged(ref) == _judged(plain) and ref["blocking"] == plain["blocking"]
        assert ref["default_choices"] == plain["default_choices"]
        # AI 판정도 같다
        j0 = (await c.post("/v1/precheck/judgment", json=IDEA, headers=AUTH)).json()
        j1 = (await c.post("/v1/precheck/judgment", json=with_ref, headers=AUTH)).json()
        assert _judged(j1) == _judged(j0) and j1["blocking"] == j0["blocking"]
        # 선택 기록에도 참고 논문은 남지 않는다
        choice = {
            **with_ref,
            "similar_choices": [{"doc_id": j0["alerts"][0]["doc_id"], "choice": "unrelated"}],
        }
        await c.post("/v1/precheck/choices", json=choice, headers=AUTH)
    assert PAPER not in str(parts["log"].records)
    # 6 자리 제한 — 참고 논문은 5건까지
    async with _client(parts) as c:
        r = await c.post(
            "/v1/precheck/recommendations",
            json={**IDEA, "reference_ids": [f"x:{i}" for i in range(6)]},
            headers=AUTH,
        )
        assert r.status_code == 422


async def test_no_similar_no_reference_gives_zero_cards_retry_and_reference_hint(parts):
    async with _client(parts) as c:
        await c.post("/v1/precheck?stage=rule", json=NONE_IDEA, headers=AUTH)
        body = (await c.post("/v1/precheck/recommendations", json=NONE_IDEA, headers=AUTH)).json()
        rec = body["recommendations"]
        assert rec["recommendations"] == [] and rec["no_recommendation_reason"]
        assert rec["retry_used"] is True and rec["hint"] == "reference"
        assert rec["reference_doc_ids"] == [] and rec["transfer"]["calls"] == 2


async def test_reference_turns_zero_into_cards_and_flows_through_comparison_and_run(parts):
    req = {**NONE_IDEA, "reference_ids": [PAPER]}
    async with _client(parts) as c:
        await c.post("/v1/precheck?stage=rule", json=req, headers=AUTH)
        body = (await c.post("/v1/precheck/recommendations", json=req, headers=AUTH)).json()
        rec = body["recommendations"]
        assert len(rec["recommendations"]) >= 1 and rec["hint"] is None
        assert rec["retry_used"] is False and rec["reference_doc_ids"] == [PAPER]
        card = rec["recommendations"][0]
        assert card["compared_with"] == [PAPER]
        assert [r["doc_id"] for r in card["refs"]] == [PAPER]

        # 비교표: [유사함] 0건 + 참고 논문 → 참고 논문 열만, 안내 없음, 모든 열에 kind
        table = (await c.post("/v1/precheck/comparison", json=req, headers=AUTH)).json()
        cmp = table["comparison"]
        assert cmp["empty_reason"] is None
        assert [(p["doc_id"], p["kind"]) for p in cmp["projects"]] == [(PAPER, "reference")]
        assert cmp["proposal"]["kind"] == "similar" and cmp["proposal"]["relevance"] is None
        # 검색 관련도 — 같은 입력의 ② 관련 연구 점수(가짜 저장소: 낱말 겹침 비율이라 늘 낮음)
        ref = cmp["projects"][0]
        assert ref["relevance"] == "low" and 0 < ref["similarity"] < 0.885

        # 활용 제안: [유사함] 0건이어도 참고 논문으로 실행
        diff = (await c.post("/v1/precheck/differentiate", json=req, headers=AUTH)).json()
        assert diff["differentiation"]["skipped_reason"] is None
        assert [i["doc_id"] for i in diff["differentiation"]["items"]] == [PAPER]

        # [적용] 미리보기 — 세션에 남은 입력의 reference_ids 를 그대로
        applied = (
            await c.post(
                f"/v1/precheck/recommendations/{rec['id']}/apply",
                json={"index": 0},
                headers=AUTH,
            )
        ).json()
        assert applied["request"]["reference_ids"] == [PAPER]

        # [더 만들기] — 참고 논문 유지
        more = (
            await c.post(
                "/v1/precheck/recommendations/more",
                json={"request": req, "rec_id": rec["id"]},
                headers=AUTH,
            )
        ).json()["recommendations"]
        assert more["reference_doc_ids"] == [PAPER] and more["hint"] is None

        # 생성 요청 — request.json 에 reference_ids 가 남는다
        r = await c.post(
            "/v1/runs", json={**applied["request"], "acknowledged": True}, headers=AUTH
        )
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]
    store = parts["store"]
    saved = [v for (_, rid), v in store.requests.items() if rid == run_id]
    assert saved and saved[0].reference_ids == [PAPER]
