"""L2 로컬 2차 검토 (ADR 0040) — 순서·판정 라벨·불일치 → Argon 제안 →
[반영](새 버전)/[무시](버전 없음)·제출 전 점검 개수. LLM·임베딩 없이 (가짜 모드 REST)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from rra.domain.models import Chunk, Section, Sentence
from rra.domain.rules.local_review import (
    batch_prompt,
    check_batches,
    is_priority_sentence,
    review_view,
    unresolved_count,
    validate_suggestion,
)
from rra.domain.rules.writer import local_check_problems, text_hash
from rra.settings import Settings
from tests.entrypoints.test_api import AUTH, SLOTS, TOKEN


def _sec(key, *texts, evidence=("alio:1#0",)):
    return Section(key=key, sentences=[Sentence(text=t, evidence=list(evidence)) for t in texts])


def test_priority_sentences_and_sections_come_first():
    assert is_priority_sentence("2025년까지 고장률을 30% 줄임.")
    assert is_priority_sentence("「제4차 국가철도망 구축계획」에 따라 추진함.")
    assert is_priority_sentence("국토교통부 철도안전 종합계획과 연계함.")
    assert not is_priority_sentence("현장 점검 방식을 개선함.")
    sections = [
        _sec("objective", "현장 점검 방식을 개선함.", "2025년까지 고장률을 30% 줄임."),
        _sec("method", "센서 자료를 분석함."),
        _sec("tech_importance", "선행연구와 다름."),
        _sec("policy_importance", "정책에 부합함."),
        Section(key="title", sentences=[Sentence(text="제목")]),  # 근거 없음 → 판정 안 함
    ]
    order = [(s.key, idx) for s, idx in check_batches(sections)]
    assert order == [
        ("policy_importance", [0]),
        ("tech_importance", [0]),
        ("objective", [1]),  # 수치 문장 먼저
        ("objective", [0]),
        ("method", [0]),
    ]
    prompt = batch_prompt(
        sections[0],
        [1],
        {"alio:1#0": Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="고장률 자료")},
    )
    assert '"sentence_id": "s:objective:1"' in prompt and "s:objective:0" not in prompt
    assert "뒷받침되는가" in prompt and "<doc" in prompt


def test_validate_suggestion_keeps_rewrites_inside_evidence():
    ev = [
        Chunk(
            chunk_id="a#0", doc_id="a", ordinal=0, text="궤도 틀림 진행 속도를 분석한 사례는 적음."
        )
    ]
    ok, _ = validate_suggestion(
        '{"action": "rewrite", "text": "궤도 틀림 진행 속도를 분석한 사례는 적음.", '
        '"reason": "근거대로"}',
        "선행연구가 전혀 없음.",
        ev,
    )
    assert ok == {
        "action": "rewrite",
        "text": "궤도 틀림 진행 속도를 분석한 사례는 적음.",
        "reason": "근거대로",
        "filtered": False,
    }
    bad, _ = validate_suggestion(
        '{"action": "rewrite", "text": "2027년까지 「궤도혁신계획」으로 40% 줄임.", "reason": "x"}',
        "원문",
        ev,
    )
    assert bad["action"] == "remove" and bad["filtered"] and bad["text"] == ""
    assert validate_suggestion("형식 아님", "원문", ev) == (None, "invalid")


def test_review_view_and_decisions_drop_the_alert():
    sec = _sec("tech_importance", "선행연구는 다루지 않음.", "본 연구는 다름.")
    h0, h1 = text_hash(sec.sentences[0].text), text_hash(sec.sentences[1].text)
    lc = {
        "enabled": True,
        "mismatches": 1,
        "mismatch_hashes": [h0],
        "verdicts": {h0: "불일치", h1: "부분"},
        "counts": {"지지": 0, "부분": 1, "불일치": 1},
        "suggestions": [
            {
                "id": "lc-aaaaaaaaaaaa",
                "section": "tech_importance",
                "text_hash": h0,
                "status": "open",
                "action": "rewrite",
                "text": "다시 쓴 문장임.",
                "reason": "r",
            }
        ],
    }
    view = review_view(lc, [sec])
    assert view["verdicts"] == {"s:tech_importance:0": "불일치", "s:tech_importance:1": "부분"}
    assert view["suggestions"]["s:tech_importance:0"]["action_label"] == "근거 안에서 다시 쓰기"
    assert view["unresolved"] == 1 and "original" not in view["suggestions"]["s:tech_importance:0"]
    assert len(local_check_problems([sec], lc)) == 1
    lc["suggestions"][0]["status"] = "dismissed"
    assert unresolved_count([sec], lc) == 0 and local_check_problems([sec], lc) == []


def _settings(tmp_path):
    from pydantic import SecretStr

    return Settings(
        _env_file=None,
        fake_llm=True,
        api_token=SecretStr(TOKEN),
        runs_dir=tmp_path / "runs",
        db_path=tmp_path / "never-created.sqlite",
        static_dir=tmp_path / "no-dist",
    )


async def _drafted(c, run_id):
    for _ in range(3000):  # 병렬 실행(xdist)에서는 느리다
        status = (await c.get(f"/v1/runs/{run_id}", headers=AUTH)).json()["status"]
        if (
            status == "drafted"
            and (await c.get(f"/v1/runs/{run_id}/draft-review", headers=AUTH)).status_code == 200
        ):
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"초안이 끝나지 않음: {status}")


async def test_fake_flow_mismatch_suggestion_apply_and_dismiss(tmp_path):
    from rra.composition import build_api

    app = build_api(_settings(tmp_path), sse_poll_sec=0.01)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ids = []
        for _ in range(2):
            r = await c.post("/v1/runs", json=SLOTS, headers=AUTH)
            ids.append(r.json()["run_id"])
        for rid in ids:
            await _drafted(c, rid)

        # 판정·제안이 초안 화면 데이터에 실린다 — 자동 반영 없음
        rid = ids[0]
        draft = (await c.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()
        lc = draft["local_check"]
        assert lc["verdicts"]["s:tech_importance:0"] == "불일치"
        assert lc["verdicts"]["s:tech_importance:1"] == "부분"
        assert lc["counts"]["불일치"] == 1 and lc["unresolved"] == 1
        sugg = lc["suggestions"]["s:tech_importance:0"]
        assert sugg["status"] == "open" and sugg["action"] == "rewrite" and sugg["text"]
        tech = next(s for s in draft["sections"] if s["key"] == "tech_importance")
        assert tech["sentences"][0]["text"] != sugg["text"]  # 자동 반영 안 함
        check = (await c.get(f"/v1/runs/{rid}/submit-check", headers=AUTH)).json()
        ev = next(i for i in check["items"] if i["key"] == "evidence_approval")
        assert ev["local_mismatch"] == 1 and "로컬 검토 불일치 1문장" in ev["detail"]

        # [반영] → 보통 편집 경로로 새 버전
        before = draft["version"]
        r = await c.post(
            f"/v1/runs/{rid}/local-review/{sugg['id']}/apply",
            json={"base_version": before},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["version"] == before + 1
        after = (await c.get(f"/v1/runs/{rid}/draft", headers=AUTH)).json()
        tech = next(s for s in after["sections"] if s["key"] == "tech_importance")
        assert tech["sentences"][0]["text"] == sugg["text"]
        assert tech["sentences"][0]["evidence"]  # 원래 근거 유지
        assert after["local_check"]["unresolved"] == 0
        assert after["local_check"]["applied"][0]["version"] == before + 1
        r = await c.post(f"/v1/runs/{rid}/local-review/{sugg['id']}/apply", json={}, headers=AUTH)
        assert r.status_code == 409  # 두 번 반영하지 않는다

        # [무시] → 결정 기록, 새 버전 없음
        rid2 = ids[1]
        d2 = (await c.get(f"/v1/runs/{rid2}/draft", headers=AUTH)).json()
        s2 = d2["local_check"]["suggestions"]["s:tech_importance:0"]
        r = await c.post(f"/v1/runs/{rid2}/local-review/{s2['id']}/dismiss", headers=AUTH)
        assert r.status_code == 200
        view = r.json()["local_check"]
        assert view["suggestions"]["s:tech_importance:0"]["status"] == "dismissed"
        assert view["unresolved"] == 0
        d2b = (await c.get(f"/v1/runs/{rid2}/draft", headers=AUTH)).json()
        assert d2b["version"] == d2["version"] and d2b["versions"] == d2["versions"]
        assert not [p for p in d2b["problems"] if p["code"] == "local_evidence_mismatch"]
        check = (await c.get(f"/v1/runs/{rid2}/submit-check", headers=AUTH)).json()
        ev = next(i for i in check["items"] if i["key"] == "evidence_approval")
        assert ev["local_mismatch"] == 0
        # 다시 받기는 결정 뒤 거부, 모르는 id 는 404
        r = await c.post(f"/v1/runs/{rid2}/local-review/{s2['id']}/retry", headers=AUTH)
        assert r.status_code == 409
        r = await c.post(f"/v1/runs/{rid2}/local-review/nope/dismiss", headers=AUTH)
        assert r.status_code == 404


def test_rule_mismatch_catches_changed_numbers_and_unrelated_claims():
    """2026-10-28 실측: 7B 는 바꿔 넣은 수치를 "지지", 무관한 주장을 "부분" 으로 봤다
    — 규칙이 불일치로."""
    from rra.domain.rules.local_review import parse_verdicts, rule_mismatch

    ev = [
        "정부는 노후 궤도의 검측 고도화와 보수 체계 개선으로 철도 안전을 높이려 함. "
        "2025년까지 궤도 검측 차량 3대를 추가 도입할 계획이다."
    ]
    assert not rule_mismatch("정부는 노후 궤도 검측 고도화로 철도 안전을 높이려 함.", ev)
    assert rule_mismatch("2025년까지 궤도 검측 차량 10대를 추가 도입할 계획임.", ev)
    assert rule_mismatch("공사는 전차선 아크 감지를 위해 드론 점검을 전면 도입함.", ev)
    assert not rule_mismatch(
        "Track geometry 열화 예측을 다룸.", ["Track geometry degradation " * 5]
    )
    ids = {"s:a:0", "s:a:1"}
    bare = (
        '[{"sentence_id": "s:a:0", "support": "지지"}, '
        '{"sentence_id": "s:a:1", "support": "불일치"}]'
    )
    assert parse_verdicts(bare, ids) == {"s:a:0": "지지", "s:a:1": "불일치"}  # 배열만 와도
    one = '{"support": [{"sentence_id": "s:a:0", "support": "부분"}]}'
    assert parse_verdicts(one, ids) == {"s:a:0": "부분"}
