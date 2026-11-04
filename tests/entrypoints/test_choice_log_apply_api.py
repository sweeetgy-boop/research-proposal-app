"""② 선택 기록 event·중복 한 줄 REST (ADR 0056 2026-11-04 후속) — 가짜 모드.

[선택 적용](POST /v1/precheck/choices?apply=true)은 event=apply 한 묶음, 같은 선택을 잇따라 다시
적용하면 쓰지 않고, 선택이 바뀌면 새로 쓴다. 생성 요청(POST /v1/runs)은 event=generate — 서명에
event 가 들어가므로 apply 뒤 같은 선택의 generate 도 남는다. 줄에는 주체 키·사번·아이디어 원문이
없다(해시만). 응답은 apply 유무와 상관없이 같고, 기록 실패는 막지 않는다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from rra.adapters.fake.auth import FAKE_STAFF
from rra.adapters.logging.choice_log import ALLOWED_KEYS

TOKEN = "choice-apply-token"  # noqa: S105 — 테스트용
AUTH = {"Authorization": f"Bearer {TOKEN}"}
IDEA = {
    "current_state": "궤도 틀림이 반복 발생함 (중복)",
    "root_cause": "다짐 효과가 오래 가지 않음",
    "limitation": "주기적 보수로는 진행 속도를 반영하지 못함",
    "goal": "검측 이력 기반 보수 우선순위 산정",
    "title_hint": "궤도 보수 우선순위 산정",
}
ROOT = Path(__file__).resolve().parents[2]
APPLY = "/v1/precheck/choices?apply=true"


class _FailingLog:
    """쓰기 실패(디스크 가득 등) — 한 번 실패한 뒤에는 쓴다."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.fail = True

    def append(self, records):
        if self.fail:
            self.fail = False
            raise OSError("disk full")
        self.records.extend(dict(r) for r in records)


def _app(tmp_path, monkeypatch, log):
    from rra import composition
    from rra.settings import Settings

    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    pipe = cfg / "pipeline.yaml"
    pipe.write_text(
        pipe.read_text(encoding="utf-8").replace("reranker: true", "reranker: false"),
        encoding="utf-8",
    )
    monkeypatch.setattr(composition, "build_choice_log", lambda settings=None: log)
    settings = Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never.sqlite",
        static_dir=tmp_path / "no-dist",
        config_dir=cfg,
    )
    return composition.build_api(settings, sse_poll_sec=0.01)


@pytest.fixture
def log():
    from rra.adapters.logging.choice_log import MemoryChoiceLog

    return MemoryChoiceLog()


@pytest.fixture
def app(tmp_path, monkeypatch, log):
    return _app(tmp_path, monkeypatch, log)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


async def _rows(c, headers=AUTH):
    pre = (await c.post("/v1/precheck", json=IDEA, headers=headers)).json()
    first, second = pre["alerts"][0], pre["alerts"][1]
    assert first["blocking"] and first["judgment"] == "same"
    return first["doc_id"], second["doc_id"]


def _body(*picks):
    return {
        **IDEA,
        "similar_choices": [{"doc_id": d, "choice": c, "source": s} for d, c, s in picks],
    }


async def test_apply_writes_once_repeat_skips_change_writes_and_generate_is_separate(app, log):
    async with _client(app) as c:
        first, second = await _rows(c)
        chosen = _body((first, "unrelated", "user"), (second, "similar", "ai_prefill"))

        # [선택 적용] — event=apply 한 묶음(선택한 행마다 한 줄)
        r = await c.post(APPLY, json=chosen, headers=AUTH)
        assert r.status_code == 200, r.text
        assert [(x["doc_id"], x["event"]) for x in log.records] == [
            (first, "apply"),
            (second, "apply"),
        ]
        # 같은 선택을 다시 적용 — 쓰지 않는다
        await c.post(APPLY, json=chosen, headers=AUTH)
        await c.post(APPLY, json=chosen, headers=AUTH)
        assert len(log.records) == 2

        # 출처만 바뀌어도 다른 선택 → 새로 쓴다
        resourced = _body((first, "unrelated", "user"), (second, "similar", "user"))
        await c.post(APPLY, json=resourced, headers=AUTH)
        assert len(log.records) == 4
        # 사이에 다른 선택이 기록됐으므로 처음 선택으로 돌아가면 다시 쓴다
        await c.post(APPLY, json=chosen, headers=AUTH)
        assert len(log.records) == 6
        assert {x["source"] for x in log.records[-2:]} == {"user", "ai_prefill"}

        # apply 없는 선택 반영(옛 호출)은 기록하지 않는다
        await c.post("/v1/precheck/choices", json=resourced, headers=AUTH)
        assert len(log.records) == 6

        # 생성 요청 — 같은 선택이라도 다른 사건(event=generate)이라 남는다
        r = await c.post("/v1/runs", json=chosen, headers=AUTH)
        assert r.status_code == 202, r.text
        assert [x["event"] for x in log.records[6:]] == ["generate", "generate"]
        # 같은 선택으로 잇따라 생성 — 쓰지 않는다
        r = await c.post("/v1/runs", json=chosen, headers=AUTH)
        assert r.status_code == 202, r.text
        assert len(log.records) == 8
        # 생성 뒤 같은 선택을 다시 적용 — 마지막 서명(generate)과 달라 남는다
        await c.post(APPLY, json=chosen, headers=AUTH)
        assert len(log.records) == 10 and log.records[-1]["event"] == "apply"

    for rec in log.records:
        assert set(rec) <= ALLOWED_KEYS and rec["event"] in ("apply", "generate")
        assert len(rec["idea"]) == 16
    flat = str(log.records)
    assert "궤도" not in flat and TOKEN not in flat  # 아이디어 원문·토큰 없음


async def test_response_is_identical_with_or_without_apply(app, log):
    async with _client(app) as c:
        first, second = await _rows(c)
        chosen = _body((first, "unrelated", "user"), (second, "similar", "ai_prefill"))
        plain = (await c.post("/v1/precheck/choices", json=chosen, headers=AUTH)).json()
        applied = (await c.post(APPLY, json=chosen, headers=AUTH)).json()
        assert plain == applied
        assert applied["blocking"] is False and applied["released"] is True
        # 선택이 없는 [선택 적용] — 쓸 것이 없다
        await c.post(APPLY, json=IDEA, headers=AUTH)
        assert len(log.records) == 2


async def test_sessions_are_separate_and_lines_carry_no_owner_or_staff_number(app, log):
    async with _client(app) as c:
        first, second = await _rows(c)
        chosen = _body((first, "unrelated", "user"))
        await c.post(APPLY, json=chosen, headers=AUTH)  # 관리 토큰
        assert len(log.records) == 1

        # 다른 로그인 주체(직원) — 같은 아이디어·같은 선택이라도 다른 세션이라 쓴다
        r = await c.post("/v1/session", json={"kind": "staff", "staff_no": FAKE_STAFF[0]})
        assert r.status_code == 200, r.text
        staff = {"X-RRA-CSRF": r.json()["csrf"]}
        r = await c.post(APPLY, json=chosen, headers=staff)
        assert r.status_code == 200, r.text
        assert len(log.records) == 2
        await c.post(APPLY, json=chosen, headers=staff)
        assert len(log.records) == 2

        # 같은 주체라도 아이디어가 다르면 다른 세션
        other = {**chosen, "goal": "다른 목표로 바꾼 아이디어"}
        await c.post(APPLY, json=other, headers=staff)
        assert len(log.records) == 3

    flat = str(log.records)
    assert FAKE_STAFF[0] not in flat and "staff:" not in flat and "admin" not in flat
    assert all(set(rec) <= ALLOWED_KEYS for rec in log.records)


async def test_log_failure_is_not_fatal_and_is_not_remembered(tmp_path, monkeypatch):
    log = _FailingLog()
    app = _app(tmp_path, monkeypatch, log)
    async with _client(app) as c:
        first, _ = await _rows(c)
        chosen = _body((first, "unrelated", "user"))
        r = await c.post(APPLY, json=chosen, headers=AUTH)
        assert r.status_code == 200 and log.records == []
        # 실패한 기록은 마지막 서명이 아니다 — 같은 선택을 다시 적용하면 이번에는 쓴다
        r = await c.post(APPLY, json=chosen, headers=AUTH)
        assert r.status_code == 200 and len(log.records) == 1
